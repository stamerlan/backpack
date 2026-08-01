import queue
from collections.abc import Callable
from typing import Any


class FakeWindow:
    """Minimal stand-in for ``webview.Window``.

    ``evaluate_js`` records the injected script and hands the pywebview style
    callback to a queue so a test can deliver a result from another thread,
    mimicking the GUI thread settling the promise. Set ``exception`` to make
    the next ``evaluate_js`` raise it (one-shot), exercising the synchronous
    failure path.
    """

    def __init__(self, exc: Exception | None = None) -> None:
        self.scripts: list[str] = []
        self._cb_q: queue.Queue[Callable[[Any], None]] = queue.Queue()
        self.exception = exc

    def evaluate_js(
        self, script: str, callback: Callable[[Any], None]
    ) -> None:
        if self.exception is not None:
            e = self.exception
            self.exception = None
            raise e
        self.scripts.append(script)
        self._cb_q.put(callback)

    def take_cb(self, timeout: float = 2.0) -> Callable[[Any], None]:
        """Block until the worker dispatched a call, return its callback."""
        return self._cb_q.get(timeout=timeout)
