"""Tests for backpack.storage.poi_cache - SQLite POI cache lifecycle."""
import sqlite3
from pathlib import Path

from backpack.storage.poi_cache import (
    PoiCache,
    _SCHEMA_VERSION,
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
