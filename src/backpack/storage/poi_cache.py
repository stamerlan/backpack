"""SQLite cache for Overpass POI data, keyed by slippy-map tile.

The cache stores raw POI facts (OSM type, id, coordinates, tags) grouped by
tile. A tile at TILE_ZOOM (~3.3 km at alpine latitudes) is the unit of fetching,
freshness, and eviction.

Schema version changes or database corruption cause the file to be deleted and
recreated silently. The cache is disposable and must never break trip loading.
"""
import logging
import sqlite3
import threading
from pathlib import Path

from backpack import paths

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

TILE_TTL_S = 60 * 86400
MAX_AGE_S = 365 * 86400
MAX_BYTES = 200 * 1024 * 1024
TOUCH_MIN_INTERVAL_S = 86400

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
