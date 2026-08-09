"""Tests for backpack.storage.poi_cache - SQLite POI cache lifecycle."""
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

from backpack.poi_tiles import PoiTile
from backpack.storage.poi_cache import (
    CachedPoi,
    PoiCache,
    TILE_TTL_S,
    _SCHEMA_VERSION,
    filters_hash,
)


def _tables(db: Path) -> set[str]:
    conn = sqlite3.connect(str(db))
    names = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type='table'"
        )
    }
    conn.close()
    return names


def _pragma(db: Path, name: str) -> object:
    conn = sqlite3.connect(str(db))
    value = conn.execute(f"PRAGMA {name}").fetchone()[0]
    conn.close()
    return value


class TestOpen:
    def test_creates_parent_dir(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "sub" / "dir" / "poi.sqlite3"
        cache = PoiCache(db)
        assert db.exists()
        cache.close()

    def test_creates_tables(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        cache = PoiCache(db)
        tables = _tables(db)
        assert "tile" in tables
        assert "poi" in tables
        cache.close()

    def test_wal_journal_mode(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        cache = PoiCache(db)
        assert _pragma(db, "journal_mode") == "wal"
        cache.close()

    def test_auto_vacuum_incremental(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        cache = PoiCache(db)
        assert _pragma(db, "auto_vacuum") == 2
        cache.close()

    def test_user_version(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        cache = PoiCache(db)
        assert _pragma(db, "user_version") == _SCHEMA_VERSION
        cache.close()

    def test_reopen_existing(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        PoiCache(db).close()
        cache = PoiCache(db)
        assert _pragma(db, "user_version") == _SCHEMA_VERSION
        assert _tables(db) >= {"tile", "poi"}
        cache.close()

    def test_foreign_keys_cascade(
        self, tmp_path: Path
    ) -> None:
        """Deleting a tile row cascades to its POI rows."""
        db = tmp_path / "poi.sqlite3"
        cache = PoiCache(db)
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO tile VALUES (1,2,0,100,100)"
        )
        conn.execute(
            "INSERT INTO poi VALUES"
            " (1,2,'n',99,48.0,11.0,'{}')"
        )
        conn.commit()
        conn.execute(
            "DELETE FROM tile WHERE x=1 AND y=2"
        )
        conn.commit()
        cnt = conn.execute(
            "SELECT count(*) FROM poi"
        ).fetchone()[0]
        assert cnt == 0
        conn.close()
        cache.close()


class TestRecovery:
    def test_wrong_version_recreates(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA user_version=999")
        conn.close()
        cache = PoiCache(db)
        assert _pragma(db, "user_version") == _SCHEMA_VERSION
        assert _tables(db) >= {"tile", "poi"}
        cache.close()

    def test_corrupt_file_recreates(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        db.write_bytes(b"not a database at all")
        cache = PoiCache(db)
        assert _pragma(db, "user_version") == _SCHEMA_VERSION
        assert _tables(db) >= {"tile", "poi"}
        cache.close()

    def test_old_version_data_cleared(
        self, tmp_path: Path
    ) -> None:
        """A version mismatch drops old data entirely."""
        db = tmp_path / "poi.sqlite3"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE leftover (id INTEGER)"
        )
        conn.execute("PRAGMA user_version=999")
        conn.commit()
        conn.close()
        cache = PoiCache(db)
        tables = _tables(db)
        assert "leftover" not in tables
        cache.close()


class TestClose:
    def test_close_is_idempotent(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        cache.close()
        cache.close()

    def test_path_survives_close(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "poi.sqlite3"
        cache = PoiCache(db)
        cache.close()
        assert cache.path == db


class TestFiltersHash:
    def test_same_input_same_output(self) -> None:
        f = ('[natural~"peak"]', '[tourism~"viewpoint"]')
        assert filters_hash(f) == filters_hash(f)

    def test_different_input_different_output(self) -> None:
        a = ('[natural~"peak"]',)
        b = ('[natural~"spring"]',)
        assert filters_hash(a) != filters_hash(b)

    def test_fits_in_32_bits(self) -> None:
        h = filters_hash(('[natural~"peak"]', '[historic]'))
        assert 0 <= h <= 0xFFFF_FFFF


_TILE_A = PoiTile(4200, 2800)
_TILE_B = PoiTile(4201, 2800)
_FHASH = 42


def _sample_pois() -> list[CachedPoi]:
    return [
        CachedPoi("n", 100, 48.0, 11.0, {"name": "Peak"}),
        CachedPoi("w", 200, 48.1, 11.1, {"tourism": "hut"}),
    ]


class TestPut:
    def test_put_then_get_returns_pois(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        pois = _sample_pois()
        cache.put(_TILE_A, pois, _FHASH)
        hits, missing, stale = cache.get(
            frozenset([_TILE_A]), _FHASH
        )
        assert _TILE_A in hits
        assert len(hits[_TILE_A]) == 2
        assert hits[_TILE_A][0].osm_id == 100
        assert hits[_TILE_A][1].tags == {"tourism": "hut"}
        assert missing == frozenset()
        assert stale == frozenset()
        cache.close()

    def test_put_replaces_previous(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        cache.put(_TILE_A, _sample_pois(), _FHASH)
        new_pois = [
            CachedPoi("r", 300, 48.2, 11.2, {"name": "Rel"})
        ]
        cache.put(_TILE_A, new_pois, _FHASH)
        hits, _, _ = cache.get(
            frozenset([_TILE_A]), _FHASH
        )
        assert len(hits[_TILE_A]) == 1
        assert hits[_TILE_A][0].osm_id == 300
        cache.close()

    def test_put_empty_poi_list(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        cache.put(_TILE_A, [], _FHASH)
        hits, missing, _ = cache.get(
            frozenset([_TILE_A]), _FHASH
        )
        assert _TILE_A in hits
        assert hits[_TILE_A] == []
        assert missing == frozenset()
        cache.close()

    def test_put_preserves_unicode_tags(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        pois = [
            CachedPoi(
                "n", 1, 48.0, 11.0,
                {"name": "Zugspitze", "name:de": "Zugspitze"}
            ),
        ]
        cache.put(_TILE_A, pois, _FHASH)
        hits, _, _ = cache.get(
            frozenset([_TILE_A]), _FHASH
        )
        assert hits[_TILE_A][0].tags["name:de"] == "Zugspitze"
        cache.close()


class TestGet:
    def test_missing_tile(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        hits, missing, stale = cache.get(
            frozenset([_TILE_A]), _FHASH
        )
        assert hits == {}
        assert _TILE_A in missing
        assert stale == frozenset()
        cache.close()

    def test_wrong_filter_hash_is_missing(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        cache.put(_TILE_A, _sample_pois(), _FHASH)
        hits, missing, stale = cache.get(
            frozenset([_TILE_A]), _FHASH + 1
        )
        assert hits == {}
        assert _TILE_A in missing
        cache.close()

    def test_stale_tile(
        self, tmp_path: Path
    ) -> None:
        """A tile older than TILE_TTL_S appears in both hits
        and stale."""
        cache = PoiCache(tmp_path / "poi.sqlite3")
        old_time = time.time() - TILE_TTL_S - 1
        with patch(
            "backpack.storage.poi_cache.time.time",
            return_value=old_time,
        ):
            cache.put(_TILE_A, _sample_pois(), _FHASH)
        hits, missing, stale = cache.get(
            frozenset([_TILE_A]), _FHASH
        )
        assert _TILE_A in hits
        assert _TILE_A in stale
        assert missing == frozenset()
        cache.close()

    def test_fresh_tile_not_stale(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        cache.put(_TILE_A, _sample_pois(), _FHASH)
        hits, missing, stale = cache.get(
            frozenset([_TILE_A]), _FHASH
        )
        assert _TILE_A in hits
        assert stale == frozenset()
        cache.close()

    def test_multiple_tiles_mixed(
        self, tmp_path: Path
    ) -> None:
        """Request two tiles; one cached, one missing."""
        cache = PoiCache(tmp_path / "poi.sqlite3")
        cache.put(_TILE_A, _sample_pois(), _FHASH)
        hits, missing, stale = cache.get(
            frozenset([_TILE_A, _TILE_B]), _FHASH
        )
        assert _TILE_A in hits
        assert _TILE_B in missing
        assert stale == frozenset()
        cache.close()

    def test_get_empty_set(
        self, tmp_path: Path
    ) -> None:
        cache = PoiCache(tmp_path / "poi.sqlite3")
        hits, missing, stale = cache.get(
            frozenset(), _FHASH
        )
        assert hits == {}
        assert missing == frozenset()
        assert stale == frozenset()
        cache.close()
