import asyncio
import logging
import sys
import threading
import webview
from argparse import ArgumentParser
from datetime import datetime

from . import APP_NAME
from backpack.app import App
from backpack.paths import app_icon_path, app_settings_path, assets_dir
from backpack.storage import Storage


DEV_SERVER_URL = "http://localhost:5173"

logger = logging.getLogger(APP_NAME)


class LogFormatter(logging.Formatter):
    def formatTime(
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:
        dt = datetime.fromtimestamp(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%H:%M:%S.%f")


def main() -> None:
    parser = ArgumentParser(prog=APP_NAME)
    parser.add_argument(
        "--dev", metavar="URL", nargs="?", const=DEV_SERVER_URL,
        help="load the UI from a Vite dev server instead of assets",
    )
    args = parser.parse_args()

    log_handler = logging.StreamHandler()
    log_handler.setFormatter(
        LogFormatter("%(asctime)s %(name)s.%(funcName)s(): %(message)s")
    )
    logging.basicConfig(level=logging.DEBUG, handlers=[log_handler])
    logging.getLogger("pywebview").handlers.clear()

    url = args.dev or str(assets_dir() / "index.html")
    logger.debug(f"url:{url}")

    if sys.platform == "win32":
        # Group the window under our own taskbar identity instead of
        # inheriting python.exe when running from source.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)

    storage = Storage()
    try:
        settings_path = app_settings_path()
        logger.debug(f'Loading settings from "{settings_path}"')
        storage.settings = storage.read_settings_file(settings_path)
    except (OSError, ValueError) as e:
        logger.warning(f"Could not read settings: {e}")

    mainloop = asyncio.new_event_loop()
    mainloop_th = threading.Thread(
        target=_run_mainloop, name="app.mainloop", args=(mainloop,)
    )
    mainloop_th.start()

    app = App(mainloop, storage)

    try:
        window = webview.create_window(
            "Backpack", url, js_api=app.api,
            width=1200, height=800, min_size=(800, 600)
        )
        assert window is not None
        webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False

        app.start(window)
        # Finish app work before pywebview tears the window down; the event
        # runs synchronously and defers the close until shutdown returns.
        window.events.closing += app.shutdown
        window.events.loaded += lambda *_: asyncio.run_coroutine_threadsafe(
            app.on_loaded(), mainloop
        )

        webview.start(
            debug=logger.isEnabledFor(logging.DEBUG),
            icon=app_icon_path(),
        )
    finally:
        app.shutdown()
        mainloop.call_soon_threadsafe(mainloop.stop)
        mainloop_th.join()

        try:
            settings_path = app_settings_path()
            logger.debug(f'Storing settings to "{settings_path}"')
            storage.write_settings_file(settings_path)
        except OSError as e:
            logger.warning(f"Could not store settings: {e}")

        logger.debug("exit")


def _run_mainloop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        try:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(
                    asyncio.gather(*tasks, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
            logger.debug("app.mainloop stopped")


if __name__ == "__main__":
    main()
