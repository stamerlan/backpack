"""MacOS application entry

Build the pywebview host, spawn the core thread that run core.main, drive the
GUI loop on the main thread.
"""

import logging
import threading
from argparse import ArgumentParser

import core
from app.macos.app import MacApp
from core import APP_NAME
from core.paths import app_icon_path, assets_dir

DEV_SERVER_URL = "http://localhost:5173"

logger = logging.getLogger(APP_NAME)


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
    app = MacApp(
        url, title="Backpack", width=1200, height=800,
        min_size=(800, 600), debug=args.debug, icon=app_icon_path(),
    )

    # core.main owns and runs the asyncio loop on this thread and blocks until
    # Core exits, then forces a teardown and persists exit state.
    core_th = threading.Thread(target=core.main, args=(app,), name="core.main")
    core_th.start()
    try:
        app.start()
    finally:
        core_th.join()


if __name__ == "__main__":
    main()
