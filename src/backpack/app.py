import asyncio
import logging
import pathlib
import webview
from uuid import uuid4

from backpack import model, route
from backpack.api import Api
from backpack.js_worker import JsWorker
from backpack.storage import Storage
from backpack.ui import UI

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
        self.doc = model.Document()

    def start(self, window: webview.Window) -> None:
        """Bind the window and start application tasks."""
        self.window = window
        self.js.start(window)
        logger.debug("app started")

    def shutdown(self) -> None:
        logger.debug("app shutting down")
        self.api.shutdown()
        self.js.shutdown()

    async def on_loaded(self) -> None:
        await self.new_doc()

    async def new_doc(self) -> None:
        logger.debug("")
        doc = model.Document()
        doc.subscribe(self.on_change)
        self.doc = doc
        self.ui.clear_notify()
        self.ui.clear_doc()
        self.ui.add_trip_card(f"trip-{uuid4().hex}", doc.title, doc.notes)

    async def open_doc(self, filepath: str | None = None) -> None:
        logger.debug(f"filepath:{filepath}")

    async def save_doc(
        self, filepath: str | None = None, show_dialog: bool = False
    ) -> None:
        logger.debug(f"filepath:{filepath} show_dialog:{show_dialog}")

    async def open_settings(self) -> None:
        logger.debug("")

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
        elif isinstance(change, model.RemoveRoute):
            if origin is not self.api:
                self.ui.remove_card(change.route_id)
        elif isinstance(change, model.MoveRoute):
            if origin is not self.api:
                self.ui.move_card(change.route_id, change.after_id)
