"""Tests for the Overpass client.

A fake stands in for _request, so no request leaves the machine. Status text
and interpreter results are canned per test, and the retry delay is shortened
to keep the suite fast.
"""
import threading
import time
import urllib.error
from typing import Any

import overpy
import pytest

from core.overpass import Overpass

TIMER_SLACK_S = 0.05

TWO_ELEMENTS = (
    '{"elements":['
    '{"type":"node","id":1,"lat":48.1,"lon":24.3,'
    '"tags":{"natural":"peak"}},'
    '{"type":"way","id":2,"center":{"lat":48.2,"lon":24.4},'
    '"tags":{"tourism":"alpine_hut"}}'
    ']}'
)


class FakeHttp:
    """Replaces Overpass._request and records how it was called.

    A GET to /api/status returns the canned status text. Any other path pops
    the next interpreter result; a result that is an Exception is raised
    instead of returned, which is how a test drives the retry paths.
    """

    def __init__(
        self, *interpreter: object, status: str = "1 slots available now"
    ) -> None:
        self.interpreter = list(interpreter)
        self.status_text = status
        self.calls = list[tuple[str, str, bytes | None, float]]()

    def __call__(
        self, method: str, path: str, body: bytes | None = None,
        timeout_s: float = 30,
    ) -> str:
        self.calls.append((method, path, body, timeout_s))
        if path == "/api/status":
            return self.status_text
        result = self.interpreter.pop(0)
        if isinstance(result, Exception):
            raise result
        return str(result)


def make_over(
    *interpreter: object,
    status: str = "1 slots available now",
    retry_delay_s: float = 0.01,
) -> tuple[Overpass, FakeHttp]:
    over = Overpass()
    http = FakeHttp(*interpreter, status=status)
    over._request = http  # type: ignore[method-assign]
    over.RETRY_DELAY_S = retry_delay_s
    return over, http


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "/api/interpreter", code, "", None, None  # type: ignore[arg-type]
    )


def test_query_parses_the_response_into_overpy_objects() -> None:
    over, http = make_over(TWO_ELEMENTS)
    result = over.query("out;")

    node = result.nodes[0]
    assert (node.id, float(node.lat), float(node.lon)) == (1, 48.1, 24.3)
    assert node.tags == {"natural": "peak"}

    way = result.ways[0]
    assert (way.id, float(way.center_lat), float(way.center_lon)) == (
        2, 48.2, 24.4
    )
    assert way.tags == {"tourism": "alpine_hut"}


def test_query_posts_the_ql_as_form_data() -> None:
    over, http = make_over('{"elements":[]}')
    over.query("node[amenity];out;")

    method, path, body, _ = http.calls[0]
    assert (method, path) == ("POST", "/api/interpreter")
    assert body is not None and body.startswith(b"data=")


def test_query_uses_cached_slots_without_polling() -> None:
    over, http = make_over('{"elements":[]}')
    over.query("out;")
    assert all(path != "/api/status" for _, path, _, _ in http.calls)


def test_status_parses_slots_available() -> None:
    over, _ = make_over(status="3 slots available now")
    assert over.status() == (3, 0.0)


def test_status_parses_the_shortest_wait() -> None:
    over, _ = make_over(
        status="Slot available after: in 9 seconds. in 5 seconds."
    )
    assert over.status() == (0, 5.0)


def test_status_unknown_format_is_treated_as_free() -> None:
    over, _ = make_over(status="gibberish")
    assert over.status() == (1, 0.0)


def test_query_repolls_and_retries_after_429() -> None:
    over, http = make_over(
        http_error(429), '{"elements":[]}', status="1 slots available now"
    )
    result = over.query("out;")
    assert isinstance(result, overpy.Result)
    paths = [path for _, path, _, _ in http.calls]
    assert paths == ["/api/interpreter", "/api/status", "/api/interpreter"]


def test_query_retries_after_a_5xx() -> None:
    over, http = make_over(http_error(503), '{"elements":[]}')
    assert isinstance(over.query("out;"), overpy.Result)
    assert sum(p == "/api/interpreter" for _, p, _, _ in http.calls) == 2


def test_query_gives_up_when_retries_run_out() -> None:
    over, _ = make_over(http_error(503), http_error(503))
    with pytest.raises(urllib.error.HTTPError):
        over.query("out;", retries=1)


def test_query_does_not_retry_a_client_error() -> None:
    over, http = make_over(http_error(400), '{"elements":[]}')
    with pytest.raises(urllib.error.HTTPError):
        over.query("out;")
    assert sum(p == "/api/interpreter" for _, p, _, _ in http.calls) == 1


def test_call_after_cancel_aborts() -> None:
    over, http = make_over('{"elements":[]}')
    over.cancel()
    with pytest.raises(Overpass.Aborted):
        over.query("out;")
    assert not http.calls


def test_cancel_releases_a_caller_waiting_for_a_slot() -> None:
    over, _ = make_over(
        '{"elements":[]}', status="Slot available after: in 30 seconds."
    )
    over._free_slots = 0
    assert _run_and_cancel(over, lambda: over.query("out;"))


def _run_and_cancel(over: Overpass, call: Any) -> bool:
    """Run call in a thread, cancel over, and report whether it aborted."""
    caught = list[BaseException]()

    def worker() -> None:
        try:
            call()
        except BaseException as e:
            caught.append(e)

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.05)
    over.cancel()
    t.join(timeout=5.0)
    assert not t.is_alive(), "cancel did not release the caller"
    return len(caught) == 1 and isinstance(caught[0], Overpass.Aborted)
