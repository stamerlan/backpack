"""Persistent application settings.

An immutable snapshot of application configuration that is stored on disk. The
value owns no lock and performs no I/O. A change builds a new value, either with
dataclasses.replace for a plain field or with the helpers below.
"""
from dataclasses import asdict, dataclass, replace
from typing import Any, TypeVar


T = TypeVar("T")
MAX_RECENT_CNT = 10


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything Backpack keeps on disk, minus secrets."""

    @dataclass(frozen=True, slots=True)
    class RecentItem:
        """A recently opened document, as listed in the menu."""

        title: str
        meta: str               # short summary, e.g. "3 routes"
        filepath: str

    theme: str = "system"       # "system" | "light" | "dark"
    recent: tuple[RecentItem, ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Settings":
        """Build from parsed JSON, falling back to defaults per field.

        Nothing here raises: a settings file is not worth failing a startup.
        A field of the wrong type is replaced by its default and a malformed
        recent entry is dropped.
        """
        defaults = cls()
        recent = list[Settings.RecentItem]()
        for r in d.get("recent", []):
            try:
                recent.append(cls.RecentItem(
                    title=str(r["title"]),
                    meta=str(r["meta"]),
                    filepath=str(r["filepath"]),
                ))
            except (KeyError, TypeError):
                pass # drop a malformed entry, keep the rest
        return cls(
            theme=_get(d, "theme", defaults.theme),
            recent=tuple(recent[:MAX_RECENT_CNT]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def add_recent(self, item: "Settings.RecentItem") -> "Settings":
        """Return a copy with item first, deduplicated by filepath."""
        rest = tuple(r for r in self.recent if r.filepath != item.filepath)
        return replace(self, recent=(item,) + rest[:MAX_RECENT_CNT - 1])

    def remove_recent(self, filepath: str) -> "Settings":
        """Return a copy without the entry for filepath."""
        return replace(self, recent=tuple(
            r for r in self.recent if r.filepath != filepath
        ))


def _get(d: dict[str, Any], key: str, default: T) -> T:
    """Read a value of the same type as default, or return default."""
    value = d.get(key, default)
    return value if isinstance(value, type(default)) else default
