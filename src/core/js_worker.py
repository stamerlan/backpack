import json
import logging
import threading
import traceback
import webview
from collections import deque
from concurrent.futures import CancelledError, Future, InvalidStateError
from dataclasses import asdict, is_dataclass
from textwrap import dedent
from typing import Any

logger = logging.getLogger(__name__)


class JsWorker:
    """Outbound bridge to the frontend with an owned worker thread.

    One worker thread performs every step: it dispatches a call to the web view
    and later settles the matching future. Settling the future - and therefore
    any ``add_done_callback`` callback - runs on that same worker thread.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._jobs = deque[CallJob]()
        self._cpl_jobs = deque[JobResult]()
        self._pending_jobs = set[CallJob]()
        self._quit = False
        self._th: threading.Thread | None = None

    def start(self, window: webview.Window) -> None:
        with self._cond:
            if self._th is not None:
                raise RuntimeError("js_worker has been started")
            self._quit = False
            self._th = threading.Thread(
                target=self._worker, name="js_worker.worker", args=(window,)
            )
            self._th.start()

    def shutdown(self) -> None:
        with self._cond:
            th = self._th
            self._th = None
            self._quit = True
            self._cond.notify_all()
        if th is None:
            return

        th.join()

        with self._cond:
            calls = list(self._jobs)
            pending = list(self._pending_jobs)
            self._jobs.clear()
            self._pending_jobs.clear()
            self._cpl_jobs.clear()

        # Never dispatched -> cancel.
        for job in calls:
            if job.future.cancel():
                logger.info(f"cancel {job}")

        # Dispatched, still awaiting the frontend -> abort.
        for job in pending:
            try:
                job.future.set_exception(CancelledError("shutdown"))
            except InvalidStateError:
                pass  # already settled
            else:
                logger.info(f"abort {job}")

        logger.debug("js_worker.worker stopped")

    def submit(self, func: str, args: tuple[Any, ...]) -> Future[Any]:
        """Queue a frontend function call and return its future.

        The worker thread performs the call and later settles the future with
        the frontend return value. Calls submitted before ``start()`` are
        queued and dispatched once started. After ``shutdown()`` the future is
        cancelled so callers fail fast instead of blocking on a result that
        will never arrive.
        """
        fut = Future[Any]()
        try:
            job = CallJob(
                func,
                ", ".join(json.dumps(a, default=_encode) for a in args),
                fut,
            )
        except Exception as exc:
            fut.set_exception(exc)
            return fut

        with self._cond:
            quit = self._quit
            if not quit:
                self._jobs.append(job)
                self._cond.notify()
        if quit:
            fut.cancel()
        return fut

    def _worker(self, window: webview.Window) -> None:
        while True:
            j: CallJob | JobResult | None = None
            with self._cond:
                if self._quit:
                    return
                elif self._cpl_jobs:
                    j = self._cpl_jobs.popleft()
                    self._pending_jobs.discard(j.call)
                elif self._jobs:
                    j = self._jobs.popleft()
                else:
                    self._cond.wait()

            if isinstance(j, JobResult):
                try:
                    if j.exc is not None:
                        j.call.future.set_exception(j.exc)
                    elif (
                        isinstance(j.result, dict) and
                        j.result.get("pywebviewJavascriptError420")
                    ):
                        del j.result["pywebviewJavascriptError420"]
                        js_exc = webview.JavascriptException(j.result)
                        j.call.annotate(js_exc)
                        j.call.future.set_exception(js_exc)
                    else:
                        j.call.future.set_result(j.result)
                except InvalidStateError:
                    pass  # already cancelled or settled
            elif isinstance(j, CallJob):
                if not j.future.set_running_or_notify_cancel():
                    continue
                with self._cond:
                    self._pending_jobs.add(j)
                try:
                    def cb(result: Any, job: CallJob = j) -> None:
                        # Runs on the GUI thread. Keep it tiny: hand the result
                        # to the worker thread, which settles the future and
                        # runs callbacks.
                        with self._cond:
                            self._cpl_jobs.append(JobResult(job, result, None))
                            self._cond.notify()

                    window.evaluate_js(j.async_call_str(), cb)
                except Exception as exc:
                    j.annotate(exc)
                    logger.exception(f"call failed: {j}")
                    with self._cond:
                        self._cpl_jobs.append(JobResult(j, None, exc))
                        self._cond.notify()


def _encode(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(
        f"Object of type {obj.__class__.__name__} is not JSON serializable"
    )


class CallJob:
    """A single queued call plus the context needed to run and debug it.

    ``str(job)`` yields the snippet handed to ``evaluate_js``. The calling
    thread name and stack are captured at construction time so a later failure
    can be traced back to the original call site.
    """

    __slots__ = ("func", "params", "future", "caller_thread", "caller_stack")

    def __init__(self, func: str, params: str, future: Future[Any]) -> None:
        self.func = func
        self.params = params
        self.future = future
        self.caller_thread = threading.current_thread().name
        # drop the __init__ frame
        self.caller_stack = "".join(traceback.format_stack()[:-1])

    def __str__(self) -> str:
        return f"{self.func}({self.params})"

    def annotate(self, exc: BaseException) -> None:
        """Attach frontend and caller context to ``exc`` as notes."""

        if isinstance(exc, webview.JavascriptException):
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
        exc.add_note(
            f"Thread {self.caller_thread!r}:\n{self.caller_stack}"
        )

    def async_call_str(self) -> str:
        """Wrap the call so evaluate_js returns without waiting.

        The frontend function is wrapped in a promise so evaluate_js returns
        right after injection and a callback arrives even when the function is
        synchronous. An undefined result is mapped to null: pywebview posts the
        value as JSON.stringify(result), which yields undefined for undefined
        and drops the reply, leaving the future forever pending.
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
        """ % str(self))


class JobResult:
    def __init__(
        self, call_job: CallJob, result: Any, exc: BaseException | None
    ) -> None:
        self.call = call_job
        self.result = result
        self.exc = exc
