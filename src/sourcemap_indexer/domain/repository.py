from __future__ import annotations

from typing import Protocol

from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import ItemId, Language, Layer
from sourcemap_indexer.lib.either import Either


class ItemRepository(Protocol):
    def upsert(self, item: Item) -> Either[str, Item]: ...

    def find_by_path(self, path: str) -> Either[str, Item | None]: ...

    def find_by_id(self, item_id: ItemId) -> Either[str, Item | None]: ...

    def find_needs_llm(
        self,
        limit: int | None = None,
        force: bool = False,
        layer: Layer | None = None,
        language: Language | None = None,
    ) -> Either[str, list[Item]]: ...

    def find_all_paths(self) -> Either[str, set[str]]: ...

    def soft_delete(self, item_id: ItemId, deleted_at: int) -> Either[str, None]: ...

    def search(
        self,
        tags: list[str] | None,
        layer: Layer | None,
        language: Language | None,
    ) -> Either[str, list[Item]]: ...
