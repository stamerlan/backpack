import asyncio
import logging
import os
import platform
import sys
from dataclasses import replace

from backpack.app_host import AppHost
from backpack.app_info import APP_NAME, APP_VERSION
from backpack.core import Backpack
from backpack.paths import app_settings_path
from backpack.storage import Storage

logger = logging.getLogger(APP_NAME)


def main(app: AppHost) -> None:
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.ERROR)

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

    backpack = Backpack(app, storage)
    try:
        asyncio.run(_serve(app, backpack))
    finally:
        try:
            # Save last opened filepath to continue on next start
            storage.settings = replace(
                storage.settings, last_filepath=backpack.filepath
            )

            settings_path = app_settings_path()
            logger.debug(f'Storing settings to "{settings_path}"')
            storage.write_settings_file(settings_path)
        except OSError as e:
            logger.warning(f"Could not store settings: {e}")
        logger.info("Exit")


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
