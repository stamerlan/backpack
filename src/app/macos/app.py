"""macOS App host built on pywebview (WKWebView)"""

import json
import logging
import queue
import threading
import traceback
from collections import deque
from concurrent.futures import Future
from dataclasses import asdict, is_dataclass
from textwrap import dedent
from typing import Any

import webview

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


def wrap_call(call_expr: str) -> str:
    """Wrap a frontend call so evaluate_js returns without waiting.

    The call is wrapped in a promise so injection returns right away and a
    result still arrives for a synchronous function.
    """
    return dedent("""\
    (function js_call_wrapper() {
        var exception_to_error = function (e) {
            var err = {
                name: e && e.name,
                pywebviewJavascriptError420: true
            };
            if (e) Object.getOwnPropertyNames(e).forEach(function (k) {
                err[k] = e[k];
            });
            return err;
        };
        var undefined_to_null = function (v) {
            return v === undefined ? null : v;
        };
        try {
            return Promise.resolve(%s)
                .catch(exception_to_error)
                .then(undefined_to_null);
        } catch (e) {
            return Promise.resolve(exception_to_error(e));
        }
    })()
    """ % call_expr)


class JsCall:
    """A queued frontend call plus the context to run and debug it.

    str() is the expression handed to the wrapper. The submitting thread name
    and stack are captured so a later failure can be traced back to the original
    call site.
    """

    __slots__ = ("fn", "args", "fut", "caller_th", "caller_stack")

    def __init__(self, fn: str, args: str, fut: Future[Any]) -> None:
        self.fn = fn
        self.args = args
        self.fut = fut
        self.caller_th = threading.current_thread().name
        # drop the __init__ frame
        self.caller_stack = "".join(traceback.format_stack()[:-1])

    def __str__(self) -> str:
        return f"{self.fn}({self.args})"

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


class WebView:
    """Runs scripts in the web view."""

    def __init__(self, window: webview.Window) -> None:
        self._window = window

    def eval_js(self, script: str) -> Future[Any]:
        fut: Future[Any] = Future()

        def cb(raw: Any) -> None:
            # pywebview delivers off the GUI thread; the concurrent future is
            # safe to settle from there.
            if not fut.done():
                fut.set_result(raw)

        self._window.evaluate_js(script, cb)
        return fut


class Js:
    """Host py2js bridge: a worker thread serializing calls to the frontend.

    call() queues one outbound call and returns its concurrent future. A
    dedicated thread consumes the queue and runs each through the web view,
    blocking on its result so the next starts only when the prior settles; no
    event loop is used. shutdown() stops the thread and cancels anything still
    queued so awaiting callers fail fast.
    """

    def __init__(self, webview: WebView) -> None:
        self._webview = webview
        self._wq: queue.Queue[JsCall | None] = queue.Queue()
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="app.js", daemon=True
        )
        self._thread.start()

    def call(self, func: str, args: tuple[Any, ...]) -> Future[Any]:
        """Queue a frontend function call and return its future.

        The concurrent future is settled by the worker thread and bridged onto
        Core's loop by the caller. After shutdown the future is cancelled so
        callers fail fast.
        """
        fut: Future[Any] = Future()
        try:
            params = ", ".join(json.dumps(a, default=encode) for a in args)
        except Exception as exc:
            fut.set_exception(exc)
            return fut
        with self._lock:
            if not self._running:
                fut.cancel()
                return fut
            self._wq.put(JsCall(func, params, fut))
        return fut

    def shutdown(self) -> None:
        """Stop the worker and cancel anything still queued."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            while True:
                try:
                    job = self._wq.get_nowait()
                except queue.Empty:
                    break
                if job is not None and not job.fut.done():
                    job.fut.cancel()
            self._wq.put(None)  # stop the worker

    def _run(self) -> None:
        """Consume the work queue on the worker thread until shutdown."""
        while True:
            job = self._wq.get()
            if job is None:
                break

            try:
                result = self._webview.eval_js(wrap_call(str(job))).result()
            except Exception as exc:
                job.annotate(exc)
                logger.exception(f"call failed: {job}")
                if not job.fut.done():
                    job.fut.set_exception(exc)
            else:
                if not job.fut.done():
                    if (isinstance(result, dict) and
                        result.get("pywebviewJavascriptError420")
                    ):
                        # pywebview returns a dictionary with the key in case
                        # js code threw an exception
                        del result["pywebviewJavascriptError420"]
                        js_exc = JsError(result)
                        job.annotate(js_exc)
                        job.fut.set_exception(js_exc)
                    else:
                        job.fut.set_result(result)


class Events:
    """Inbound event queue: js2py calls and OS events, drained by Core.

    post() enqueues one event from any thread (a pywebview worker for js2py,
    the GUI thread for window load/close) and hands it to a waiting get_event(),
    or queues it until one asks; it returns False once shut down so the caller
    can react. get_event() returns a concurrent future for the next event that
    Core drives on its loop. A lock guards the queue and the single pending
    waiter, so no event loop is involved. shutdown() cancels the waiter and
    drops the queue so Core stops waiting.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: deque[app.App.Event] = deque()
        self._waiter: Future[app.App.Event] | None = None
        self._running = True

    def post(self, name: str, args: tuple[Any, ...]) -> bool:
        """Enqueue one event; return False if the bridge is shut down."""
        with self._lock:
            if not self._running:
                return False
            event = app.App.Event(name, args)
            if self._waiter is not None and not self._waiter.done():
                waiter, self._waiter = self._waiter, None
                waiter.set_result(event)
            else:
                self._pending.append(event)
            return True

    def get_event(self) -> "Future[app.App.Event]":
        """Return a future for the next event, resolved if one is queued."""
        with self._lock:
            fut: Future[app.App.Event] = Future()
            if not self._running:
                fut.cancel()
            elif self._pending:
                fut.set_result(self._pending.popleft())
            else:
                self._waiter = fut
            return fut

    def shutdown(self) -> None:
        """Cancel the waiter and drop any queued events."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            if self._waiter is not None and not self._waiter.done():
                self._waiter.cancel()
            self._waiter = None
            self._pending.clear()


class Window:
    def __init__(self, window: webview.Window) -> None:
        self._window = window

    def hide(self) -> None:
        self._window.hide()

    def set_title(self, title: str) -> None:
        self._window.title = title


class JsApi:
    """pywebview js_api object exposing a single dispatch entry point.

    pywebview publishes every public method as window.pywebview.api.*, so only
    dispatch is public. It runs on a pywebview worker thread and posts the call
    as an event for Core to service, then returns at once: js2py is
    fire-and-forget, so the worker never blocks and no result flows back.
    """

    def __init__(self, events: Events) -> None:
        self._events = events

    def dispatch(self, name: str, *args: Any) -> None:
        self._events.post(name, tuple(args))


def fut_resolve(fut: Future[Any] | None, res: Any) -> None:
    if fut is not None and not fut.done():
        fut.set_result(res)


def fut_exception(fut: Future[Any] | None, exc: BaseException) -> None:
    if fut is not None and not fut.done():
        fut.set_exception(exc)


class MacApp:
    def __init__(
        self,
        url: str,
        *,
        title: str = "Backpack",
        width: int = 1200,
        height: int = 800,
        min_size: tuple[int, int] = (800, 600),
        debug: bool = False,
        icon: str | None = None
    ) -> None:
        self._debug = debug
        self._icon = icon

        # The py2js and js2py bridges are host-owned and reached by Core through
        # js_call and get_event; both settle work as concurrent futures, so the
        # host keeps no event loop. window load/close are posted as events too,
        # so Core drives the whole lifecycle off one stream.
        self._events = Events()

        window = webview.create_window(
            title, url, js_api=JsApi(self._events),
            width=width, height=height, min_size=min_size
        )
        assert window is not None
        self._window = window
        self.window: app.Window = Window(window)
        self.webview: app.WebView = WebView(window)
        self._js = Js(self.webview)

        def cb_loaded() -> None:
            self._events.post("load", ())
        def cb_closing() -> bool:
            # Post the attempt and keep the window open so Core can run its
            # shutdown; if the bridge is already down (Core gone), allow close.
            return not self._events.post("close", ())

        window.events.loaded += cb_loaded
        window.events.closing += cb_closing

    def start(self) -> None:
        """Run the GUI on the main thread until the window is destroyed.

        The core thread owns and runs the asyncio loop through core.main; here
        webview.start just blocks running the platform GUI loop. quit() destroys
        the window to return from here, so the caller can join the core thread.
        """
        webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
        try:
            webview.start(debug=self._debug, icon=self._icon)
        finally:
            # If the GUI ended without a Core-driven quit, release Core so the
            # core thread returns: fail in-flight js_call futures and end the
            # event stream so run() unwinds. Safe no-ops if quit() already ran.
            self._js.shutdown()
            self._events.shutdown()

    def quit(self) -> None:
        """Shut the app down from the core thread when Core's lifecycle ends.

        Stops the py2js and js2py bridges, failing in-flight work fast (cancels
        queued js_call futures and the pending get_event wait), then destroys
        the window so start() returns on the main thread. run() returns right
        after this call, which ends core.main's loop.
        """
        self._js.shutdown()
        self._events.shutdown()
        self._window.destroy()

    def js_call(self, func: str, args: tuple[Any, ...]) -> Future[Any]:
        """Call a frontend function and return a future for its result."""
        return self._js.call(func, args)

    def get_event(self) -> "Future[app.App.Event]":
        """Return a future for the next inbound frontend or OS event."""
        return self._events.get_event()

    def show_open_dialog(
        self, *, multiple: bool = False, filters: tuple[str, ...] = ()
    ) -> Future[Any]:
        """Show a native open dialog and return a future for the picks.

        Resolves to the chosen path, a list of paths when multiple is set, or
        None when the dialog is dismissed. The dialog runs on a worker thread
        that settles the concurrent future directly.
        """
        def show_dialog() -> Any:
            try:
                picks = self._window.create_file_dialog(
                    webview.FileDialog.OPEN,
                    allow_multiple=multiple,
                    file_types=tuple(filters)
                )

                result: list[str] | str | None = None
                if picks:
                    result = list(picks) if multiple else picks[0]
                fut_resolve(fut, result)
            except Exception as exc:
                fut_exception(fut, exc)

        fut: Future[Any] = Future()
        threading.Thread(
            target=show_dialog, name="app.file_dialog", daemon=True
        ).start()
        return fut

    def show_save_dialog(
        self, *, filename: str = "", filters: tuple[str, ...] = ()
    ) -> Future[Any]:
        """Show a native save dialog and return a future for the path.

        Resolves to the chosen path, or None when the dialog is dismissed. The
        dialog runs on a worker thread that settles the concurrent future
        directly.
        """
        def show_dialog() -> Any:
            try:
                picks = self._window.create_file_dialog(
                    webview.FileDialog.SAVE,
                    save_filename=filename,
                    file_types=tuple(filters),
                )

                result: str | None = None
                if picks:
                    result = picks if isinstance(picks, str) else picks[0]
                fut_resolve(fut, result)
            except Exception as exc:
                fut_exception(fut, exc)

        fut: Future[Any] = Future()
        threading.Thread(
            target=show_dialog, name="app.file_dialog", daemon=True
        ).start()
        return fut
