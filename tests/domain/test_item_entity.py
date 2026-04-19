from __future__ import annotations

import dataclasses

import pytest

from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import (
    ContentHash,
    ItemId,
    Language,
    Layer,
    SideEffect,
    Stability,
)
from sourcemap_indexer.lib.either import Right


@pytest.fixture
def content_hash() -> ContentHash:
    result = ContentHash.from_bytes(b"test")
    assert isinstance(result, Right)
    return result.value


@pytest.fixture
def item_id() -> ItemId:
    return ItemId.generate()


@pytest.fixture
def sample_item(content_hash: ContentHash, item_id: ItemId) -> Item:
    return Item(
        id=item_id,
        path="src/foo.py",
        name="foo.py",
        language=Language.PY,
        lines=42,
        size_bytes=1024,
        content_hash=content_hash,
        last_modified=1000000,
        created_at=1000000,
        updated_at=1000000,
    )


def test_item_construction_defaults(sample_item: Item) -> None:
    assert sample_item.needs_llm is True
    assert sample_item.layer == Layer.UNKNOWN
    assert sample_item.stability == Stability.UNKNOWN
    assert sample_item.tags == frozenset()
    assert sample_item.side_effects == frozenset()
    assert sample_item.invariants == ()
    assert sample_item.purpose is None
    assert sample_item.entry_point is False


def test_item_construction_explicit_fields(
    sample_item: Item, item_id: ItemId, content_hash: ContentHash
) -> None:
    assert sample_item.path == "src/foo.py"
    assert sample_item.name == "foo.py"
    assert sample_item.language == Language.PY
    assert sample_item.lines == 42
    assert sample_item.size_bytes == 1024
    assert sample_item.content_hash == content_hash
    assert sample_item.last_modified == 1000000
    assert sample_item.id == item_id


def test_item_is_immutable(sample_item: Item) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample_item.path = "other.py"  # type: ignore[misc]


def test_with_llm_enrichment_returns_updated_item(
    sample_item: Item, content_hash: ContentHash
) -> None:
    enriched = sample_item.with_llm_enrichment(
        purpose="Does something useful",
        layer=Layer.APPLICATION,
        stability=Stability.STABLE,
        tags=frozenset({"feature", "utility"}),
        side_effects=frozenset({SideEffect.WRITES_FS}),
        invariants=("must not be empty",),
        llm_at=2000000,
    )
    assert enriched.purpose == "Does something useful"
    assert enriched.layer == Layer.APPLICATION
    assert enriched.stability == Stability.STABLE
    assert enriched.tags == frozenset({"feature", "utility"})
    assert enriched.side_effects == frozenset({SideEffect.WRITES_FS})
    assert enriched.invariants == ("must not be empty",)
    assert enriched.needs_llm is False
    assert enriched.llm_hash == content_hash
    assert enriched.llm_at == 2000000


def test_with_llm_enrichment_does_not_mutate_original(sample_item: Item) -> None:
    enriched = sample_item.with_llm_enrichment(
        purpose="test",
        layer=Layer.APPLICATION,
        stability=Stability.STABLE,
        tags=frozenset(),
        side_effects=frozenset(),
        invariants=(),
        llm_at=2000000,
    )
    assert sample_item.purpose is None
    assert sample_item.needs_llm is True
    assert enriched is not sample_item


def test_with_llm_enrichment_preserves_structural_fields(sample_item: Item) -> None:
    enriched = sample_item.with_llm_enrichment(
        purpose="test",
        layer=Layer.APPLICATION,
        stability=Stability.STABLE,
        tags=frozenset(),
        side_effects=frozenset(),
        invariants=(),
        llm_at=2000000,
    )
    assert enriched.path == sample_item.path
    assert enriched.language == sample_item.language
    assert enriched.lines == sample_item.lines
    assert enriched.content_hash == sample_item.content_hash
    assert enriched.llm_hash == sample_item.content_hash
