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
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import asdict, is_dataclass
from typing import Any, Protocol

from backpack import app_host

logger = logging.getLogger(__name__)


class WebView(Protocol):
    def close(self) -> None: ...


class EventQueue(Protocol):
    def get(self, cb: Callable[[str], None]) -> bool: ...


class ScriptQueue(Protocol):
    def exec_script(
        self, script: str, cb: Callable[[int, str], None]
    ) -> bool: ...


class JsError(Exception):
    """A frontend function rejected or threw"""


def encode(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(
        f"Object of type {obj.__class__.__name__} is not JSON serializable"
    )


class _Call:
    """One outbound frontend call plus the context to debug a later failure.

    The submitting thread name and stack are captured so an error settled from
    a native callback can be traced back to the original call site.
    """

    __slots__ = ("expr", "caller_th", "caller_stack")

    def __init__(self, expr: str) -> None:
        self.expr = expr
        self.caller_th = threading.current_thread().name
        # drop the __init__ frame
        self.caller_stack = "".join(traceback.format_stack()[:-1])

    def annotate(self, exc: BaseException) -> None:
        """Attach frontend and caller context to exc as notes."""
        if isinstance(exc, JsError):
            detail = exc.args[0] if exc.args else None
            if not isinstance(detail, dict):
                exc.add_note(f"Frontend error: {detail}")
            else:
                name = detail.get("name", "Error")
                message = detail.get("message", "")
                head = f"{name}: {message}" if message else name
                stack = detail.get("stack")
                if stack:
                    exc.add_note(f"Frontend error: {head}\n{stack}")
                else:
                    exc.add_note(f"Frontend error: {head}")
        exc.add_note(f"Thread {self.caller_th!r}:\n{self.caller_stack}")


class WinAppHost:
    """App host backed by the native window, webview and queue objects.

    The native launcher injects one object per native class - the window, the
    webview, the inbound event queue and the outbound script queue - each
    exposing its own methods. This host encodes outbound calls for the script
    queue, drives the window, and settles every call as a concurrent future
    Core bridges onto its loop. It keeps no event loop of its own.
    """

    def __init__(
        self,
        window: app_host.Window,
        webview: WebView,
        event_q: EventQueue,
        script_q: ScriptQueue,
    ) -> None:
        self._webview = webview
        self._events = event_q
        self._scripts = script_q
        self.window = window

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
        fut = Future[Any]()
        try:
            params = ", ".join(json.dumps(a, default=encode) for a in args)
        except Exception as exc:
            fut.set_exception(exc)
            return fut
        call = _Call(f"{func}({params})")

        def on_done(status: int, payload: str) -> None:
            # Settled from the script queue when the call completes. status 0
            # carries the raw JSON result - a value, or a
            # pywebviewJavascriptError420 object on a throw; anything else means
            # the call did not run (aborted or webview gone).
            if fut.done():
                return
            if status != 0:
                fut.cancel()
                return
            result = json.loads(payload) if payload else None
            if isinstance(result, dict) and result.get(
                "pywebviewJavascriptError420"
            ):
                del result["pywebviewJavascriptError420"]
                exc = JsError(result)
                call.annotate(exc)
                logger.error(f"call failed: {call.expr}")
                fut.set_exception(exc)
            else:
                fut.set_result(result)

        if not self._scripts.exec_script(call.expr, on_done):
            fut.cancel()  # queue aborted; stop the caller waiting
        return fut
