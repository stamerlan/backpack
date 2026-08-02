import asyncio
import logging
import webview
from uuid import uuid4

from backpack.api import Api
from backpack.js_worker import JsWorker
from backpack.ui import UI

logger = logging.getLogger(__name__)


class App:
    def __init__(self, mainloop: asyncio.AbstractEventLoop) -> None:
        self.mainloop = mainloop
        self.window: webview.Window | None = None
        self.api = Api(self)
        self.js = JsWorker()
        self.ui = UI(self.js)

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
        self.ui.clear_doc()
        self.ui.add_trip_card(f"trip-{uuid4().hex}")

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
