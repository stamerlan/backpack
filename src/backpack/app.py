import asyncio
import logging
import webview

logger = logging.getLogger(__name__)


class App:
    def __init__(self, mainloop: asyncio.AbstractEventLoop) -> None:
        self.mainloop = mainloop
        self.window: webview.Window | None = None

    def start(self, window: webview.Window) -> None:
        """Bind the window and start application tasks."""
        self.window = window
        logger.debug("app started")

    def shutdown(self) -> None:
        logger.debug("app shutting down")
