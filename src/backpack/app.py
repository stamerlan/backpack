import asyncio
import logging
import webview

from backpack.api import Api

logger = logging.getLogger(__name__)


class App:
    def __init__(self, mainloop: asyncio.AbstractEventLoop) -> None:
        self.mainloop = mainloop
        self.window: webview.Window | None = None
        self.api = Api(self)

    def start(self, window: webview.Window) -> None:
        """Bind the window and start application tasks."""
        self.window = window
        logger.debug("app started")

    def shutdown(self) -> None:
        logger.debug("app shutting down")
        self.api.shutdown()

    async def new_doc(self) -> None:
        logger.debug("")

    async def open_doc(self, filepath: str | None = None) -> None:
        logger.debug(f"filepath:{filepath}")

    async def save_doc(
        self, filepath: str | None = None, show_dialog: bool = False
    ) -> None:
        logger.debug(f"filepath:{filepath} show_dialog:{show_dialog}")

    async def open_settings(self) -> None:
        logger.debug("")
