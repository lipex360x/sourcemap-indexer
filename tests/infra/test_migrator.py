from __future__ import annotations

from pathlib import Path

from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.lib.either import Left, Right


def test_init_db_returns_right_for_memory() -> None:
    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    result.value.close()


def test_init_db_creates_items_table() -> None:
    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    connection = result.value
    cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "items" in tables
    assert "tags" in tables
    assert "side_effects" in tables
    assert "invariants" in tables
    assert "_migrations" in tables
    connection.close()


def test_init_db_records_migration() -> None:
    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    connection = result.value
    cursor = connection.execute("SELECT name FROM _migrations")
    names = [row[0] for row in cursor.fetchall()]
    assert "001_init.sql" in names
    connection.close()


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    first = init_db(db_path)
    assert isinstance(first, Right)
    first.value.close()
    second = init_db(db_path)
    assert isinstance(second, Right)
    connection = second.value
    cursor = connection.execute("SELECT COUNT(*) FROM _migrations WHERE name = '001_init.sql'")
    assert cursor.fetchone()[0] == 1
    connection.close()


def test_init_db_enables_foreign_keys() -> None:
    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    connection = result.value
    cursor = connection.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    connection.close()


def test_init_db_returns_left_for_invalid_path() -> None:
    result = init_db(Path("/nonexistent_dir/that/does/not/exist/test.db"))
    assert isinstance(result, Left)
    assert result.error.startswith("db-error")
