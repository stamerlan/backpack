"""MacOS application entry"""

import logging
import logging.handlers
import threading
from argparse import ArgumentParser
from datetime import datetime

import backpack
from backpack import APP_NAME
from backpack.paths import app_icon_path, applogs, assets_dir
from native.macos import MacAppHost

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


def _setup_logging(debug: bool) -> None:
    """Log to the console and the rotating backpack.log"""
    log_formatter = LogFormatter(
        "%(asctime)s %(name)s.%(funcName)s(): %(message)s"
    )
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(log_formatter)
    handlers: list[logging.Handler] = [log_handler]

    try:
        log_dir = applogs()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "backpack.log", maxBytes=1_000_000, backupCount=3,
            encoding="utf-8"
        )
        file_handler.setFormatter(log_formatter)
        handlers.append(file_handler)
    except OSError:
        # A read-only home must never block startup; keep stream-only.
        pass

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        handlers=handlers
    )
    # pywebview adds its own stream handler; keep only ours
    logging.getLogger("pywebview").handlers.clear()


def main() -> None:
    parser = ArgumentParser(prog=APP_NAME)
    parser.add_argument(
        "--dev", metavar="URL", nargs="?", const=DEV_SERVER_URL,
        help="load the UI from a Vite dev server instead of assets",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true",
        help="log at debug level and open the web view with dev tools",
    )
    args = parser.parse_args()
    _setup_logging(args.debug)

    # Override the identity inherited from the embedded Python.app so the menu
    # bar and cmd+tab switcher show Backpack, not Python, when run from source.
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        info["CFBundleName"] = "Backpack"
    except Exception:
        logger.exception("could not set macOS app name")

    url = args.dev or str(assets_dir() / "index.html")
    app = MacAppHost(
        url, title="Backpack", width=1200, height=800,
        min_size=(800, 600), debug=args.debug, icon=app_icon_path(),
    )

    # backpack.main owns and runs the asyncio loop on this thread and blocks
    # until Core exits, then forces a teardown and persists exit state.
    core_th = threading.Thread(
        target=backpack.main, args=(app,), name="backpack.main"
    )
    core_th.start()
    try:
        app.start()
    finally:
        core_th.join()


if __name__ == "__main__":
    main()
