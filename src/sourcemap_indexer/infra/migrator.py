from __future__ import annotations

import importlib.resources
import sqlite3
import time
from pathlib import Path

from sourcemap_indexer.lib.either import Either, left, right


def _load_migration(name: str) -> str:
    package = importlib.resources.files("sourcemap_indexer.infra.migrations")
    return (package / name).read_text(encoding="utf-8")


def _run_migration(connection: sqlite3.Connection, name: str) -> None:
    for statement in _load_migration(name).split(";"):
        stripped = statement.strip()
        if stripped:
            connection.execute(stripped)
    connection.execute(
        "INSERT INTO _migrations (name, applied_at) VALUES (?, ?)",
        (name, int(time.time())),
    )


def _apply_pending(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS _migrations "
        "(name TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    try:
        applied = {row[0] for row in connection.execute("SELECT name FROM _migrations").fetchall()}
        for name in ["001_init.sql"]:
            if name not in applied:
                _run_migration(connection, name)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def init_db(db_path: Path) -> Either[str, sqlite3.Connection]:
    try:
        connection = sqlite3.connect(str(db_path))
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        _apply_pending(connection)
        return right(connection)
    except sqlite3.OperationalError as error:
        return left(f"db-error: {error}")
