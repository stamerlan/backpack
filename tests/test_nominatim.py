"""Tests for the Nominatim geocoding client.

A fake stands in for the geopy client, so no request leaves the machine. The
rate limit and the retry delay are shortened per test to keep the suite fast.
"""
import threading
import time
from typing import Any

import pytest
from geopy.exc import (
    GeocoderQueryError,
    GeocoderRateLimited,
    GeocoderTimedOut,
    GeocoderUnavailable,
)

from backpack.nominatim import Nominatim

TIMER_SLACK_S = 0.05


class FakeLocation:
    """Stands in for geopy's Location, which only carries .raw here."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw


class FakeGeo:
    """Replays canned results and records how it was called.

    A result that is an Exception is raised instead of returned, which is how
    a test drives the retry paths.
    """

    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.calls = list[tuple[str, Any, dict[str, Any]]]()

    def reverse(self, query: Any, **kwargs: Any) -> Any:
        return self._pop("reverse", query, kwargs)

    def geocode(self, query: Any, **kwargs: Any) -> Any:
        return self._pop("geocode", query, kwargs)

    def _pop(self, name: str, query: Any, kwargs: dict[str, Any]) -> Any:
        self.calls.append((name, query, kwargs))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_nom(
    *results: object, interval_s: float = 0.0, retry_delay_s: float = 0.01
) -> tuple[Nominatim, FakeGeo]:
    nom = Nominatim()
    geo = FakeGeo(*results)
    nom._geo = geo
    nom.REQ_INTERVAL_S = interval_s
    nom.RETRY_DELAY_S = retry_delay_s
    return nom, geo


def test_reverse_returns_the_raw_place() -> None:
    place = {"name": "Kvasy", "display_name": "Kvasy, Ukraine"}
    nom, geo = make_nom(FakeLocation(place))

    assert nom.reverse(48.15, 24.31) == place

    name, query, kwargs = geo.calls[0]
    assert name == "reverse"
    assert query == (48.15, 24.31)
    assert kwargs == {"exactly_one": True, "zoom": 14, "addressdetails": True}


def test_reverse_passes_the_requested_zoom() -> None:
    nom, geo = make_nom(FakeLocation({}))
    nom.reverse(48.15, 24.31, zoom=10)
    assert geo.calls[0][2]["zoom"] == 10


def test_reverse_returns_none_when_nothing_is_found() -> None:
    nom, _ = make_nom(None)
    assert nom.reverse(0.0, 0.0) is None


def test_search_forward_geocodes_the_query() -> None:
    place = {"lat": "48.16", "lon": "24.50"}
    nom, geo = make_nom(FakeLocation(place))

    assert nom.search("Hoverla, Ukraine") == place

    name, query, kwargs = geo.calls[0]
    assert name == "geocode"
    assert query == "Hoverla, Ukraine"
    assert kwargs == {"exactly_one": True, "addressdetails": True}


def test_search_returns_none_when_nothing_is_found() -> None:
    nom, _ = make_nom(None)
    assert nom.search("nowhere at all") is None


def test_requests_are_spaced_by_the_rate_limit() -> None:
    nom, _ = make_nom(
        FakeLocation({}), FakeLocation({}), interval_s=0.2
    )
    start = time.monotonic()
    nom.reverse(1.0, 2.0)
    nom.reverse(3.0, 4.0)
    assert time.monotonic() - start >= 0.2 - TIMER_SLACK_S


def test_timeout_is_retried() -> None:
    nom, geo = make_nom(GeocoderTimedOut("slow"), FakeLocation({"ok": True}))
    assert nom.reverse(1.0, 2.0) == {"ok": True}
    assert len(geo.calls) == 2


def test_outage_is_retried() -> None:
    nom, geo = make_nom(
        GeocoderUnavailable("down"), FakeLocation({"ok": True})
    )
    assert nom.reverse(1.0, 2.0) == {"ok": True}
    assert len(geo.calls) == 2


def test_rate_limit_honours_retry_after() -> None:
    nom, geo = make_nom(
        GeocoderRateLimited("slow down", retry_after=0.2),
        FakeLocation({"ok": True}),
        retry_delay_s=0.0,
    )
    start = time.monotonic()
    assert nom.reverse(1.0, 2.0) == {"ok": True}
    assert time.monotonic() - start >= 0.2 - TIMER_SLACK_S
    assert len(geo.calls) == 2


def test_retries_run_out() -> None:
    nom, geo = make_nom(GeocoderTimedOut("a"), GeocoderTimedOut("b"))
    with pytest.raises(GeocoderTimedOut):
        nom.reverse(1.0, 2.0, retries=1)
    assert len(geo.calls) == 2


def test_bad_query_is_not_retried() -> None:
    nom, geo = make_nom(GeocoderQueryError("bad"), FakeLocation({}))
    with pytest.raises(GeocoderQueryError):
        nom.reverse(1000.0, 1000.0)
    assert len(geo.calls) == 1


def test_call_after_cancel_aborts() -> None:
    nom, geo = make_nom(FakeLocation({}))
    nom.cancel()
    with pytest.raises(Nominatim.Aborted):
        nom.reverse(1.0, 2.0)
    assert not geo.calls


def test_cancel_releases_a_caller_waiting_for_a_slot() -> None:
    nom, _ = make_nom(FakeLocation({}), FakeLocation({}), interval_s=30.0)
    nom.reverse(1.0, 2.0)
    assert _run_and_cancel(nom, lambda: nom.reverse(3.0, 4.0))


def test_cancel_releases_a_caller_waiting_to_retry() -> None:
    nom, _ = make_nom(
        GeocoderTimedOut("slow"), FakeLocation({}), retry_delay_s=30.0
    )
    assert _run_and_cancel(nom, lambda: nom.reverse(1.0, 2.0))


def _run_and_cancel(nom: Nominatim, call: Any) -> bool:
    """Run call in a thread, cancel nom, and report whether it aborted."""
    caught = list[BaseException]()

    def worker() -> None:
        try:
            call()
        except BaseException as e:
            caught.append(e)

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.05)
    nom.cancel()
    t.join(timeout=5.0)
    assert not t.is_alive(), "cancel did not release the caller"
    return len(caught) == 1 and isinstance(caught[0], Nominatim.Aborted)
