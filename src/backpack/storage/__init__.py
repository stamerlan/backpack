import asyncio
import json
import logging
import os
from pathlib import Path

from backpack import paths
from .. import APP_NAME
from .settings import Settings
from .vault import Vault


logger = logging.getLogger(__name__)

class Storage:
    def __init__(self) -> None:
        self.settings = Settings()
        self.vault = Vault()

    async def load_settings(
        self, filepath: str | os.PathLike[str] | None = None
    ) -> Settings:
        self.settings = await asyncio.to_thread(
            self.read_settings_file, filepath
        )
        return self.settings

    async def save_settings(
        self, filepath: str | os.PathLike[str] | None = None
    ) -> None:
        await asyncio.to_thread(self.write_settings_file, filepath)

    async def load_key(self, key: str) -> str | None:
        value = await asyncio.to_thread(self.read_key_store, key)
        self.vault = self.vault.set(key, value)
        return value

    async def store_key(self, key: str, value: str | None) -> None:
        await asyncio.to_thread(self.write_key_store, key, value)
        self.vault = self.vault.set(key, value)

    def read_settings_file(
        self, filepath: str | os.PathLike[str] | None = None
    ) -> Settings:
        """Blocking: read settings from disk, defaults if absent.

        A missing file is a normal first run and yields defaults; any other
        error (unreadable, malformed JSON) is raised so the caller can handle
        it.
        """
        path = paths.app_settings_path() if filepath is None else Path(filepath)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Settings()
        return Settings.from_dict(json.loads(text))

    def write_settings_file(
            self, filepath: str | os.PathLike[str] | None = None
    ) -> None:
        """Blocking: write the current settings to disk."""
        path = paths.app_settings_path() if filepath is None else Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.settings.to_dict(), indent=2)
        path.write_text(text, encoding="utf-8")

    def read_key_store(self, key: str) -> str | None:
        """Blocking: read one key from the OS credential store.

        Returns None if there is no such key. Raises KeyringError if the store
        cannot be read.
        """
        import keyring
        return keyring.get_password(APP_NAME, key)

    def write_key_store(self, key: str, value: str | None) -> None:
        """Blocking: store or delete one key in the credential store.

        An empty value deletes the key, a no-op when nothing is stored.
        Raises KeyringError on any other failure.
        """
        import keyring
        import keyring.errors
        try:
            if value:
                keyring.set_password(APP_NAME, key, value)
            else:
                keyring.delete_password(APP_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass
