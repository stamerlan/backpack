"""Application entry"""

import logging
import sys
import threading
from argparse import ArgumentParser

import backpack
from backpack import APP_NAME
from backpack.paths import app_icon_path, assets_dir
from native.app_host import PyWebViewAppHost

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

    if sys.platform == "win32":
        # Group the window under our own taskbar identity instead of
        # inheriting python.exe when running from source.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
    elif sys.platform == "darwin":
        # Override the identity inherited from the embedded Python.app so the
        # menu bar and cmd+tab switcher show Backpack, not Python, when run
        # from source.
        try:
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            info["CFBundleName"] = "Backpack"
        except Exception:
            logger.exception("could not set macOS app name")

    url = args.dev or str(assets_dir() / "index.html")
    app = PyWebViewAppHost(
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
