import asyncio
import json
import logging
import os
import pathlib
import subprocess
import sys
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import CancelledError, Future
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from backpack import model
from backpack.app_host import AppHost
from backpack.app_info import APP_VERSION
from backpack.i18n import i18n, system_locales
from backpack.paths import applogs
from backpack.storage import Storage
from backpack.storage.settings import Settings
from backpack.ui import UI, DialogAction, NotifyAction, RecentItem

if TYPE_CHECKING:
    from backpack import ai
    from backpack.nominatim import Nominatim
    from backpack.route_details import RouteDetails

logger = logging.getLogger(__name__)


class Backpack:
    def __init__(self, app: AppHost, storage: Storage) -> None:
        self.app = app
        # Origin token for edits made in response to a frontend call. The
        # frontend reflects these optimistically, so on_change skips pushing
        # them back to it.
        self.frontend = object()
        self.ui = UI(app.exec_script)
        self.storage = storage
        self.poi: dict[str, tuple[model.Poi, ...]] = {}

        # geopy (geocoding, distance math), overpy and the ai package
        # (pydantic-ai, google-genai) are well over a second of imports the
        # window does not need to paint. Build them on one background thread so
        # the window comes up meanwhile. Each future settles with its object,
        # or with the exception if the build failed; async callers await it and
        # only block if it is not ready yet.
        self._nominatim: Future[Nominatim] = Future()
        self._route_details: Future[RouteDetails] = Future()
        self._ai: Future[ai.Agent] = Future()

        self.doc = model.Document()
        self.filepath: str | None = None
        self._closed = False
        self._settings_task: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

        async def sched_ask_assist(
            chat_id: str, model_id: str, prompt: str
        ) -> None:
            # Run the turn detached so later frontend calls can be processed
            self.add_task(self.ask_assist(chat_id, model_id, prompt))

        # The calls the frontend may make, dispatched by name. Anything not
        # listed here is refused, so no other member is reachable from JS.
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {
            "new_doc": self.new_doc,
            "open_doc": self.open_doc,
            "save_doc": self.save_doc,
            "open_settings": self.open_settings,
            "open_logs": self.open_logs,
            "remove_recent": self.remove_recent,
            "set_theme": self.set_theme,
            "set_locale": self.set_locale,
            "set_trip_info": self.set_trip_info,
            "add_route": self.add_route,
            "set_route_info": self.set_route_info,
            "remove_route": self.remove_route,
            "move_route": self.move_route,
            "add_chat": self.add_chat,
            "del_chat": self.del_chat,
            "ask_assist": sched_ask_assist,
            "stop_assist": self.stop_assist,
        }

        self._bg_load_thread = threading.Thread(
            target=self._bg_load, name="app.bg_load", daemon=True
        )
        self._bg_load_thread.start()

    def _bg_load(self) -> None:
        """Import and build the heavy services off the startup path.

        Runs on a background thread started in __init__ and settles each service
        future with its object, or with the exception if the import or build
        failed. Only Python object construction happens here, no event loop, so
        it is safe off the mainloop. The agent is built last since it needs th
        geocoder.
        """
        if self._nominatim.set_running_or_notify_cancel():
            try:
                from backpack.nominatim import Nominatim
                self._nominatim.set_result(Nominatim())
            except Exception as e:
                self._nominatim.set_exception(e)
                logger.exception("nominatim load failed")

        if self._route_details.set_running_or_notify_cancel():
            try:
                from backpack.route_details import RouteDetails
                self._route_details.set_result(
                    RouteDetails(self.storage.poi_cache)
                )
            except Exception as e:
                self._route_details.set_exception(e)
                logger.exception("route_details load failed")

        if self._ai.set_running_or_notify_cancel():
            try:
                from backpack import ai
                self._ai.set_result(
                    ai.Agent(self.storage, self._nominatim.result())
                )
            except Exception as e:
                self._ai.set_exception(e)
                logger.exception("ai load failed")
        logger.debug("background load done")

    async def dispatch(self, name: str, args: tuple[Any, ...]) -> None:
        """Run the frontend call name with args, if it is allowed."""
        handler = self._handlers.get(name)
        if handler is None:
            logger.error(f"no handler for {name!r}")
            return
        await handler(*args)

    def add_task(self, coro: Coroutine[Any, Any, None]) -> None:
        """Schedule coro as a detached, tracked mainloop task.

        Keeps a strong reference so the task is not garbage-collected mid run,
        and drops it once it settles. Call from the mainloop.
        """
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> bool:
        """Close the app, asking to save pending edits first.

        Returns False if the user canceled at the save prompt, in which case
        the app keeps running.
        """
        if not await self._show_save_dialog():
            return False
        self.teardown()
        return True

    def teardown(self) -> None:
        """Release resources. Call on the mainloop; later calls do nothing.

        Also the fallback for an abnormal exit, where no save prompt can be
        shown.
        """
        if self._closed:
            return
        self._closed = True
        logger.debug("app shutting down")

        # cancel running agents and pending detail loads
        for task in list(self._tasks):
            task.cancel()

        # Drop a pending build so its awaiters wake, or cancel the built
        # service; a build still in flight cannot be cancelled and just
        # finishes on the daemon thread.
        for svc in (self._nominatim, self._route_details):
            if svc.cancel():
                continue
            if svc.done() and svc.exception() is None:
                svc.result().cancel()
        self.storage.poi_cache.close()

    async def start(self) -> None:
        """Push the saved preferences to the frontend and open a document.

        Run once the frontend has loaded, so it is ready for the calls.
        """
        async def _evict_poi_cache() -> None:
            """Run POI cache eviction on a worker thread."""
            try:
                deleted = await asyncio.to_thread(self.storage.poi_cache.evict)
                if deleted:
                    logger.debug(f"poi cache: evicted {deleted} tiles")
            except Exception:
                logger.exception("poi cache eviction failed")

        await self.set_locale(
            self.storage.settings.locale, self.storage.settings.units
        )
        await self.set_theme(self.storage.settings.theme)
        self._update_recent_items_view()

        self.add_task(_evict_poi_cache())

        # load last opened document
        last = self.storage.settings.last_filepath
        if last and pathlib.Path(last).exists() and await self.open_doc(last):
            return
        await self.new_doc()

    async def new_doc(self) -> None:
        if not await self._show_save_dialog():
            return

        # cancel running agents and pending detail loads
        for task in list(self._tasks):
            task.cancel()

        doc = model.Document()
        doc.subscribe(self.on_change)
        self.doc = doc
        self.poi = {}
        self.filepath = None
        self._reset_ui(doc)
        chat = model.ChatData()
        with doc.edit(self.frontend) as ed:
            ed.apply(model.AddChat(chat))
        self.ui.assist.set_active_chat(chat.id)
        doc.mark_saved()
        self._push_doc_state()

    async def open_doc(self, filepath: str | None = None) -> bool:
        if not await self._show_save_dialog():
            return False

        if filepath is None:
            filepath = await asyncio.wrap_future(self.app.show_open_dialog(
                filters=(
                    (i18n.gettext("Json files"), "*.json"),
                    (i18n.gettext("All files"), "*.*"),
                )
            ))
            if not filepath:
                return False

        try:
            text = await asyncio.to_thread(
                pathlib.Path(filepath).read_text, encoding="utf-8"
            )
            doc = model.Document.from_dict(json.loads(text))
        except (OSError, ValueError) as e:
            logger.exception(f'Failed to open "{filepath}"')
            self._remove_recent_item(filepath)
            self.ui.notify(
                str(e) or type(e).__name__,
                intent="error",
                title=i18n.gettext("Could not open trip")
            )
            return False

        # cancel running agents and pending detail loads
        for task in list(self._tasks):
            task.cancel()

        doc.subscribe(self.on_change)
        self.doc = doc
        self.poi = {}
        self.filepath = filepath
        self._reset_ui(doc)
        if not doc.chats():
            chat = model.ChatData()
            with doc.edit(self.frontend) as ed:
                ed.apply(model.AddChat(chat))
            self.ui.assist.set_active_chat(chat.id)
        for r in doc.routes():
            self.add_task(self.load_route_details(r.id, r.track))
        doc.mark_saved()
        self._add_recent_item(filepath, doc)
        self._push_doc_state()
        logger.info(
            f"opened {filepath!r}: {len(doc.routes())} routes, "
            f"{len(doc.chats())} chats"
        )
        return True

    def _reset_ui(self, doc: model.Document) -> None:
        """Render the whole UI to match doc: trip, routes and chats.

        The assistant model list is not needed to draw the document, so it is
        pushed separately when the background ai import lands, keeping the
        render off that import.
        """
        async def enum_llm() -> None:
            """Fill the composer once the model list is ready.

            Scheduled from _reset_ui so the document paints without waiting for
            the background ai import; the models arrive a moment later.
            """
            try:
                agent = await asyncio.wrap_future(self._ai)
                self.ui.assist.set_models(await agent.enum_models())
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception("failed to enumerate assistant models")
                self.ui.notify(
                    str(e) or type(e).__name__,
                    intent="error",
                    title=i18n.gettext("Assistant unavailable"),
                )

        from backpack import route

        self.ui.clear_notify()
        self.ui.clear_doc()
        self.ui.add_trip_card(f"trip-{uuid4().hex}", doc.title, doc.notes)
        for r in doc.routes():
            self.ui.add_route_card(
                r.id, r.title, r.notes, r.track,
                route.RouteStats.from_track(r.track) if r.track else None,
            )
        self.ui.assist.clear()
        self.add_task(enum_llm())
        for chat in doc.chats():
            self.ui.assist.new_chat(chat.id, chat.title)
            for turn in chat.turns:
                self.ui.assist.new_turn(chat.id, turn.id, turn.prompt)
                for item in turn.items:
                    match item:
                        case model.ChatThinking(text=text):
                            self.ui.assist.append_thinking(chat.id, text)
                        case model.ChatReply(text=text):
                            self.ui.assist.append_reply(chat.id, text)
                        case model.ChatCard():
                            self.ui.assist.add_card(chat.id, item)
                self.ui.assist.end_turn(chat.id)
        chats = doc.chats()
        if chats:
            self.ui.assist.set_active_chat(chats[0].id)
            # Replaying saved turns above runs end_turn per chat, which flags
            # every non-active chat unread. Opening a document is not new
            # activity, so clear those flags once the restore is done.
            self.ui.assist.mark_read([c.id for c in chats])

    async def save_doc(
        self, filepath: str | None = None, show_dialog: bool = False
    ) -> bool:
        """Save the document. Return True if saved, False if canceled."""
        if filepath is None:
            if show_dialog or self.filepath is None:
                filepath = await asyncio.wrap_future(self.app.show_save_dialog(
                    filename="trip.json",
                    filters=(
                        (i18n.gettext("Json files"), "*.json"),
                        (i18n.gettext("All files"), "*.*"),
                    )
                ))
                if not filepath:
                    return False
            else:
                filepath = self.filepath

        doc = self.doc
        try:
            text = json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)
            await asyncio.to_thread(
                pathlib.Path(filepath).write_text, text, encoding="utf-8"
            )
        except OSError as e:
            logger.exception(f'Failed to save to "{filepath}"')
            self.ui.notify(
                str(e) or type(e).__name__,
                intent="error", title=i18n.gettext("Could not save trip")
            )
            return False

        self.filepath = filepath
        doc.mark_saved()
        self._add_recent_item(filepath, doc)
        self._push_doc_state()
        logger.info(f"saved {filepath!r}")
        return True

    async def _show_save_dialog(self) -> bool:
        """Ask to save pending edits before replacing the document.

        Returns True to proceed with the operation, False to cancel it.
        """
        if not self.doc.has_edits:
            return True
        result = await asyncio.wrap_future(self.ui.show_dialog(
            i18n.gettext("Save changes?"),
            i18n.gettext(
                "This trip has unsaved changes. Save them before continuing?"
            ),
            actions=(
                DialogAction(i18n.gettext("Cancel"), result="cancel"),
                DialogAction(i18n.gettext("Don't save"), result="discard"),
                DialogAction(
                    i18n.gettext("Save"), result="save", appearance="primary"
                )
            )
        ))
        if result == "save":
            return await self.save_doc()
        return bool(result == "discard")

    def _add_recent_item(self, filepath: str, doc: model.Document) -> None:
        self.storage.settings = self.storage.settings.add_recent(
            Settings.RecentItem(
                title=doc.title,
                routes=len(doc.routes()),
                filepath=filepath,
            )
        )
        self._update_recent_items_view()

    def _remove_recent_item(self, filepath: str) -> None:
        self.storage.settings = self.storage.settings.remove_recent(filepath)
        self._update_recent_items_view()

    def _push_doc_state(self) -> None:
        """Reflect the open file and dirty flag in the app bar and title.

        The frontend draws the file name and a dirty dot from this, and the
        native window title mirrors both so the source and unsaved state show
        even when the window is not focused.
        """
        name = pathlib.Path(self.filepath).name if self.filepath else None
        dirty = self.doc.has_edits
        self.ui.set_doc_state(name, dirty)
        trip = self.doc.title.strip()
        label = trip or name or i18n.gettext("Untitled trip")
        prefix = "* " if dirty else ""
        self.app.window.set_title(f"{prefix}{label} - Backpack")

    def _update_recent_items_view(self) -> None:
        self.ui.set_recent(
            RecentItem(
                r.title,
                (i18n.gettext("no routes") if r.routes == 0 else
                 i18n.ngettext("{n} route", "{n} routes", r.routes)
                ),
                r.filepath
            )
            for r in self.storage.settings.recent
        )

    async def remove_recent(self, filepath: str) -> None:
        """Drop a trip from the recent list without opening it."""
        self._remove_recent_item(filepath)

    async def set_theme(self, mode: str) -> None:
        """Apply a theme mode to the live window without persisting it.

        This is the single place the window theme is applied, so a preview can
        follow a selection and later restore the original mode. The web content
        is themed by the frontend, and the native window title bar is themed by
        the host window, since it is drawn by the OS outside the document and
        would otherwise stay light.
        """
        self.ui.set_theme(mode)
        self.app.window.set_theme(mode)

    async def set_locale(self, locale: str, units: str) -> None:
        """Apply locale and units to the live app without persisting them.

        :param str locale: "system" to follow the OS, or a tag, e.g. "en-US".
        :param str units: "auto" to follow the OS, or "metric" or "imperial".
        """
        i18n.load([locale] + system_locales(), units)
        self.ui.set_locale(i18n.tag, i18n.units)
        self._update_recent_items_view()

    async def open_settings(self) -> None:
        """Open the settings dialog without blocking the calling frontend.

        The dialog flow runs as a detached task so this call returns at once,
        leaving the frontend action chain free while the dialog is open. That
        lets frontend reach the backend meanwhile. A second request is ignored
        while a dialog is already open.

        A stored API key is never sent to the frontend, only whether one exists,
        so the dialog can offer to replace or remove it.
        """
        if self._settings_task is not None and not self._settings_task.done():
            return

        async def do_show_settings_dialog() -> None:
            key = self.storage.vault.get("gemini_api_key")
            if not key:
                key = await self.storage.load_key("gemini_api_key")
            poi_cache_bytes = await self.storage.poi_cache_size()
            cur_settings = {
                "theme": self.storage.settings.theme,
                "locale": self.storage.settings.locale,
                "units": self.storage.settings.units,
                "gemini_api_key_set": bool(key),
                "poi_cache_bytes": poi_cache_bytes,
                "version": APP_VERSION,
            }

            new_settings = await asyncio.wrap_future(
                self.ui.show_settings_dialog(cur_settings)
            )
            if not isinstance(new_settings, dict):
                return

            # apply new theme
            theme = new_settings.get("theme", self.storage.settings.theme)
            if theme != self.storage.settings.theme:
                self.storage.settings = replace(
                    self.storage.settings, theme=theme
                )
                await self.set_theme(theme)

            # apply locale and units from the dialog so Save does not depend on
            # a live preview having already pushed them
            locale = new_settings.get("locale", self.storage.settings.locale)
            units = new_settings.get("units", self.storage.settings.units)
            if (locale != self.storage.settings.locale
                    or units != self.storage.settings.units):
                self.storage.settings = replace(
                    self.storage.settings, locale=locale, units=units
                )
                await self.set_locale(locale, units)

            await self.storage.save_settings()

            # store, replace or remove the API key: the dialog sends "" to
            # leave the stored key alone, a string to replace it and None to
            # remove it
            api_key = new_settings.get("gemini_api_key", "")
            if api_key != "":
                await self.storage.store_key("gemini_api_key", api_key)

            if new_settings.get("clear_poi_cache"):
                await self.storage.clear_poi_cache()

        def on_settings_dialog_close(task: "asyncio.Task[None]") -> None:
            self._settings_task = None
            if not task.cancelled() and (exc := task.exception()) is not None:
                logger.error("open settings failed", exc_info=exc)
                self.ui.notify(
                    str(exc) or type(exc).__name__,
                    intent="error",
                    title=i18n.gettext("Could not open settings")
                )

        self._settings_task = asyncio.ensure_future(do_show_settings_dialog())
        self._settings_task.add_done_callback(on_settings_dialog_close)

    async def open_logs(self) -> None:
        """Reveal the log folder in the OS file manager.

        The directory is created first so a reveal never fails just because
        nothing has been logged to disk yet. The reveal runs off the mainloop
        since it spawns the file manager, and any failure is logged and surfaced
        as a notification rather than raised to the frontend.
        """
        def reveal() -> None:
            path = applogs()
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=True)
            else:
                subprocess.run(["xdg-open", str(path)], check=True)

        try:
            await asyncio.to_thread(reveal)
        except Exception as e:
            logger.exception("Failed to open logs")
            self.ui.notify(
                str(e) or type(e).__name__,
                intent="error",
                title=i18n.gettext("Could not open logs")
            )

    async def add_chat(self) -> None:
        chat = model.ChatData()
        with self.doc.edit(self.frontend) as ed:
            ed.apply(model.AddChat(chat))
        self.ui.assist.set_active_chat(chat.id)

    async def del_chat(self, chat_id: str) -> None:
        active: str | None = None
        with self.doc.edit(self.frontend) as ed:
            ed.apply(model.RemoveChat(chat_id))
            if not self.doc.chats():
                chat = model.ChatData()
                ed.apply(model.AddChat(chat))
                active = chat.id
        if active is None:
            chats = self.doc.chats()
            active = chats[-1].id if chats else None
        if active is not None:
            self.ui.assist.set_active_chat(active)

    async def ask_assist(
        self, chat_id: str, model_id: str, prompt: str
    ) -> None:
        """Run one assistant turn, streaming replies to the frontend.

        The agent streams thinking and reply tokens through the callbacks and
        returns the finished items (including a trailing error card on failure),
        which are committed as one turn. A stopped run raises CancelledError
        instead, so the turn is dropped and the chat left idle.
        """
        async def card_action(fut: Future[Any]) -> None:
            try:
                action_id = await asyncio.wrap_future(fut)
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.ui.notify(str(e) or type(e).__name__)
                return

            if action_id != "retry" or self.doc.chat(chat_id) is None:
                return
            # Follow the live composer choice, falling back to the model the
            # failed turn used if none comes back.
            cur_model_id = await asyncio.wrap_future(
                self.ui.assist.get_model(chat_id)
            )
            with self.doc.edit(self.frontend) as ed:
                ed.apply(model.RemoveChatTurn(chat_id, turn_id))
            self.add_task(self.ask_assist(
                chat_id, cur_model_id or model_id, prompt
            ))

        logger.debug(f"chat_id:{chat_id} model_id:{model_id!r}")
        if self.doc.chat(chat_id) is None:
            return

        turn_id = model.ChatTurn.unique_id()
        self.ui.assist.new_turn(chat_id, turn_id, prompt)

        # The agent is normally loaded well before the first prompt, but wait
        # for the background import here in case it is not, so the very first
        # turn still works instead of failing.
        try:
            agent = await asyncio.wrap_future(self._ai)
        except asyncio.CancelledError:
            self.ui.assist.del_turn(chat_id, turn_id)
            self.ui.assist.end_turn(chat_id)
            return
        except Exception as e:
            logger.exception("assistant unavailable")
            self.ui.assist.del_turn(chat_id, turn_id)
            self.ui.assist.end_turn(chat_id)
            self.ui.notify(
                str(e) or type(e).__name__,
                intent="error",
                title=i18n.gettext("Assistant unavailable"),
            )
            return

        try:
            items = await agent.ask(
                self.doc, self.poi, chat_id, model_id, prompt,
                on_text=lambda text: self.ui.assist.append_reply(chat_id, text),
                on_think=(
                    lambda text: self.ui.assist.append_thinking(chat_id, text)
                )
            )
        except asyncio.CancelledError:
            # Stopped by the user: drop the streamed turn and clear the busy
            # state so the frontend can restore the prompt for editing.
            self.ui.assist.del_turn(chat_id, turn_id)
            self.ui.assist.end_turn(chat_id)
            return

        turn = model.ChatTurn(turn_id, prompt, items)
        with self.doc.edit(agent) as ed:
            ed.apply(model.AppendChatTurn(chat_id, turn))

        for item in items:
            if isinstance(item, model.ChatCard):
                self.add_task(
                    card_action(self.ui.assist.add_card(chat_id, item))
                )
        self.ui.assist.end_turn(chat_id)

    async def stop_assist(self, chat_id: str) -> None:
        """Stop the assistant run for a chat, if one is in flight.

        The stopped run drops its streamed turn and clears the busy state,
        leaving the chat ready for the next prompt.
        """
        # Nothing can be running before the agent exists, so a stop that races
        # the background load is a no-op rather than a wait.
        if self._ai.done() and self._ai.exception() is None:
            self._ai.result().stop(chat_id)

    async def set_trip_info(self, card_id: str, title: str, notes: str) -> None:
        with self.doc.edit(self.frontend) as ed:
            ed.apply(model.SetDocInfo(title=title, notes=notes))

    async def add_route(self) -> None:
        from backpack import route

        files = await asyncio.wrap_future(self.app.show_open_dialog(
            multiple=True,
            filters=(
                (i18n.gettext("GPX files"), "*.gpx"),
                (i18n.gettext("All files"), "*.*"),
            )
        ))
        if not files:
            return

        self.ui.set_busy(True, i18n.gettext("Loading routes..."))
        added = 0
        try:
            for filepath in files:
                try:
                    text = await asyncio.to_thread(
                        pathlib.Path(filepath).read_text, encoding="utf-8"
                    )
                    gpx = await asyncio.to_thread(route.parse_gpx, text)
                    r = model.RouteData(
                        title=gpx.name or pathlib.Path(filepath).stem,
                        notes=gpx.description,
                        track=gpx.track,
                    )
                    with self.doc.edit(self) as ed:
                        ed.apply(model.AddRoute(r))
                    self.add_task(self.load_route_details(r.id, r.track))
                    added += 1
                except Exception as e:
                    logger.exception(f'Failed to load "{filepath}"')
                    name = pathlib.Path(filepath).name
                    self.ui.notify(
                        f"{name}: {e}",
                        intent="error",
                        title=i18n.gettext("Could not load route")
                    )
        finally:
            self.ui.set_busy(False)
        logger.info(f"added {added} of {len(files)} routes")

    async def set_route_info(
        self, card_id: str, title: str, notes: str
    ) -> None:
        with self.doc.edit(self.frontend) as ed:
            ed.apply(model.SetRouteInfo(card_id, title=title, notes=notes))

    async def remove_route(self, card_id: str) -> None:
        with self.doc.edit(self.frontend) as ed:
            ed.apply(model.RemoveRoute(card_id))

    async def move_route(
        self, card_id: str, after_id: str | None = None
    ) -> None:
        with self.doc.edit(self.frontend) as ed:
            ed.apply(model.MoveRoute(card_id, after_id))

    async def load_route_details(
        self, route_id: str, track: tuple[model.TrackPoint, ...]
    ) -> None:
        """Load one route's POIs and store them, reflecting it in the UI.

        The fetch runs on the route-details pool but this coroutine runs on
        the mainloop, so self.poi is only ever rebound here, without a lock.
        Route ids are unique across documents, so a completion that lands
        after the document changed just adds an entry no current route reads;
        it is dropped on the next new or open.
        """
        async def retry_poi(route_id: str, error: Exception) -> bool:
            """Prompt to retry a failed POI load; return True to retry."""
            route = self.doc.route(route_id)
            name = route.title if route else route_id
            notify_fut = self.ui.notify(
                f"{name}: {error}",
                intent="error",
                title=i18n.gettext("Could not load route details"),
                actions=[
                    NotifyAction(i18n.gettext("Retry"), result="retry")
                ]
            )
            try:
                action = await asyncio.wrap_future(notify_fut)
            except CancelledError:
                return False
            return bool(action == "retry")

        try:
            route_details = await asyncio.wrap_future(self._route_details)
        except CancelledError:
            return
        except Exception:
            logger.exception("route details unavailable")
            return

        while True:
            self.ui.set_route_loading(route_id, True)
            try:
                poi = await route_details.load_poi(track)
            except CancelledError:
                self.ui.set_route_loading(route_id, False)
                return
            except Exception as e:
                self.ui.set_route_loading(route_id, False)
                logger.exception(f"route_id:{route_id} POI load failed")
                if await retry_poi(route_id, e):
                    continue
                return
            self.poi = {**self.poi, route_id: poi}
            self.ui.set_route_loading(route_id, False)
            logger.debug(f"route_id:{route_id} loaded {len(poi)} poi")
            return

    def on_change(self, change: model.Change, origin: model.Origin) -> None:
        # Any committed change marks the document dirty, and a trip rename
        # also moves the title, so refresh the app bar and window title here.
        self._push_doc_state()
        if isinstance(change, model.AddRoute):
            from backpack import route

            track = change.route.track
            self.ui.add_route_card(
                change.route.id,
                change.route.title,
                change.route.notes,
                track,
                route.RouteStats.from_track(track) if track else None,
            )
        elif isinstance(change, model.SetDocInfo):
            if origin is not self.frontend:
                self.ui.set_trip_card(self.doc.title, self.doc.notes)
        elif isinstance(change, model.SetRouteInfo):
            if origin is not self.frontend:
                r = self.doc.route(change.route_id)
                if r is not None:
                    self.ui.set_route_card(r.id, r.title, r.notes)
        elif isinstance(change, model.RemoveRoute):
            self.poi = {
                rid: p for rid, p in self.poi.items()
                if rid != change.route_id
            }
            if origin is not self.frontend:
                self.ui.remove_card(change.route_id)
        elif isinstance(change, model.MoveRoute):
            if origin is not self.frontend:
                self.ui.move_card(change.route_id, change.after_id)
        elif isinstance(change, model.AddChat):
            self.ui.assist.new_chat(change.chat.id, change.chat.title)
        elif isinstance(change, model.RemoveChat):
            self.ui.assist.del_chat(change.chat_id)
        elif isinstance(change, model.SetChatTitle):
            self.ui.assist.set_chat_title(change.chat_id, change.title)
        elif isinstance(change, model.AppendChatTurn):
            pass  # already streamed to the UI while running
        elif isinstance(change, model.RemoveChatTurn):
            self.ui.assist.del_turn(change.chat_id, change.turn_id)
