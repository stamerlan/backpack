"""SQLite cache for Overpass POI data, keyed by slippy-map tile.

The cache stores raw POI facts (OSM type, id, coordinates, tags) grouped by
tile. A tile at TILE_ZOOM (~3.3 km at alpine latitudes) is the unit of fetching,
freshness, and eviction.

Schema version changes or database corruption cause the file to be deleted and
recreated silently. The cache is disposable and must never break trip loading.
"""
import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backpack import paths
from backpack.poi_tiles import PoiTile

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

TILE_TTL_S = 60 * 86400
MAX_AGE_S = 365 * 86400
MAX_BYTES = 200 * 1024 * 1024
TOUCH_MIN_INTERVAL_S = 86400

@dataclass(frozen=True, slots=True)
class CachedPoi:
    """A POI as stored in the cache - route-independent facts only."""

    osm_type: Literal["n", "w", "r"]
    osm_id: int
    lat: float
    long: float
    tags: dict[str, str]


def filters_hash(filters: tuple[str, ...]) -> int:
    """Stable 32-bit hash of the active POI filter set.

    When the filters change, cached tiles fetched under the old set are
    treated as missing rather than stale, since they may be incomplete.
    """
    h = hashlib.sha256("\n".join(filters).encode()).digest()
    return int.from_bytes(h[:4])


_SCHEMA = """\
CREATE TABLE tile (
    x          INTEGER NOT NULL,
    y          INTEGER NOT NULL,
    filters    INTEGER NOT NULL,
    fetched_at INTEGER NOT NULL,
    used_at    INTEGER NOT NULL,
    PRIMARY KEY (x, y)
);
CREATE TABLE poi (
    x        INTEGER NOT NULL,
    y        INTEGER NOT NULL,
    osm_type TEXT    NOT NULL,
    osm_id   INTEGER NOT NULL,
    lat      REAL    NOT NULL,
    long     REAL    NOT NULL,
    tags     TEXT    NOT NULL,
    PRIMARY KEY (x, y, osm_type, osm_id),
    FOREIGN KEY (x, y) REFERENCES tile ON DELETE CASCADE
);
"""


class _Recreate(Exception):
    """The cache file must be deleted and rebuilt."""


class PoiCache:
    """Thread-safe SQLite cache for tile-keyed POI data.

    One connection with check_same_thread=False guarded by a threading.Lock.
    Writes are tiny so a single lock is simpler than one connection per worker.
    """

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = paths.appcache() / "poi.sqlite3"
        self.path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._open()

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = self._db_connect()
            return
        except (sqlite3.DatabaseError, _Recreate):
            pass
        logger.warning(f"poi cache unusable, recreating: {self.path}")
        self.path.unlink(missing_ok=True)
        self._conn = self._db_connect()

    def _db_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        try:
            conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                conn.executescript(_SCHEMA)
                conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            elif version != _SCHEMA_VERSION:
                raise _Recreate(f"version {version} != {_SCHEMA_VERSION}")
        except BaseException:
            conn.close()
            raise
        return conn

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def put(
        self, tile: PoiTile, pois: list[CachedPoi], current_filters: int
    ) -> None:
        """Write a tile and its POIs, replacing any previous data.

        Stamps fetched_at and used_at to now; stores the filter hash so future
        reads can detect whether the cached set is complete.
        """
        now = int(time.time())
        with self._lock:
            assert self._conn is not None
            conn = self._conn
            with conn:
                conn.execute(
                    "DELETE FROM tile WHERE x=? AND y=?",
                    (tile.x, tile.y)
                )
                conn.execute(
                    "INSERT INTO tile"
                    " (x, y, filters, fetched_at, used_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (tile.x, tile.y, current_filters, now, now)
                )
                conn.executemany(
                    "INSERT INTO poi"
                    " (x, y, osm_type, osm_id, lat, long, tags)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            tile.x, tile.y,
                            p.osm_type, p.osm_id,
                            p.lat, p.long,
                            json.dumps(
                                p.tags, ensure_ascii=False
                            ),
                        )
                        for p in pois
                    ]
                )

    def touch(self, tiles: frozenset[PoiTile]) -> None:
        """Bump used_at for tiles, throttled to once per day.

        Only updates tiles whose stored used_at is more than
        TOUCH_MIN_INTERVAL_S old, so opening a trip repeatedly does not cause a
        write storm.
        """
        if not tiles:
            return
        now = int(time.time())
        threshold = now - TOUCH_MIN_INTERVAL_S
        with self._lock:
            assert self._conn is not None
            conn = self._conn
            with conn:
                for tile in tiles:
                    conn.execute(
                        "UPDATE tile SET used_at=?"
                        " WHERE x=? AND y=? AND used_at<?",
                        (now, tile.x, tile.y, threshold),
                    )

    def evict(self) -> int:
        """Remove old and excess tiles, then vacuum freed pages.

        Eviction order:
        1. Delete tiles with used_at older than MAX_AGE_S.
        2. While file size exceeds MAX_BYTES, delete the least recently used
           tile until under budget.
        3. Run incremental vacuum to release freed pages to the OS.

        Returns the number of tiles deleted.
        """
        now = int(time.time())
        cutoff = now - MAX_AGE_S
        deleted = 0
        with self._lock:
            assert self._conn is not None
            conn = self._conn
            with conn:
                cur = conn.execute(
                    "DELETE FROM tile WHERE used_at<?", (cutoff,)
                )
                deleted += cur.rowcount
            while self._file_size_locked() > MAX_BYTES:
                with conn:
                    cur = conn.execute(
                        "DELETE FROM tile WHERE rowid IN"
                        " (SELECT rowid FROM tile"
                        " ORDER BY used_at ASC LIMIT 1)"
                    )
                    if cur.rowcount == 0:
                        break
                    deleted += cur.rowcount
            conn.execute("PRAGMA incremental_vacuum")
        if deleted:
            logger.info(f"poi cache evicted {deleted} tiles")
        return deleted

    def _file_size_locked(self) -> int:
        """File size in bytes; caller must hold self._lock."""
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def get(
        self, tiles: frozenset[PoiTile], current_filters: int
    ) -> tuple[
        dict[PoiTile, list[CachedPoi]],
        frozenset[PoiTile],
        frozenset[PoiTile],
    ]:
        """Look up tiles in the cache.

        Returns (hits, missing, stale) where:
        - hits maps each cached tile to its POIs;
        - missing is the set of tiles not in the cache or fetched under a
          different filter set;
        - stale is the set of tiles older than TILE_TTL_S (also in hits, so they
          can be served immediately and refreshed in the background).
        """
        now = int(time.time())
        hits: dict[PoiTile, list[CachedPoi]] = {}
        missing: set[PoiTile] = set()
        stale: set[PoiTile] = set()

        with self._lock:
            assert self._conn is not None
            conn = self._conn
            for tile in tiles:
                row = conn.execute(
                    "SELECT filters, fetched_at FROM tile WHERE x=? AND y=?",
                    (tile.x, tile.y)
                ).fetchone()
                if row is None:
                    missing.add(tile)
                    continue
                stored_filters, fetched_at = row
                if stored_filters != current_filters:
                    missing.add(tile)
                    continue
                pois: list[CachedPoi] = []
                for pr in conn.execute(
                    "SELECT osm_type, osm_id, lat, long, tags"
                    " FROM poi WHERE x=? AND y=?",
                    (tile.x, tile.y)
                ):
                    pois.append(CachedPoi(
                        osm_type=pr[0],
                        osm_id=pr[1],
                        lat=pr[2],
                        long=pr[3],
                        tags=json.loads(pr[4]),
                    ))
                hits[tile] = pois
                if now - fetched_at > TILE_TTL_S:
                    stale.add(tile)

        return hits, frozenset(missing), frozenset(stale)
