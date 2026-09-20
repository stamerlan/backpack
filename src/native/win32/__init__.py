"""Windows app host over the native window, webview and queue objects.

The native backpack.exe owns the window, the WebView2 control and the message
loop. It injects Python objects for the window, the webview, the inbound event
queue and the outbound script queue - each a native type exposing its own
methods (see py::to_object() in py/object.h) - and this host drives them into
the AppHost interface Core expects. Each call settles a concurrent future Core
bridges onto its loop, so this host keeps no event loop of its own.

Every operation runs directly on an injected object, so this package imports no
native module and stays importable elsewhere (tests, tooling); a caller passes
the collaborators in, real or fake.
"""

import json
import logging
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, Protocol

from backpack import app_host
from native.js import JsCall

logger = logging.getLogger(__name__)


DialogCallback = Callable[[int, bool, list[str]], None]


class Window(app_host.Window, Protocol):
    def show_open_dialog(
        self, multiple: bool, filters: list[tuple[str, str]],
        cb: DialogCallback,
    ) -> None: ...

    def show_save_dialog(
        self, filename: str, filters: list[tuple[str, str]],
        cb: DialogCallback,
    ) -> None: ...


class WebView(Protocol):
    def close(self) -> None: ...


class EventQueue(Protocol):
    def get(self, cb: Callable[[str], None]) -> bool: ...


class ScriptQueue(Protocol):
    def exec_script(
        self, script: str, cb: Callable[[int, str], None]
    ) -> bool: ...


class WinAppHost:
    """App host backed by the native window, webview and queue objects.

    The native launcher injects one object per native class - the window, the
    webview, the inbound event queue and the outbound script queue - each
    exposing its own methods. This host encodes outbound calls for the script
    queue, drives the window and its dialogs, and settles every call as a
    concurrent future Core bridges onto its loop. It keeps no event loop of its
    own.
    """

    def __init__(
        self,
        window: Window,
        webview: WebView,
        event_q: EventQueue,
        script_q: ScriptQueue,
    ) -> None:
        self._window = window
        self._webview = webview
        self._events = event_q
        self._scripts = script_q
        self.window: app_host.Window = window

    def quit(self) -> None:
        """Exit the application"""
        self._webview.close()

    def get_event(self) -> Future[app_host.Event]:
        """Return a future for the next inbound frontend or OS event."""
        fut = Future[app_host.Event]()

        def on_event(event_json: str) -> None:
            # Runs on the native UI thread, or inline here when an event is
            # already queued. Settling the concurrent future is thread safe.
            # An empty event means the queue was aborted (the GUI is gone).
            if fut.done():
                return
            if not event_json:
                fut.cancel()
                return
            try:
                doc = json.loads(event_json)
                name = doc["name"]
                raw = doc.get("args") or []
                fut.set_result(app_host.Event(name, tuple(raw)))
            except Exception as exc:
                logger.exception(f"bad event payload: {event_json!r}")
                fut.set_exception(exc)

        if not self._events.get(on_event):
            fut.cancel()  # bridge is down; stop the caller waiting
        return fut

    def exec_script(self, func: str, args: tuple[Any, ...]) -> Future[Any]:
        """Call a frontend function and return a future for its result.

        The call is queued on the native script queue and run through the
        webview one at a time, so the frontend sees calls in submission order.
        The queue wraps each call so a JS throw comes back as an error object.
        """
        call = JsCall(func, args)
        if call.fut.done():
            return call.fut

        def on_done(status: int, payload: str) -> None:
            # Settled from the script queue when the call completes. status 0
            # carries the raw JSON result - a value, or a
            # pywebviewJavascriptError420 object on a throw; 1 means the call
            # was aborted (the webview is gone) and 2 that it failed to run.
            if status == 1:
                call.fut.cancel()
                return
            if status != 0:
                call.set_exception(RuntimeError("script failed to run"))
                return
            try:
                result = json.loads(payload) if payload else None
            except Exception as exc:
                call.set_exception(exc)
                return
            call.set_result(result)

        if not self._scripts.exec_script(call.expr, on_done):
            call.fut.cancel()  # queue aborted; stop the caller waiting
        return call.fut

    def show_open_dialog(
        self,
        *,
        multiple: bool = False,
        filters: tuple[tuple[str, str], ...] = (),
    ) -> Future[Any]:
        """Show a native open dialog and return a future for the picks.

        Resolves to the chosen path, a list of paths when multiple is set, or
        None when the dialog is dismissed. Each filter is a (name, spec) pair,
        e.g. ("Json files", "*.json").
        """
        fut = Future[Any]()

        def on_done(
            status: int, cancelled: bool, paths: list[str]
        ) -> None:
            if fut.done():
                return
            if status == 1:
                fut.cancel()
            elif status == 2:
                fut.set_exception(OSError("file dialog failed"))
            elif cancelled or not paths:
                fut.set_result(None)
            elif multiple:
                fut.set_result(list(paths))
            else:
                fut.set_result(paths[0])

        self._window.show_open_dialog(multiple, list(filters), on_done)
        return fut

    def show_save_dialog(
        self,
        *,
        filename: str = "",
        filters: tuple[tuple[str, str], ...] = (),
    ) -> Future[Any]:
        """Show a native save dialog and return a future for the path.

        Resolves to the chosen path, or None when the dialog is dismissed. Each
        filter is a (name, spec) pair, e.g. ("Json files", "*.json").
        """
        fut = Future[Any]()

        def on_done(
            status: int, cancelled: bool, paths: list[str]
        ) -> None:
            if fut.done():
                return
            if status == 1:
                fut.cancel()
            elif status == 2:
                fut.set_exception(OSError("file dialog failed"))
            elif cancelled or not paths:
                fut.set_result(None)
            else:
                fut.set_result(paths[0])

        self._window.show_save_dialog(filename, list(filters), on_done)
        return fut
