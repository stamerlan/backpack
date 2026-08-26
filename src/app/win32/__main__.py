"""Windows application entry

Build the pywebview host, spawn the core thread that run core.main, drive the
GUI loop on the main thread.
"""

import sys
import threading
from argparse import ArgumentParser

import core
from app.win32.app import WinApp
from core import APP_NAME
from core.paths import app_icon_path, assets_dir

DEV_SERVER_URL = "http://localhost:5173"


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

    url = args.dev or str(assets_dir() / "index.html")
    app = WinApp(
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
