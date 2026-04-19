from __future__ import annotations

import importlib.resources
import sqlite3
import time
from pathlib import Path

from sourcemap_indexer.lib.either import Either, left, right


def _load_migration(name: str) -> str:
    package = importlib.resources.files("sourcemap_indexer.infra.migrations")
    return (package / name).read_text(encoding="utf-8")


def _apply_pending(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS _migrations "
        "(name TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    applied = {row[0] for row in connection.execute("SELECT name FROM _migrations").fetchall()}
    migrations = ["001_init.sql"]
    for name in migrations:
        if name in applied:
            continue
        sql = _load_migration(name)
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO _migrations (name, applied_at) VALUES (?, ?)",
            (name, int(time.time())),
        )
    connection.commit()


def init_db(db_path: Path) -> Either[str, sqlite3.Connection]:
    try:
        connection = sqlite3.connect(str(db_path))
        connection.execute("PRAGMA foreign_keys = ON")
        _apply_pending(connection)
        return right(connection)
    except sqlite3.OperationalError as error:
        return left(f"db-error: {error}")
