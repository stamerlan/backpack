import asyncio
import functools
import logging
import threading
from typing import Any, Callable, Concatenate, Coroutine, ParamSpec, cast
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .app import App


P = ParamSpec("P")
ApiMethod = Callable[Concatenate["Api", P], Coroutine[Any, Any, Any]]
logger = logging.getLogger(__name__)


def api_method(func: ApiMethod[P]) -> Callable[Concatenate["Api", P], Any]:
    """Bridge one frontend call to an App coroutine on the mainloop.

    pywebview runs every frontend to backend call on its own thread. The wrapper
    schedules the wrapped coroutine on the App mainloop and blocks the call
    thread until it settles, so the frontend promise resolves with the App
    return value or rejects with its exception. After shutdown the wrapper
    returns None at once and never touches the App.
    """
    @functools.wraps(func)
    def wrapper(self: "Api", *args: P.args, **kw: P.kwargs) -> Any:
        with self._lock:
            if not self._running:
                return None
            fut = asyncio.run_coroutine_threadsafe(
                func(self, *args, **kw), self._app.mainloop
            )
        return fut.result()
    return cast(Callable[Concatenate["Api", P], Any], wrapper)


class Api:
    """Inbound bridge: methods the frontend can call from Python.

    pywebview publishes every public method of the js_api object as
    window.pywebview.api.*, so whatever is handed to the window defines the
    JS-callable surface. Api exists to be that curated allow-list: it names
    exactly the calls the frontend may make and forwards each to App.

    Keeping it separate from the controller lets the controller keep host-only
    public members without leaking them to JS, since only this small object is
    ever exposed.
    """

    def __init__(self, app: "App") -> None:
        self._app = app
        self._lock = threading.Lock()
        self._running = True

    def shutdown(self) -> None:
        """After the call, all API functions return None immediately."""
        with self._lock:
            self._running = False

    @api_method
    def new_doc(self) -> Coroutine[Any, Any, Any]:
        return self._app.new_doc()

    @api_method
    def open_doc(
        self, filepath: str | None = None
    ) -> Coroutine[Any, Any, Any]:
        return self._app.open_doc(filepath)

    @api_method
    def save_doc(
        self, filepath: str | None = None, show_dialog: bool = False
    ) -> Coroutine[Any, Any, Any]:
        return self._app.save_doc(filepath, show_dialog)

    @api_method
    def open_settings(self) -> Coroutine[Any, Any, Any]:
        return self._app.open_settings()

    @api_method
    def set_trip_info(
        self, card_id: str, title: str, notes: str
    ) -> Coroutine[Any, Any, Any]:
        return self._app.set_trip_info(card_id, title, notes)
