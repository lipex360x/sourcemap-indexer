from __future__ import annotations

import sqlite3
from typing import Any

from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import (
    ContentHash,
    ItemId,
    Language,
    Layer,
    SideEffect,
    Stability,
)
from sourcemap_indexer.lib.either import Either, left, right


def _row_to_item(row: dict[str, Any], connection: sqlite3.Connection) -> Item:
    item_id = row["id"]
    tags_rows = connection.execute("SELECT tag FROM tags WHERE item_id = ?", (item_id,)).fetchall()
    effects_rows = connection.execute(
        "SELECT effect FROM side_effects WHERE item_id = ?", (item_id,)
    ).fetchall()
    invariants_rows = connection.execute(
        "SELECT invariant FROM invariants WHERE item_id = ? ORDER BY position",
        (item_id,),
    ).fetchall()

    llm_hash = ContentHash(row["llm_hash"]) if row["llm_hash"] else None
    return Item(
        id=ItemId(row["id"]),
        path=row["path"],
        name=row["name"],
        language=Language(row["language"]),
        lines=row["lines"],
        size_bytes=row["size_bytes"],
        content_hash=ContentHash(row["content_hash"]),
        last_modified=row["last_modified"],
        entry_point=bool(row["entry_point"]),
        has_test=None if row["has_test"] is None else bool(row["has_test"]),
        test_path=row["test_path"],
        purpose=row["purpose"],
        layer=Layer(row["layer"]),
        stability=Stability(row["stability"]),
        tags=frozenset(r[0] for r in tags_rows),
        side_effects=frozenset(SideEffect(r[0]) for r in effects_rows),
        invariants=tuple(r[0] for r in invariants_rows),
        needs_llm=bool(row["needs_llm"]),
        llm_hash=llm_hash,
        llm_at=row["llm_at"],
        deleted_at=row["deleted_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqliteItemRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row

    def upsert(self, item: Item) -> Either[str, Item]:
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO items (
                        id, path, name, language, lines, size_bytes,
                        content_hash, last_modified, entry_point, has_test,
                        test_path, purpose, layer, stability, needs_llm,
                        llm_hash, llm_at, deleted_at, created_at, updated_at
                    ) VALUES (
                        :id, :path, :name, :language, :lines, :size_bytes,
                        :content_hash, :last_modified, :entry_point, :has_test,
                        :test_path, :purpose, :layer, :stability, :needs_llm,
                        :llm_hash, :llm_at, :deleted_at, :created_at, :updated_at
                    )
                    ON CONFLICT(path) DO UPDATE SET
                        id=excluded.id,
                        name=excluded.name,
                        language=excluded.language,
                        lines=excluded.lines,
                        size_bytes=excluded.size_bytes,
                        content_hash=excluded.content_hash,
                        last_modified=excluded.last_modified,
                        entry_point=excluded.entry_point,
                        has_test=excluded.has_test,
                        test_path=excluded.test_path,
                        purpose=excluded.purpose,
                        layer=excluded.layer,
                        stability=excluded.stability,
                        needs_llm=excluded.needs_llm,
                        llm_hash=excluded.llm_hash,
                        llm_at=excluded.llm_at,
                        deleted_at=excluded.deleted_at,
                        updated_at=excluded.updated_at
                    """,
                    {
                        "id": item.id.uuid_str,
                        "path": item.path,
                        "name": item.name,
                        "language": str(item.language),
                        "lines": item.lines,
                        "size_bytes": item.size_bytes,
                        "content_hash": item.content_hash.hex_value,
                        "last_modified": item.last_modified,
                        "entry_point": int(item.entry_point),
                        "has_test": None if item.has_test is None else int(item.has_test),
                        "test_path": item.test_path,
                        "purpose": item.purpose,
                        "layer": str(item.layer),
                        "stability": str(item.stability),
                        "needs_llm": int(item.needs_llm),
                        "llm_hash": item.llm_hash.hex_value if item.llm_hash else None,
                        "llm_at": item.llm_at,
                        "deleted_at": item.deleted_at,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    },
                )
                self._connection.execute("DELETE FROM tags WHERE item_id = ?", (item.id.uuid_str,))
                self._connection.executemany(
                    "INSERT INTO tags (item_id, tag) VALUES (?, ?)",
                    [(item.id.uuid_str, tag) for tag in item.tags],
                )
                self._connection.execute(
                    "DELETE FROM side_effects WHERE item_id = ?", (item.id.uuid_str,)
                )
                self._connection.executemany(
                    "INSERT INTO side_effects (item_id, effect) VALUES (?, ?)",
                    [(item.id.uuid_str, str(effect)) for effect in item.side_effects],
                )
                self._connection.execute(
                    "DELETE FROM invariants WHERE item_id = ?", (item.id.uuid_str,)
                )
                self._connection.executemany(
                    "INSERT INTO invariants (item_id, position, invariant) VALUES (?, ?, ?)",
                    [(item.id.uuid_str, pos, inv) for pos, inv in enumerate(item.invariants)],
                )
            return right(item)
        except sqlite3.Error as error:
            return left(f"db-error: {error}")

    def find_by_path(self, path: str) -> Either[str, Item | None]:
        try:
            row = self._connection.execute(
                "SELECT * FROM items WHERE path = ? AND deleted_at IS NULL", (path,)
            ).fetchone()
            if row is None:
                return right(None)
            return right(_row_to_item(dict(row), self._connection))
        except sqlite3.Error as error:
            return left(f"db-error: {error}")

    def find_by_id(self, item_id: ItemId) -> Either[str, Item | None]:
        try:
            row = self._connection.execute(
                "SELECT * FROM items WHERE id = ? AND deleted_at IS NULL",
                (item_id.uuid_str,),
            ).fetchone()
            if row is None:
                return right(None)
            return right(_row_to_item(dict(row), self._connection))
        except sqlite3.Error as error:
            return left(f"db-error: {error}")

    def find_needs_llm(
        self,
        limit: int | None = None,
        force: bool = False,
        layer: Layer | None = None,
        language: Language | None = None,
    ) -> Either[str, list[Item]]:
        try:
            conditions = ["deleted_at IS NULL"]
            params: list[Any] = []
            if not force:
                conditions.append("needs_llm = 1")
            if layer is not None:
                conditions.append("layer = ?")
                params.append(str(layer))
            if language is not None:
                conditions.append("language = ?")
                params.append(str(language))
            query = "SELECT * FROM items WHERE " + " AND ".join(conditions)
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            rows = self._connection.execute(query, params).fetchall()
            return right([_row_to_item(dict(row), self._connection) for row in rows])
        except sqlite3.Error as error:
            return left(f"db-error: {error}")

    def find_all_paths(self) -> Either[str, set[str]]:
        try:
            rows = self._connection.execute(
                "SELECT path FROM items WHERE deleted_at IS NULL"
            ).fetchall()
            return right({row[0] for row in rows})
        except sqlite3.Error as error:
            return left(f"db-error: {error}")

    def soft_delete(self, item_id: ItemId, deleted_at: int) -> Either[str, None]:
        try:
            with self._connection:
                self._connection.execute(
                    "UPDATE items SET deleted_at = ? WHERE id = ?",
                    (deleted_at, item_id.uuid_str),
                )
            return right(None)
        except sqlite3.Error as error:
            return left(f"db-error: {error}")

    def search(
        self,
        tags: list[str] | None,
        layer: Layer | None,
        language: Language | None,
    ) -> Either[str, list[Item]]:
        try:
            conditions = ["i.deleted_at IS NULL"]
            params: list[Any] = []
            if layer is not None:
                conditions.append("i.layer = ?")
                params.append(str(layer))
            if language is not None:
                conditions.append("i.language = ?")
                params.append(str(language))
            where = " AND ".join(conditions)
            if tags:
                placeholders = ", ".join("?" for _ in tags)
                query = f"""
                    SELECT DISTINCT i.* FROM items i
                    JOIN tags t ON t.item_id = i.id
                    WHERE {where} AND t.tag IN ({placeholders})
                """
                params.extend(tags)
            else:
                query = f"SELECT * FROM items i WHERE {where}"
            rows = self._connection.execute(query, params).fetchall()
            return right([_row_to_item(dict(row), self._connection) for row in rows])
        except sqlite3.Error as error:
            return left(f"db-error: {error}")
