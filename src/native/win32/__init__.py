"""Windows app host over the native window, webview and queue objects.

The native backpack.exe owns the window, the WebView2 control and the message
loop. It injects Python objects for the window, the webview, the inbound event
queue and the outbound script queue - each a native type wrapping a C++ class,
and this host drives them into the AppHost interface Core expects. Each call
settles a concurrent future Core bridges onto its loop, so this host keeps no
event loop of its own.

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

# HRESULT values the native callbacks report, as unsigned ints
E_ABORT = 0x80004004
E_CANCELLED = 0x800704C7  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
FAILED_BIT = 0x80000000


class Window(Protocol):
    """native.win32.Window over the C++ window_t"""

    def set_title(self, title: str) -> None: ...
    def set_theme(self, mode: str) -> None: ...

    def show_open_dialog(
        self, multiple: bool, filters: list[tuple[str, str]],
        cb: Callable[[int, list[str]], None]
    ) -> None: ...

    def show_save_dialog(
        self, filename: str, filters: list[tuple[str, str]],
        cb: Callable[[int, list[str]], None]
    ) -> None: ...


class WebView(Protocol):
    """native.win32.WebView over the C++ webview_t"""

    def close(self) -> None: ...


class EventQueue(Protocol):
    """native.win32.EventQueue over the C++ event_queue_t"""

    def get(self, cb: Callable[[str], None]) -> bool: ...


class ScriptQueue(Protocol):
    """native.win32.ScriptQueue over the C++ script_queue_t"""

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

    def quit(self) -> None:
        """Exit the application"""
        self._webview.close()

    def set_title(self, title: str) -> None:
        self._window.set_title(title)

    def set_theme(self, mode: str) -> None:
        self._window.set_theme(mode)

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

        def on_done(hresult: int, payload: str) -> None:
            # Settled from the script queue when the call completes. Success
            # carries the raw JSON result - a value, or a
            # pywebviewJavascriptError420 object on a throw; E_ABORT means
            # the call was aborted (the webview is gone).
            if hresult == E_ABORT:
                call.fut.cancel()
                return
            if hresult & FAILED_BIT:
                call.set_exception(
                    OSError(0, "script failed to run", None, hresult))
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
        fut = Future[Any]()

        def on_done(hresult: int, paths: list[str]) -> None:
            if fut.done():
                return
            if hresult == E_ABORT:
                fut.cancel()
            elif hresult & FAILED_BIT and hresult != E_CANCELLED:
                fut.set_exception(
                    OSError(0, "file dialog failed", None, hresult)
                )
            elif not paths:
                fut.set_result(None)
            elif multiple:
                fut.set_result(list(paths))
            else:
                fut.set_result(paths[0])

        self._window.show_open_dialog(multiple, list(filters), on_done)
        return fut

    def show_save_dialog(
        self, *, filename: str = "", filters: tuple[tuple[str, str], ...] = ()
    ) -> Future[Any]:
        fut = Future[Any]()

        def on_done(hresult: int, paths: list[str]) -> None:
            if fut.done():
                return
            if hresult == E_ABORT:
                fut.cancel()
            elif hresult & FAILED_BIT and hresult != E_CANCELLED:
                fut.set_exception(
                    OSError(0, "file dialog failed", None, hresult)
                )
            elif not paths:
                fut.set_result(None)
            else:
                fut.set_result(paths[0])

        self._window.show_save_dialog(filename, list(filters), on_done)
        return fut
