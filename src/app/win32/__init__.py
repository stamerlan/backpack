"""Windows App host over the native _app extension (WebView2).

The native backpack.exe owns the window, the WebView2 control and the message
loop. This host wraps the primitives _app exposes into the App interface Core
drives: get_event and js_call, the file dialogs, the window operations and
quit. Each call crosses into native code and settles a concurrent future that
Core bridges onto its loop, so this host keeps no event loop of its own.

_app is the builtin extension the native backpack.exe registers, so it only
exists inside that process. It is imported lazily inside the methods that use
it, keeping this package importable elsewhere (tests, tooling) where the
extension is absent.
"""

import json
import logging
import threading
import traceback
from concurrent.futures import Future
from dataclasses import asdict, is_dataclass
from typing import Any

from core import app

logger = logging.getLogger(__name__)


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


class Window:
    """Native window operations, forwarded to the UI thread by _app."""

    def hide(self) -> None:
        import _app
        _app.hide()

    def set_title(self, title: str) -> None:
        import _app
        _app.set_title(title)

    def set_theme(self, mode: str) -> None:
        import _app
        _app.set_theme(mode)


class WebView:
    """Placeholder web view: Core reaches the frontend through js_call."""


class WinApp:
    """App host backed by the native window and WebView2 via _app."""

    def __init__(self) -> None:
        self.window: app.Window = Window()
        self.webview: app.WebView = WebView()
        # Track outstanding futures so the GUI can fail them on an abnormal
        # exit (see _abort), letting core.main unwind instead of hanging.
        self._lock = threading.Lock()
        self._event_fut: "Future[app.App.Event] | None" = None
        self._js_futs: set["Future[Any]"] = set()
        self._dialog_futs: set["Future[Any]"] = set()

    def quit(self) -> None:
        """Exit the application by tearing the native window down."""
        import _app
        _app.quit()

    def get_event(self) -> "Future[app.App.Event]":
        """Return a future for the next inbound frontend or OS event."""
        import _app
        fut: "Future[app.App.Event]" = Future()
        with self._lock:
            self._event_fut = fut

        def on_event(event_json: str) -> None:
            # Runs on the native UI thread, or inline here when an event is
            # already queued. Settling the concurrent future is thread safe.
            if fut.done():
                return
            try:
                doc = json.loads(event_json)
                name = doc["name"]
                raw = doc.get("args") or []
                fut.set_result(app.App.Event(name, tuple(raw)))
            except Exception as exc:
                logger.exception(f"bad event payload: {event_json!r}")
                fut.set_exception(exc)

        if not _app.get_event(on_event):
            fut.cancel()  # bridge is down; stop the caller waiting
        return fut

    def js_call(self, func: str, args: tuple[Any, ...]) -> "Future[Any]":
        """Call a frontend function and return a future for its result.

        The native side serializes calls, one in flight at a time, so the
        frontend sees them in submission order.
        """
        import _app
        fut: "Future[Any]" = Future()
        try:
            params = ", ".join(json.dumps(a, default=encode) for a in args)
        except Exception as exc:
            fut.set_exception(exc)
            return fut
        call = _Call(f"{func}({params})")

        with self._lock:
            self._js_futs.add(fut)
        fut.add_done_callback(self._discard_js)

        def on_done(status: int, payload: str) -> None:
            # Settled from a WebView2 completion on the UI thread. status 0
            # carries the raw JSON result - a value, or a
            # pywebviewJavascriptError420 object on a throw; 2 means the call
            # did not run (webview gone).
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

        _app.js_call(call.expr, on_done)
        return fut

    def show_open_dialog(
        self,
        *,
        multiple: bool = False,
        filters: tuple[tuple[str, str], ...] = (),
    ) -> "Future[Any]":
        """Show a native open dialog and return a future for the picks.

        Resolves to the chosen path, a list of paths when multiple is set, or
        None when the dialog is dismissed. Each filter is a (name, spec) pair,
        e.g. ("Json files", "*.json").
        """
        import _app
        fut: "Future[Any]" = Future()
        with self._lock:
            self._dialog_futs.add(fut)
        fut.add_done_callback(self._discard_dialog)

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

        _app.show_open_dialog(multiple, list(filters), on_done)
        return fut

    def show_save_dialog(
        self,
        *,
        filename: str = "",
        filters: tuple[tuple[str, str], ...] = (),
    ) -> "Future[Any]":
        """Show a native save dialog and return a future for the path.

        Resolves to the chosen path, or None when the dialog is dismissed. Each
        filter is a (name, spec) pair, e.g. ("Json files", "*.json").
        """
        import _app
        fut: "Future[Any]" = Future()
        with self._lock:
            self._dialog_futs.add(fut)
        fut.add_done_callback(self._discard_dialog)

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

        _app.show_save_dialog(filename, list(filters), on_done)
        return fut

    def _abort(self) -> None:
        """Fail every outstanding future so a stalled Core unwinds.

        Called from the native side once the GUI loop ends. Any pending event
        wait, in-flight js_call or open dialog is cancelled so core.main stops
        waiting on a result the departed GUI can no longer deliver. A normal
        shutdown has nothing outstanding, so this is then a no-op.
        """
        with self._lock:
            event_fut = self._event_fut
            js = list(self._js_futs)
            dialogs = list(self._dialog_futs)
        # Cancel outside the lock: a done callback re-enters _discard_* which
        # takes the same non-reentrant lock.
        if event_fut is not None and not event_fut.done():
            event_fut.cancel()
        for f in js:
            if not f.done():
                f.cancel()
        for f in dialogs:
            if not f.done():
                f.cancel()

    def _discard_js(self, fut: "Future[Any]") -> None:
        with self._lock:
            self._js_futs.discard(fut)

    def _discard_dialog(self, fut: "Future[Any]") -> None:
        with self._lock:
            self._dialog_futs.discard(fut)
