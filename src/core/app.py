"""Native app interface.

The platform App owns the window, the web view and the application lifecycle. It
exchanges work with Core as thread-safe concurrent futures, so the App needs no
event loop of its own.
"""

from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Protocol


class WebView(Protocol):
    ...

class Window(Protocol):
    def hide(self) -> None: ...
    def set_title(self, title: str) -> None: ...


class App(Protocol):
    @dataclass
    class Event:
        name: str
        args: tuple[Any, ...]

    webview: WebView
    window: Window

    def quit(self) -> None:
        """Exit the application."""
        ...

    def js_call(self, func: str, args: tuple[Any, ...]) -> Future[Any]:
        """Call a frontend function and return a future for its result.

        Outbound py2js. Calls serialize: one is in flight at a time and the next
        starts when the prior settles, so the frontend sees them in
        submission order.
        """
        ...

    def get_event(self) -> "Future[Event]":
        """Return a future for the next inbound call.

        The future resolves with the next Event to be serviced, already resolved
        if one is queued. The future is cancelled on shutdown so the caller
        stops waiting.
        """
        ...

    def show_open_dialog(
        self, *, multiple: bool = False, filters: tuple[str, ...] = ()
    ) -> Future[Any]:
        """Show a native open dialog and return a future for the picks.

        The future resolves to the chosen path, a list of paths when multiple is
        set, or None when the dialog is dismissed.
        """
        ...

    def show_save_dialog(
        self, *, filename: str = "", filters: tuple[str, ...] = ()
    ) -> Future[Any]:
        """Show a native save dialog and return a future for the path.

        The future resolves to the chosen path, or None when the dialog is
        dismissed.
        """
        ...
