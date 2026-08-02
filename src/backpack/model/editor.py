"""Editor: the only handle through which the document is modified.

An Editor is obtained from Document.edit(origin) and used as a context manager.
It binds the origin of the edit, holds the document lock for the duration of the
block and applies changes immediately, while their notifications are buffered
and delivered once the block exits cleanly.
"""
from types import TracebackType
from typing import TYPE_CHECKING, Literal
from .change import Change

if TYPE_CHECKING:
    from .document import Document


Origin = object
"""Opaque edit source. Only identity matters; the model never dereferences
it. A UI widget passes ``self``; a service passes its own instance.

In future it may become a Protocol, for example each origin has label.
"""


class Editor:
    __slots__ = ("doc", "origin")

    def __init__(self, doc: "Document", origin: Origin) -> None:
        self.doc = doc
        self.origin = origin

    def __enter__(self) -> "Editor":
        self.doc._begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        self.doc._end(aborted=exc_type is not None)
        return False  # never swallow exceptions

    def apply(self, change: Change) -> None:
        """Apply one change now and buffer its notification."""
        self.doc._apply(change, self.origin)
