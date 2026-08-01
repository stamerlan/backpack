import threading
import time
from collections.abc import Callable
from concurrent.futures import CancelledError, Future
from dataclasses import dataclass
from typing import Any, cast

import pytest
import webview

from backpack.js_worker import JsWorker
from tests.fake_window import FakeWindow


def test_result_settled_on_worker_thread(
    js: JsWorker, win: FakeWindow
) -> None:
    js.start(cast(webview.Window, win))

    fut = js.submit("greet", ("world", 3))
    cb = win.take_cb()
    assert 'greet("world", 3)' in win.scripts[0]

    recorded: dict[str, str] = {}
    done = threading.Event()

    def on_done(_f: Future[Any]) -> None:
        recorded["thread"] = threading.current_thread().name
        done.set()

    fut.add_done_callback(on_done)
    cb(42)

    assert fut.result(timeout=2.0) == 42
    assert done.wait(2.0)
    assert recorded["thread"] == "js_worker.worker"


def test_undefined_result_maps_to_none(
    js: JsWorker, win: FakeWindow
) -> None:
    js.start(cast(webview.Window, win))
    fut = js.submit("noop", ())
    cb = win.take_cb()
    cb(None)
    assert fut.result(timeout=2.0) is None


def test_js_error_becomes_exception(
    js: JsWorker, win: FakeWindow
) -> None:
    js.start(cast(webview.Window, win))
    fut = js.submit("boom", ())
    cb = win.take_cb()
    cb({
        "name": "TypeError",
        "message": "kaboom",
        "stack": "at boom (app.js:1)",
        "pywebviewJavascriptError420": True,
    })

    with pytest.raises(webview.JavascriptException) as ei:
        fut.result(timeout=2.0)

    notes = getattr(ei.value, "__notes__", [])
    assert any("TypeError: kaboom" in n for n in notes)
    assert any(n.startswith("Thread ") for n in notes)


def test_sync_evaluate_failure_settles_future(
    js: JsWorker, win: FakeWindow
) -> None:
    win.exception = RuntimeError("inject failed")
    js.start(cast(webview.Window, win))
    fut = js.submit("nope", ())

    with pytest.raises(RuntimeError, match="inject failed") as ei:
        fut.result(timeout=2.0)

    notes = getattr(ei.value, "__notes__", [])
    assert any(n.startswith("Thread ") for n in notes)


def test_submit_before_start_is_queued(
    js: JsWorker, win: FakeWindow
) -> None:
    fut = js.submit("early", (1,))
    assert not fut.done()

    js.start(cast(webview.Window, win))
    cb = win.take_cb()
    assert "early(1)" in win.scripts[0]
    cb("ok")
    assert fut.result(timeout=2.0) == "ok"


def test_submit_after_shutdown_is_cancelled(
    js: JsWorker, win: FakeWindow
) -> None:
    js.start(cast(webview.Window, win))
    js.shutdown()

    fut = js.submit("late", ())
    assert fut.cancelled()


def test_shutdown_aborts_inflight_call(
    js: JsWorker, win: FakeWindow
) -> None:
    js.start(cast(webview.Window, win))
    fut = js.submit("hang", ())
    win.take_cb()  # dispatched, promise is never resolved

    js.shutdown()

    with pytest.raises(CancelledError):
        fut.result(timeout=2.0)


def test_shutdown_cancels_queued_call(js: JsWorker) -> None:
    gate = threading.Event()
    started = threading.Event()

    class BlockingWindow:
        def __init__(self) -> None:
            self.scripts: list[str] = []

        def evaluate_js(
            self, script: str, callback: Callable[[Any], None]
        ) -> None:
            self.scripts.append(script)
            started.set()
            gate.wait(2.0)

    js.start(cast(webview.Window, BlockingWindow()))

    first = js.submit("first", ())
    assert started.wait(2.0)  # worker is blocked inside evaluate_js
    second = js.submit("second", ())  # stays queued, never dispatched

    shutdown_done = threading.Event()

    def do_shutdown() -> None:
        js.shutdown()
        shutdown_done.set()

    t = threading.Thread(target=do_shutdown)
    t.start()

    # Release the worker only after shutdown has set the quit flag, so it
    # sees the flag and exits instead of dispatching the queued "second".
    deadline = time.monotonic() + 2.0
    while not js._quit and time.monotonic() < deadline:
        time.sleep(0.001)
    assert js._quit
    gate.set()

    assert shutdown_done.wait(2.0)
    t.join()

    assert second.cancelled()
    with pytest.raises(CancelledError):
        first.result(timeout=2.0)


def test_double_start_raises(js: JsWorker, win: FakeWindow) -> None:
    js.start(cast(webview.Window, win))
    with pytest.raises(RuntimeError):
        js.start(cast(webview.Window, win))


def test_dataclass_arg_is_json_encoded(
    js: JsWorker, win: FakeWindow
) -> None:
    @dataclass
    class Point:
        x: int
        y: int

    js.start(cast(webview.Window, win))
    fut = js.submit("plot", (Point(1, 2),))
    cb = win.take_cb()
    assert '{"x": 1, "y": 2}' in win.scripts[0]
    cb(None)
    assert fut.result(timeout=2.0) is None


def test_non_serializable_arg_fails_future(
    js: JsWorker, win: FakeWindow
) -> None:
    js.start(cast(webview.Window, win))
    fut = js.submit("f", (object(),))
    with pytest.raises(TypeError):
        fut.result(timeout=2.0)
