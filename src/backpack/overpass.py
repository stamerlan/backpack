import http.client
import logging
import re
import threading
import urllib.error
import urllib.parse

import overpy

from . import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


class Overpass:
    """Overpass API client that respects the public server's slot budget.

    The public interpreter grants only a couple of concurrent slots and hands
    out 429s to clients that ignore that, so every query reserves a slot first,
    polling /api/status when the cached count runs out. One instance is meant to
    be shared by all callers: the budget is per instance and the class is thread
    safe.

    Queries are plain Overpass QL strings and results come back as overpy
    objects (nodes, ways and relations with parsed tags and centers), so callers
    neither build request bodies nor parse JSON by hand.
    """

    HOST = "overpass-api.de"
    USER_AGENT = f"{APP_NAME}/{APP_VERSION} (trip planner)"
    RETRY_DELAY_S = 1.0     # backoff before retrying a 5xx response

    class Aborted(Exception):
        """Raised from query()/status() when cancel() was called, e.g. during
        shutdown. Not an error condition - a control signal.
        """

    def __init__(self) -> None:
        self._cancel = threading.Event()

        self._cond = threading.Condition()   # guards _free_slots/_polling
        self._free_slots = 2                 # cached server availability
        self._polling = False                # a thread is in status() now

        self._conn_lock = threading.Lock()
        self._conns: set[http.client.HTTPSConnection] = set()

        # Used only to turn a response body into overpy objects; it never
        # touches the network, our own transport below does.
        self._parser = overpy.Overpass()

    def cancel(self) -> None:
        """Abort any pending or in-flight request. After this call both query()
        and status() raise Overpass.Aborted. Safe to call from another thread.
        """
        self._cancel.set()
        with self._conn_lock:
            for conn in self._conns:
                try:
                    conn.close()
                except OSError:
                    pass
            self._conns.clear()
        with self._cond:
            self._cond.notify_all()      # release poller + waiters

    def query(
        self, ql: str, timeout_s: float = 90, retries: int = 3
    ) -> overpy.Result:
        """Run an Overpass QL query and return the parsed result.

        :param str ql: The Overpass QL to POST to /api/interpreter.
        :param float timeout_s: Socket timeout for the HTTP request.
        :param int retries: How many times to retry a 429 or a 5xx before
            giving up.
        :return: The parsed overpy result (nodes, ways, relations).
        :raises Overpass.Aborted: If cancel() was called.
        """
        body = urllib.parse.urlencode({"data": ql}).encode("utf-8")
        slot_acquired = False
        while True:
            try:
                if not slot_acquired:
                    self._get_slot()
                    slot_acquired = True
                text = self._request(
                    "POST", "/api/interpreter", body, timeout_s
                )
                return self._parser.parse_json(text)
            except urllib.error.HTTPError as e:
                if e.code not in (429, 502, 503, 504) or retries == 0:
                    raise
                retries -= 1
                if e.code == 429:
                    # cache was stale; re-poll
                    with self._cond:
                        self._free_slots = 0
                        slot_acquired = False
                else:
                    if self._cancel.wait(self.RETRY_DELAY_S):
                        raise Overpass.Aborted()

    def status(self, timeout_s: float = 30) -> tuple[int, float]:
        """Return (free_slots, seconds_until_next_slot). Raise
        Overpass.Aborted if the request was canceled."""
        text = self._request("GET", "/api/status", timeout_s=timeout_s)
        m = re.search(r"(\d+)\s+slots?\s+available\s+now", text)
        if m and int(m.group(1)) > 0:
            return int(m.group(1)), 0.0

        waits = [int(s) for s in re.findall(r"in\s+(\d+)\s+seconds", text)]
        if waits:
            return 0, float(max(0, min(waits)))
        logger.warning(f"Overpass status {text!r}")
        return 1, 0.0   # unknown format, treat as free

    def _get_slot(self) -> None:
        with self._cond:
            while True:
                if self._cancel.is_set():
                    raise Overpass.Aborted()
                if self._free_slots > 0:
                    self._free_slots -= 1
                    return                       # got a cached slot
                if not self._polling:
                    self._polling = True
                    break                        # this thread is status poller
                self._cond.wait()                # another thread polls

        # Poller path: status() + sleep WITHOUT holding the lock, so the
        # others can keep waiting on the condition.
        free = 0
        try:
            free, wait = 0, 0.0
            while free == 0:
                if self._cancel.is_set():
                    raise Overpass.Aborted()
                free, wait = self.status()
                logger.debug(f"{self.HOST}: free:{free} wait:{wait}")
                if free == 0:
                    if wait == 0:
                        wait = 0.1 # to stop spamming status() requests
                    if self._cancel.wait(wait):
                        raise Overpass.Aborted()
        finally:
            with self._cond:                     # release the poller role
                self._polling = False
                if free > 0:
                    self._free_slots += free - 1 # keep one for myself
                self._cond.notify_all()          # wake waiters for the rest

    def _request(
        self, method: str, path: str, body: bytes | None = None,
        timeout_s: float = 30,
    ) -> str:
        """Perform one cancelable HTTPS request. Return the response body.
        Raise Overpass.Aborted if canceled while pending or in flight, or
        HTTPError on a 4xx/5xx response."""
        if self._cancel.is_set():
            raise Overpass.Aborted(f"{self.HOST}: {method} {path}")

        headers = {"User-Agent": self.USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        logger.debug(f"{self.HOST}: {method} {path}")

        conn = http.client.HTTPSConnection(self.HOST, timeout=timeout_s)
        with self._conn_lock:
            if self._cancel.is_set():
                conn.close()
                raise Overpass.Aborted(f"{self.HOST}: {method} {path}")
            self._conns.add(conn)

        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            status = resp.status
            text = resp.read().decode("utf-8")
        except OSError:
            if self._cancel.is_set():
                raise Overpass.Aborted(f"{self.HOST}: {method} {path}")
            raise
        finally:
            with self._conn_lock:
                self._conns.discard(conn)
            conn.close()

        logger.debug(f"{self.HOST}: {method} {path} status:{status}")
        # Raised outside the try above so it is not caught by except OSError
        # (HTTPError is an OSError subclass).
        if status >= 400:
            raise urllib.error.HTTPError(
                path, status, text, None, None  # type: ignore[arg-type]
            )
        return text
