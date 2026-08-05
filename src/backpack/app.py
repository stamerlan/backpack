import asyncio
import json
import logging
import pathlib
import webview
from concurrent.futures import CancelledError, Future
from typing import Any
from uuid import uuid4

from backpack import ai, model, route
from backpack.api import Api
from backpack.js_worker import JsWorker
from backpack.nominatim import Nominatim
from backpack.route_details import RouteDetails
from backpack.storage import Storage
from backpack.storage.settings import Settings
from backpack.ui import UI, DialogAction, NotifyAction, RecentItem

logger = logging.getLogger(__name__)


class App:
    def __init__(
        self, mainloop: asyncio.AbstractEventLoop, storage: Storage
    ) -> None:
        self.mainloop = mainloop
        self.window: webview.Window | None = None
        self.api = Api(self)
        self.js = JsWorker()
        self.ui = UI(self.js)
        self.storage = storage
        self.nominatim = Nominatim()
        self.route_details = RouteDetails()
        self.ai = ai.Agent(storage, self.nominatim)
        self.ai_models: asyncio.Future[tuple[ai.AiModel, ...]] = (
            mainloop.create_future()
        )
        self.doc = model.Document()
        self.filepath: str | None = None

    def start(self, window: webview.Window) -> None:
        """Bind the window and start application tasks."""
        self.window = window
        self.js.start(window)
        logger.debug("app started")

    def shutdown(self) -> None:
        logger.debug("app shutting down")
        self.api.shutdown()
        self.js.shutdown()
        self.nominatim.cancel()
        self.route_details.cancel()

    async def on_loaded(self) -> None:
        # enumerate models in the background; it might take a while
        self.ai_models = asyncio.ensure_future(ai.enum_models())
        self._update_recent_items_view()
        await self.new_doc()

    async def new_doc(self) -> None:
        logger.debug("")
        if not await self._show_save_dialog():
            return
        doc = model.Document()
        doc.subscribe(self.on_change)
        self.doc = doc
        self.filepath = None
        models = await self.ai_models
        self._reset_ui(doc, models)
        chat = model.ChatData()
        with doc.edit(self.api) as ed:
            ed.apply(model.AddChat(chat))
        self.ui.assist.set_active_chat(chat.id)
        doc.mark_saved()

    async def open_doc(self, filepath: str | None = None) -> None:
        logger.debug(f"filepath:{filepath}")
        if self.window is None:
            return
        if not await self._show_save_dialog():
            return

        if filepath is None:
            files = await asyncio.to_thread(
                self.window.create_file_dialog,
                webview.FileDialog.OPEN,
                file_types=("Json files (*.json)", "All files (*.*)"),
            )
            if not files:
                return
            filepath = files if isinstance(files, str) else files[0]

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
                title="Could not open trip"
            )
            return

        doc.subscribe(self.on_change)
        self.doc = doc
        self.filepath = filepath
        models = await self.ai_models
        self._reset_ui(doc, models)
        if not doc.chats():
            chat = model.ChatData()
            with doc.edit(self.api) as ed:
                ed.apply(model.AddChat(chat))
            self.ui.assist.set_active_chat(chat.id)
        for r in doc.routes():
            if r.poi is None:
                self._load_route_details(doc, r.id, r.track)
        doc.mark_saved()
        self._add_recent_item(filepath, doc)

    def _reset_ui(
        self, doc: model.Document, models: tuple[ai.AiModel, ...]
    ) -> None:
        """Render the whole UI to match doc: trip, routes and chats."""
        self.ui.clear_notify()
        self.ui.clear_doc()
        self.ui.add_trip_card(f"trip-{uuid4().hex}", doc.title, doc.notes)
        for r in doc.routes():
            self.ui.add_route_card(
                r.id, r.title, r.notes, r.track,
                route.RouteStats.from_track(r.track) if r.track else None,
            )
        self.ui.assist.clear()
        self.ui.assist.set_models(models)
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

    async def save_doc(
        self, filepath: str | None = None, show_dialog: bool = False
    ) -> bool:
        """Save the document. Return True if saved, False if canceled."""
        logger.debug(f"filepath:{filepath} show_dialog:{show_dialog}")
        if self.window is None:
            return False

        if filepath is None:
            if show_dialog or self.filepath is None:
                files = await asyncio.to_thread(
                    self.window.create_file_dialog,
                    webview.FileDialog.SAVE,
                    save_filename="trip.json",
                    file_types=("Json files (*.json)", "All files (*.*)"),
                )
                if not files:
                    return False
                filepath = files if isinstance(files, str) else files[0]
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
                intent="error", title="Could not save trip"
            )
            return False

        self.filepath = filepath
        doc.mark_saved()
        self._add_recent_item(filepath, doc)
        return True

    async def _show_save_dialog(self) -> bool:
        """Ask to save pending edits before replacing the document.

        Returns True to proceed with the operation, False to cancel it.
        """
        if not self.doc.has_edits:
            return True
        result = await asyncio.wrap_future(self.ui.show_dialog(
            "Save changes?",
            "This trip has unsaved changes. Save them before continuing?",
            actions=(
                DialogAction("Cancel", result="cancel"),
                DialogAction("Don't save", result="discard"),
                DialogAction("Save", result="save", appearance="primary")
            )
        ))
        if result == "save":
            return await self.save_doc()
        return bool(result == "discard")

    def _add_recent_item(self, filepath: str, doc: model.Document) -> None:
        match len(doc.routes()):
            case 0:
                meta = "no routes"
            case 1:
                meta = "one route"
            case n:
                meta = f"{n} routes"
        self.storage.settings = self.storage.settings.add_recent(
            Settings.RecentItem(title=doc.title, meta=meta, filepath=filepath)
        )
        self._update_recent_items_view()

    def _remove_recent_item(self, filepath: str) -> None:
        self.storage.settings = self.storage.settings.remove_recent(filepath)
        self._update_recent_items_view()

    def _update_recent_items_view(self) -> None:
        self.ui.set_recent(
            RecentItem(r.title, r.meta, r.filepath)
            for r in self.storage.settings.recent
        )

    async def open_settings(self) -> None:
        logger.debug("")

    async def add_chat(self) -> None:
        logger.debug("")
        chat = model.ChatData()
        with self.doc.edit(self.api) as ed:
            ed.apply(model.AddChat(chat))
        self.ui.assist.set_active_chat(chat.id)

    async def del_chat(self, chat_id: str) -> None:
        logger.debug(f"chat_id:{chat_id}")
        active: str | None = None
        with self.doc.edit(self.api) as ed:
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
        logger.debug(f"chat_id:{chat_id} model_id:{model_id!r}")
        doc = self.doc
        if doc.chat(chat_id) is None:
            return

        turn_id = model.ChatTurn.unique_id()
        self.ui.assist.new_turn(chat_id, turn_id, prompt)

        items = list[model.ChatItem]()

        def on_text(text: str) -> None:
            if items and isinstance(items[-1], model.ChatReply):
                items[-1] = model.ChatReply(items[-1].text + text)
            else:
                items.append(model.ChatReply(text))
            self.ui.assist.append_reply(chat_id, text)

        def on_think(text: str) -> None:
            if items and isinstance(items[-1], model.ChatThinking):
                items[-1] = model.ChatThinking(items[-1].text + text)
            else:
                items.append(model.ChatThinking(text))
            self.ui.assist.append_thinking(chat_id, text)

        def card_action(fut: Future[Any]) -> None:
            try:
                action_id = fut.result()
            except CancelledError:
                return
            except Exception as e:
                self.ui.notify(str(e) or type(e).__name__)
                return

            logger.debug(
                f"chat_id:{chat_id} turn_id:{turn_id} action_id:{action_id!r}"
            )
            if action_id == "retry":
                async def _retry() -> None:
                    if self.doc.chat(chat_id) is None:
                        return
                    with self.doc.edit(self.api) as ed:
                        ed.apply(model.RemoveChatTurn(chat_id, turn_id))
                    await self.ask_assist(chat_id, model_id, prompt)
                asyncio.run_coroutine_threadsafe(_retry(), self.mainloop)

        card: model.ChatCard | None = None
        try:
            await self.ai.ask(
                doc, chat_id, model_id, prompt,
                on_text=on_text, on_think=on_think,
            )
        except ai.AiError as e:
            logger.exception(e.message)
            card = model.ChatCard(
                card_kind="error",
                text=e.message,
                actions=(
                    model.ChatCardAction(
                        id="retry", label="Retry", appearance="primary"
                    ),
                ) if e.retryable else ()
            )
        except Exception as e:
            logger.exception("assist run failed")
            card = model.ChatCard(
                card_kind="error",
                text=str(e) or type(e).__name__
            )

        if card is not None:
            items.append(card)

        turn = model.ChatTurn(id=turn_id, prompt=prompt, items=tuple(items))
        with doc.edit(self.ai) as ed:
            ed.apply(model.AppendChatTurn(chat_id, turn))

        if card is not None:
            fut = self.ui.assist.add_card(chat_id, card)
            fut.add_done_callback(card_action)
        self.ui.assist.end_turn(chat_id)

    async def set_trip_info(
        self, card_id: str, title: str, notes: str
    ) -> None:
        logger.debug(f"card_id:{card_id} title:{title!r} notes:{notes!r}")
        with self.doc.edit(self.api) as ed:
            ed.apply(model.SetDocInfo(title=title, notes=notes))

    async def add_route(self) -> None:
        logger.debug("")
        window = self.window
        if window is None:
            return
        files = await asyncio.to_thread(
            window.create_file_dialog,
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("GPX files (*.gpx)", "All files (*.*)"),
        )
        if not files:
            return

        self.ui.set_busy(True, "Loading routes...")
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
                    self._load_route_details(self.doc, r.id, r.track)
                except Exception as e:
                    logger.exception(f'Failed to load "{filepath}"')
                    name = pathlib.Path(filepath).name
                    self.ui.notify(
                        f"{name}: {e}",
                        intent="error",
                        title="Could not load route"
                    )
        finally:
            self.ui.set_busy(False)

    async def set_route_info(
        self, card_id: str, title: str, notes: str
    ) -> None:
        logger.debug(f"card_id:{card_id} title:{title!r} notes:{notes!r}")
        with self.doc.edit(self.api) as ed:
            ed.apply(model.SetRouteInfo(card_id, title=title, notes=notes))

    async def remove_route(self, card_id: str) -> None:
        logger.debug(f"card_id:{card_id}")
        with self.doc.edit(self.api) as ed:
            ed.apply(model.RemoveRoute(card_id))

    async def move_route(
        self, card_id: str, after_id: str | None = None
    ) -> None:
        logger.debug(f"card_id:{card_id} after_id:{after_id}")
        with self.doc.edit(self.api) as ed:
            ed.apply(model.MoveRoute(card_id, after_id))

    def _load_route_details(
        self, doc: model.Document, route_id: str,
        track: tuple[model.TrackPoint, ...]
    ) -> None:
        """Start loading a route's details and reflect it in the UI."""
        if not track:
            return
        self.ui.set_route_loading(route_id, True)
        fut = self.route_details.load_poi(track)

        def on_loaded(fut: Future[tuple[model.Poi, ...]]) -> None:
            try:
                if fut.cancelled():
                    return
                poi = fut.result()
                if doc is self.doc and doc.route(route_id):
                    with doc.edit(self) as ed:
                        ed.apply(model.SetRoutePoi(route_id, poi))
            except CancelledError:
                return # aborted while shutting down
            except Exception as e:
                logger.exception(f"route_id:{route_id} POI load failed")
                route = doc.route(route_id)
                name = route.title if route else route_id
                notify_fut = self.ui.notify(
                    f"{name}: {e}",
                    intent="error",
                    title="Could not load route details",
                    actions=[NotifyAction("Retry", result="retry")]
                )

                def retry(notify_fut: Future[Any]) -> None:
                    if notify_fut.cancelled():
                        return
                    if notify_fut.result() == "retry":
                        self._load_route_details(doc, route_id, track)
                notify_fut.add_done_callback(retry)
            finally:
                self.ui.set_route_loading(route_id, False)

        fut.add_done_callback(on_loaded)

    def on_change(self, change: model.Change, origin: model.Origin) -> None:
        if isinstance(change, model.AddRoute):
            track = change.route.track
            self.ui.add_route_card(
                change.route.id,
                change.route.title,
                change.route.notes,
                track,
                route.RouteStats.from_track(track) if track else None,
            )
        elif isinstance(change, model.SetDocInfo):
            if origin is not self.api:
                self.ui.set_trip_card(self.doc.title, self.doc.notes)
        elif isinstance(change, model.SetRouteInfo):
            if origin is not self.api:
                r = self.doc.route(change.route_id)
                if r is not None:
                    self.ui.set_route_card(r.id, r.title, r.notes)
        elif isinstance(change, model.RemoveRoute):
            if origin is not self.api:
                self.ui.remove_card(change.route_id)
        elif isinstance(change, model.MoveRoute):
            if origin is not self.api:
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
