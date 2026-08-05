import logging
import threading
import time
from typing import Any, Callable

from geopy.exc import (
    GeocoderQueryError,
    GeocoderRateLimited,
    GeocoderServiceError,
    GeocoderTimedOut,
    GeocoderUnavailable,
)
from geopy.geocoders import Nominatim as _GeoNominatim

from . import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


class Nominatim:
    """OpenStreetMap geocoding with the public 1 req/s budget respected.

    The public Nominatim service allows one request per second per client and
    bans clients that ignore it, so every call reserves a slot first. One
    instance is meant to be shared by all callers: the budget is per instance,
    and the class is thread safe.
    """

    REQ_INTERVAL_S = 1.0
    RETRY_DELAY_S = 1.0     # used when the service names no delay itself

    class Aborted(Exception):
        """Raised from any call after cancel() - a control signal, not an error.
        """

    def __init__(
        self,
        user_agent: str = f"{APP_NAME}/{APP_VERSION} (trip planner)",
        timeout_s: float = 30.0,
    ) -> None:
        self._geo = _GeoNominatim(user_agent=user_agent, timeout=timeout_s)
        self._cancel = threading.Event()

        # Serializes callers and enforces the shared 1 req/s budget.
        self._rate_lock = threading.Lock()
        self._next_time = 0.0           # monotonic time of next request

    def cancel(self) -> None:
        """Cancel all pending requests. After this every call raises Aborted.
        A request already in flight ends within its timeout.
        """
        self._cancel.set()

    def reverse(
        self, lat: float, long: float, zoom: int = 14, retries: int = 3
    ) -> dict[str, Any] | None:
        """Resolve coordinates to an OSM place.
        
        :param float lat: Latitude in decimal degrees.
        :param float long: Longitude in decimal degrees.
        :param int zoom: OSM zoom level of the answer, 3 for country up to 18
            for building. The default 14 lands on a suburb or village.
        :param int retries: How many times to retry a timeout, an outage or a
            rate limit before giving up.
        :return: JSON dict or None if nothing was found.
        :raises Aborted: If cancel() was called.
        """
        loc = self._request(
            self._geo.reverse, (lat, long), retries=retries,
            exactly_one=True, zoom=zoom, addressdetails=True,
        )
        return None if loc is None else loc.raw

    def search(self, query: str, retries: int = 3) -> dict[str, Any] | None:
        """Forward geocode a free-form query.

        :param str query: Free-form place name, e.g. "Hoverla, Ukraine".
        :param int retries: How many times to retry a timeout, an outage or a
            rate limit before giving up.
        :return: JSON dict of the best match, or None.
        :raises Aborted: If cancel() was called.
        """
        loc = self._request(
            self._geo.geocode, query, retries=retries,
            exactly_one=True, addressdetails=True,
        )
        return None if loc is None else loc.raw

    def _request(
        self,
        func: Callable[..., Any],
        query: Any,
        *,
        retries: int,
        **kwargs: Any,
    ) -> Any:
        while True:
            self._get_slot()
            try:
                return func(query, **kwargs)
            except GeocoderQueryError:
                raise                          # bad request, do not retry
            except (
                GeocoderTimedOut, GeocoderUnavailable, GeocoderRateLimited
            ) as e:
                if retries == 0:
                    raise
                retries -= 1
                delay = getattr(e, "retry_after", None) or self.RETRY_DELAY_S
                logger.debug(f"retry in {delay}s after {e!r}")
                if self._cancel.wait(delay):
                    raise Nominatim.Aborted()
            except GeocoderServiceError:
                raise                          # unknown, do not retry

    def _get_slot(self) -> None:
        """Block until the shared 1 req/s budget allows a request, then reserve
        the slot. Raise Aborted if canceled while waiting."""
        with self._rate_lock:
            while True:
                if self._cancel.is_set():
                    raise Nominatim.Aborted()
                now = time.monotonic()
                wait = self._next_time - now
                if wait <= 0:
                    self._next_time = now + self.REQ_INTERVAL_S
                    return
                if self._cancel.wait(wait):
                    raise Nominatim.Aborted()
