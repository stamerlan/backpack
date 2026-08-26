from __future__ import annotations

import logging
import logging.handlers
from argparse import ArgumentParser
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

    from core.app import App

# The import package is "core", but the product keeps the "backpack" identity:
# user data directories, the gettext domain and the distribution metadata are
# all named after it, so pin the name rather than deriving it from __name__.
APP_NAME = "backpack"

try:
    # Written at build/install time by hatch-vcs and holds the version derived
    # from git, including the short commit for dev builds.
    from ._version import __version__

    APP_VERSION = __version__
except ImportError:
    try:
        APP_VERSION = version(APP_NAME)
    except PackageNotFoundError:
        APP_VERSION = "0+unknown"

logger = logging.getLogger(APP_NAME)


class LogFormatter(logging.Formatter):
    def formatTime(
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:
        dt = datetime.fromtimestamp(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%H:%M:%S.%f")


def main(app: App) -> None:
    """Run Backpack on an App the platform layer has already built.

    Home for the durable run logic: initialize logging, wire Core to the App
    and run the asyncio loop to completion on the calling thread. The platform
    layer dedicates this thread to the core, one the pywebview entries spawn
    and the native host starts from C++, and runs its own GUI loop elsewhere.
    This call blocks until Core's lifecycle ends, then forces a teardown and
    persists exit state; returning is the host's cue to shut the application
    down. Heavy imports are deferred so importing the core package stays cheap.
    """
    import asyncio
    import os
    import platform
    import sys
    from dataclasses import replace

    from core.core import Core
    from core.paths import app_settings_path
    from core.storage import Storage

    _configure_logging()

    logger.info(
        f"Starting {APP_NAME} {APP_VERSION} ("
        f"{sys.platform}-{platform.machine().lower()} "
        f"python-{platform.python_version()} "
        f"frozen:{getattr(sys, 'frozen', False)})"
    )

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

    inst = Core(app, storage)

    # Core owns the run loop: it drives the whole lifecycle off the App event
    # stream (startup on load, shutdown then app.quit() on close) and returns
    # when that ends. core.main owns the asyncio loop, so run it here and block
    # on run() completing rather than run_forever.
    def on_run_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("app lifecycle failed", exc_info=exc)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run_task = loop.create_task(inst.run())
    run_task.add_done_callback(on_run_done)

    try:
        loop.run_until_complete(run_task)
    except BaseException:
        # run() was cancelled or failed; the teardown below still runs.
        pass
    finally:
        # A graceful close tore Core down already; force a teardown as a safety
        # net for an abnormal exit, then drain and close the loop.
        try:
            inst.shutdown(force=True)
        except Exception:
            logger.exception("forced shutdown failed")
        _drain(loop)
        try:
            # Save last opened filepath to continue on next start.
            storage.settings = replace(
                storage.settings, last_filepath=inst.filepath
            )
            storage.write_settings_file(app_settings_path())
        except OSError as e:
            logger.warning(f"Could not store settings: {e}")
        logger.info("Exit\n")


def _drain(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel pending tasks and close the loop after it has stopped."""
    import asyncio

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
        logger.debug("mainloop stopped")


def _configure_logging() -> None:
    from core.paths import applogs

    # Only the debug flag affects logging; ignore the rest so a host that adds
    # its own options (e.g. --dev) does not trip this parse.
    parser = ArgumentParser(add_help=False)
    parser.add_argument("-d", "--debug", action="store_true")
    args, _ = parser.parse_known_args()

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
