from __future__ import annotations

import threading
from pathlib import Path

import pytest

from sourcemap_indexer.infra.db.migrator import init_db
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


def test_apply_pending_rolls_back_on_migration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3  # noqa: PLC0415

    import sourcemap_indexer.infra.db.migrator as migrator_mod  # noqa: PLC0415

    def _raise(_conn: object, _name: object) -> None:
        raise sqlite3.OperationalError("simulated-failure")

    monkeypatch.setattr(migrator_mod, "_run_migration", _raise)
    db_path = tmp_path / "test.db"
    result = init_db(db_path)
    assert isinstance(result, Left)
    assert "db-error" in result.error


def test_init_db_is_safe_under_concurrent_calls(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.db"
    failures: list[BaseException] = []

    def run() -> None:
        try:
            outcome = init_db(db_path)
            if isinstance(outcome, Right):
                outcome.value.close()
        except Exception as thrown:
            failures.append(thrown)

    first_thread = threading.Thread(target=run)
    second_thread = threading.Thread(target=run)
    first_thread.start()
    second_thread.start()
    first_thread.join()
    second_thread.join()

    assert not failures, f"thread raised: {failures[0]}"

    verification = init_db(db_path)
    assert isinstance(verification, Right)
    counter = verification.value.execute("SELECT COUNT(*) FROM _migrations")
    count = counter.fetchone()[0]
    verification.value.close()
    assert count == 1
