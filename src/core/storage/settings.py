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
        """A recently opened document, as listed in the menu.

        Stores the raw route count, not a baked summary, so the view can
        format and re-translate the meta line on a language switch.
        """

        title: str
        routes: int             # number of routes in the document
        filepath: str

    theme: str = "system"       # "system" | "light" | "dark"
    locale: str = "system"      # "system" or a tag, e.g. "en-US", "ru"
    units: str = "auto"         # "auto" | "metric" | "imperial"
    recent: tuple[RecentItem, ...] = ()
    last_filepath: str | None = None  # restored on next launch

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
                    routes=int(r["routes"]),
                    filepath=str(r["filepath"]),
                ))
            except (KeyError, TypeError):
                pass # drop a malformed entry, keep the rest
        lf = d.get("last_filepath")
        return cls(
            theme=_get(d, "theme", defaults.theme),
            locale=_get(d, "locale", defaults.locale),
            units=_get(d, "units", defaults.units),
            recent=tuple(recent[:MAX_RECENT_CNT]),
            last_filepath=lf if isinstance(lf, str) else None,
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
