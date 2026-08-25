"""Native OS and application interface"""

from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Protocol


class Window(Protocol):
    def hide(self) -> None: ...
    def set_title(self, title: str) -> None: ...
    def set_theme(self, mode: str) -> None:
        """Theme the native title bar (either"light", "dark" or "system")."""


@dataclass
class Event:
    name: str
    args: tuple[Any, ...]


class AppHost(Protocol):
    window: Window

    def quit(self) -> None:
        """Exit the application."""
        ...

    def exec_script(self, func: str, args: tuple[Any, ...]) -> Future[Any]:
        """Call a frontend function and return a future for its result.

        Outbound py2js bridge. Calls serialize: one is in flight at a time and
        the next starts when the prior settles, so the frontend sees them in
        submission order.
        """
        ...

    def get_event(self) -> "Future[Event]":
        """Return a future for the next inbound call.

        The future resolves with the next Event to be serviced, already
        resolved if one is queued. The future is cancelled on shutdown so the
        caller stops waiting.
        """
        ...

    def show_open_dialog(
        self,
        *,
        multiple: bool = False,
        filters: tuple[tuple[str, str], ...] = ()
    ) -> Future[Any]:
        """Show a native open dialog and return a future for the picks.

        The future resolves to the chosen path, a list of paths when multiple
        is set, or None when the dialog is dismissed. Each filter is a
        (name, spec) pair where spec is a ;-separated list of globs, e.g.
        ("Images", "*.png;*.jpg").
        """
        ...

    def show_save_dialog(
        self, *, filename: str = "", filters: tuple[tuple[str, str], ...] = ()
    ) -> Future[Any]:
        """Show a native save dialog and return a future for the path.

        The future resolves to the chosen path, or None when the dialog is
        dismissed. filters are (name, spec) pairs as in show_open_dialog.
        """
        ...
