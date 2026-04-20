from __future__ import annotations

from dataclasses import dataclass, replace

from sourcemap_indexer.domain.value_objects import (
    ContentHash,
    ItemId,
    Language,
    Layer,
    SideEffect,
    Stability,
)


@dataclass(frozen=True, slots=True)
class Item:
    id: ItemId
    path: str
    name: str
    language: Language
    lines: int
    size_bytes: int
    content_hash: ContentHash
    last_modified: int
    entry_point: bool = False
    has_test: bool | None = None
    test_path: str | None = None
    purpose: str | None = None
    layer: Layer = "unknown"
    stability: Stability = Stability.UNKNOWN
    tags: frozenset[str] = frozenset()
    side_effects: frozenset[SideEffect] = frozenset()
    invariants: tuple[str, ...] = ()
    needs_llm: bool = True
    llm_hash: ContentHash | None = None
    llm_at: int | None = None
    deleted_at: int | None = None
    created_at: int = 0
    updated_at: int = 0

    def with_llm_enrichment(
        self,
        purpose: str,
        layer: Layer,
        stability: Stability,
        tags: frozenset[str],
        side_effects: frozenset[SideEffect],
        invariants: tuple[str, ...],
        llm_at: int,
    ) -> Item:
        return replace(
            self,
            purpose=purpose,
            layer=layer,
            stability=stability,
            tags=tags,
            side_effects=side_effects,
            invariants=invariants,
            needs_llm=False,
            llm_hash=self.content_hash,
            llm_at=llm_at,
        )
