from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


_EMPTY: Mapping[str, str | None] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Vault:
    _keys: Mapping[str, str | None] = field(default=_EMPTY)

    def get(self, key: str) -> str | None:
        """Return the cached value for key, or None if unknown."""
        return self._keys.get(key)

    def has(self, key: str) -> bool:
        """Whether key was loaded, even if its value is None."""
        return key in self._keys

    def set(self, key: str, value: str | None) -> "Vault":
        """Return a copy with key set to value."""
        return Vault(MappingProxyType({**self._keys, key: value}))
