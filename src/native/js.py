"""Outbound frontend calls, shared by the app hosts"""

import json
import logging
import threading
import traceback
from concurrent.futures import Future
from dataclasses import asdict, is_dataclass
from typing import Any

logger = logging.getLogger(__name__)


class JsError(Exception):
    """A frontend function rejected or threw"""


def encode(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(
        f"Object of type {obj.__class__.__name__} is not JSON serializable"
    )


class JsCall:
    """One outbound frontend call, its future and the context to debug it.

    expr is the call expression a host hands to the web view. The submitting
    thread name and stack are captured so a failure settled on another thread
    can be traced back to the original call site. Every failure is annotated
    and logged the same way whichever host runs the call, so an error is
    never lost when the caller drops the future. A call whose args cannot be
    encoded is failed at once, so check fut.done() before running it.
    """

    __slots__ = ("expr", "fut", "caller_th", "caller_stack")

    def __init__(self, func: str, args: tuple[Any, ...]) -> None:
        self.fut: Future[Any] = Future()
        self.caller_th = threading.current_thread().name
        # drop the __init__ frame
        self.caller_stack = "".join(traceback.format_stack()[:-1])
        try:
            params = ", ".join(json.dumps(a, default=encode) for a in args)
        except Exception as exc:
            self.expr = f"{func}(...)"
            self.set_exception(exc)
        else:
            self.expr = f"{func}({params})"

    def set_result(self, result: Any) -> None:
        """Settle with the raw frontend result.

        The result is the call's value, or a pywebviewJavascriptError420 object
        when the frontend threw, which fails the call with a JsError.
        """
        if isinstance(result, dict) and result.get(
            "pywebviewJavascriptError420"
        ):
            del result["pywebviewJavascriptError420"]
            self.set_exception(JsError(result))
        elif not self.fut.done():
            self.fut.set_result(result)

    def set_exception(self, exc: BaseException) -> None:
        """Fail the call with exc, annotated with frontend and caller context.
        """
        if self.fut.done():
            return
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
        logger.error(f"call failed: {self.expr}", exc_info=exc)
        self.fut.set_exception(exc)
