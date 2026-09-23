import asyncio
import logging
import logging.handlers
import os
import platform
import sys
import threading
from argparse import ArgumentParser
from dataclasses import replace
from datetime import datetime

from native.app_host import PyWebViewAppHost

from . import APP_NAME, APP_VERSION
from backpack.app_host import AppHost
from backpack.core import Backpack
from backpack.paths import app_icon_path, app_settings_path, applogs, assets_dir
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
    parser.add_argument(
        "-d", "--debug", action="store_true",
        help="log at debug level and open the web view with dev tools",
    )
    args = parser.parse_args()

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
        level=logging.DEBUG if args.debug else logging.INFO,
        handlers=handlers
    )
    logging.getLogger("pywebview").handlers.clear()
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.ERROR)

    logger.info(
        f"Starting {APP_NAME} {APP_VERSION} ("
        f"{sys.platform}-{platform.machine().lower()} "
        f"python-{platform.python_version()} "
        f"frozen:{getattr(sys, 'frozen', False)})"
    )

    url = args.dev or str(assets_dir() / "index.html")
    logger.debug(f"url:{url}")

    if sys.platform == "win32":
        # Group the window under our own taskbar identity instead of
        # inheriting python.exe when running from source.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
    elif sys.platform == "darwin":
        # Override the identity inherited from the embedded Python.app so the
        # menu bar and cmd+tab switcher show Backpack, not Python, when running
        # from source.
        try:
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            info["CFBundleName"] = "Backpack"
        except Exception:
            logger.exception("could not set macOS app name")

    # The stdlib ssl module (http.client, urllib) has no usable trust store on
    # macOS, so it fails with CERTIFICATE_VERIFY_FAILED. certifi ships a bundle
    # and OpenSSL honors SSL_CERT_FILE when building the default context. This
    # is additive on Windows.
    try:
        import certifi
        ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca)
        logger.debug(f"TLS CA bundle: {ca}")
    except Exception:
        logger.exception("could not configure certifi CA bundle")

    storage = Storage()
    try:
        settings_path = app_settings_path()
        logger.debug(f'Loading settings from "{settings_path}"')
        storage.settings = storage.read_settings_file(settings_path)
    except (OSError, ValueError) as e:
        logger.warning(f"Could not read settings: {e}")

    host = PyWebViewAppHost(url, debug=args.debug, icon=app_icon_path())
    app = Backpack(host, storage)

    mainloop_th = threading.Thread(
        target=asyncio.run, name="app.mainloop", args=(_serve(host, app),)
    )
    mainloop_th.start()

    try:
        host.start()
    finally:
        mainloop_th.join()

        try:
            # Save last opened filepath to continue on next start
            storage.settings = replace(
                storage.settings, last_filepath=app.filepath
            )

            settings_path = app_settings_path()
            logger.debug(f'Storing settings to "{settings_path}"')
            storage.write_settings_file(settings_path)
        except OSError as e:
            logger.warning(f"Could not store settings: {e}")

        logger.info("Exit\n")


async def _serve(host: AppHost, app: Backpack) -> None:
    """Service the host events until the app close"""
    loaded = False
    try:
        while True:
            try:
                event = await asyncio.wrap_future(host.get_event())
            except asyncio.CancelledError:
                return
            try:
                if event.name == "load":
                    if loaded:
                        continue
                    loaded = True
                    await app.start()
                elif event.name == "close":
                    try:
                        closed = await app.close()
                    except Exception:
                        logger.exception("close failed")
                        closed = True  # close anyway on an unexpected error
                    if closed:
                        host.quit()
                        return
                else:
                    # ui called a backed routine
                    await app.dispatch(event.name, event.args)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception(f"{event.name!r} failed")
    finally:
        # a no-op after a close, the fallback when the GUI ended on its own
        app.teardown()


if __name__ == "__main__":
    main()
