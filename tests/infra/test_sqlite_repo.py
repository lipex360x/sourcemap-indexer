from __future__ import annotations

import time

from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import (
    ContentHash,
    ItemId,
    Language,
    Layer,
    SideEffect,
    Stability,
)
from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Right


def _make_item(
    path: str = "src/app.py",
    language: Language = Language.PY,
) -> Item:
    return Item(
        id=ItemId.generate(),
        path=path,
        name=path.split("/")[-1],
        language=language,
        lines=10,
        size_bytes=200,
        content_hash=ContentHash("a" * 64),
        last_modified=int(time.time()),
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )


def _make_repo() -> SqliteItemRepository:
    from pathlib import Path

    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    return SqliteItemRepository(result.value)


def test_upsert_new_item_returns_right() -> None:
    repo = _make_repo()
    item = _make_item()
    result = repo.upsert(item)
    assert isinstance(result, Right)
    assert result.value.id == item.id


def test_find_by_path_returns_item_after_upsert() -> None:
    repo = _make_repo()
    item = _make_item(path="src/main.py")
    repo.upsert(item)
    result = repo.find_by_path("src/main.py")
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.path == "src/main.py"


def test_find_by_path_returns_none_for_missing() -> None:
    repo = _make_repo()
    result = repo.find_by_path("not/exists.py")
    assert isinstance(result, Right)
    assert result.value is None


def test_upsert_updates_existing_item() -> None:
    repo = _make_repo()
    item = _make_item(path="src/app.py")
    repo.upsert(item)
    updated = Item(
        id=item.id,
        path=item.path,
        name=item.name,
        language=item.language,
        lines=99,
        size_bytes=999,
        content_hash=ContentHash("b" * 64),
        last_modified=item.last_modified,
        created_at=item.created_at,
        updated_at=int(time.time()),
    )
    repo.upsert(updated)
    result = repo.find_by_path("src/app.py")
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.lines == 99
    assert result.value.content_hash.hex_value == "b" * 64


def test_find_by_id_returns_item() -> None:
    repo = _make_repo()
    item = _make_item()
    repo.upsert(item)
    result = repo.find_by_id(item.id)
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.id == item.id


def test_find_by_id_returns_none_for_missing() -> None:
    repo = _make_repo()
    result = repo.find_by_id(ItemId.generate())
    assert isinstance(result, Right)
    assert result.value is None


def test_find_needs_llm_returns_items_with_flag_true() -> None:
    repo = _make_repo()
    needs = _make_item(path="a.py")
    done = Item(
        id=ItemId.generate(),
        path="b.py",
        name="b.py",
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("c" * 64),
        last_modified=0,
        needs_llm=False,
        created_at=0,
        updated_at=0,
    )
    repo.upsert(needs)
    repo.upsert(done)
    result = repo.find_needs_llm()
    assert isinstance(result, Right)
    paths = [i.path for i in result.value]
    assert "a.py" in paths
    assert "b.py" not in paths


def test_find_needs_llm_respects_limit() -> None:
    repo = _make_repo()
    for i in range(5):
        repo.upsert(_make_item(path=f"file{i}.py"))
    result = repo.find_needs_llm(limit=2)
    assert isinstance(result, Right)
    assert len(result.value) == 2


def test_find_all_paths_returns_active_paths() -> None:
    repo = _make_repo()
    repo.upsert(_make_item(path="x.py"))
    repo.upsert(_make_item(path="y.py"))
    result = repo.find_all_paths()
    assert isinstance(result, Right)
    assert {"x.py", "y.py"}.issubset(result.value)


def test_soft_delete_sets_deleted_at() -> None:
    repo = _make_repo()
    item = _make_item(path="gone.py")
    repo.upsert(item)
    deleted_ts = int(time.time())
    result = repo.soft_delete(item.id, deleted_ts)
    assert isinstance(result, Right)
    found = repo.find_by_path("gone.py")
    assert isinstance(found, Right)
    assert found.value is None


def test_find_all_paths_excludes_deleted() -> None:
    repo = _make_repo()
    item = _make_item(path="deleted.py")
    repo.upsert(item)
    repo.soft_delete(item.id, int(time.time()))
    result = repo.find_all_paths()
    assert isinstance(result, Right)
    assert "deleted.py" not in result.value


def test_tags_round_trip() -> None:
    repo = _make_repo()
    item = Item(
        id=ItemId.generate(),
        path="tagged.py",
        name="tagged.py",
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("d" * 64),
        last_modified=0,
        tags=frozenset({"alpha", "beta"}),
        created_at=0,
        updated_at=0,
    )
    repo.upsert(item)
    result = repo.find_by_path("tagged.py")
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.tags == frozenset({"alpha", "beta"})


def test_side_effects_round_trip() -> None:
    repo = _make_repo()
    item = Item(
        id=ItemId.generate(),
        path="effectful.py",
        name="effectful.py",
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("e" * 64),
        last_modified=0,
        side_effects=frozenset({SideEffect.WRITES_FS, SideEffect.GIT}),
        created_at=0,
        updated_at=0,
    )
    repo.upsert(item)
    result = repo.find_by_path("effectful.py")
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.side_effects == frozenset({SideEffect.WRITES_FS, SideEffect.GIT})


def test_invariants_round_trip() -> None:
    repo = _make_repo()
    item = Item(
        id=ItemId.generate(),
        path="invariant.py",
        name="invariant.py",
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("f" * 64),
        last_modified=0,
        invariants=("must be idempotent", "no side effects"),
        created_at=0,
        updated_at=0,
    )
    repo.upsert(item)
    result = repo.find_by_path("invariant.py")
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.invariants == ("must be idempotent", "no side effects")


def test_search_no_filters_returns_all_active() -> None:
    repo = _make_repo()
    repo.upsert(_make_item(path="a.py"))
    repo.upsert(_make_item(path="b.py"))
    deleted = _make_item(path="c.py")
    repo.upsert(deleted)
    repo.soft_delete(deleted.id, int(time.time()))
    result = repo.search(tags=None, layer=None, language=None)
    assert isinstance(result, Right)
    paths = [i.path for i in result.value]
    assert "a.py" in paths
    assert "b.py" in paths
    assert "c.py" not in paths


def test_search_filter_by_language() -> None:
    repo = _make_repo()
    repo.upsert(_make_item(path="app.py", language=Language.PY))
    repo.upsert(_make_item(path="app.ts", language=Language.TS))
    result = repo.search(tags=None, layer=None, language=Language.TS)
    assert isinstance(result, Right)
    paths = [i.path for i in result.value]
    assert "app.ts" in paths
    assert "app.py" not in paths


def test_search_filter_by_layer() -> None:
    repo = _make_repo()
    domain_item = Item(
        id=ItemId.generate(),
        path="domain/entity.py",
        name="entity.py",
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("1" * 64),
        last_modified=0,
        layer=Layer.DOMAIN,
        created_at=0,
        updated_at=0,
    )
    repo.upsert(domain_item)
    repo.upsert(_make_item(path="other.py"))
    result = repo.search(tags=None, layer=Layer.DOMAIN, language=None)
    assert isinstance(result, Right)
    paths = [i.path for i in result.value]
    assert "domain/entity.py" in paths
    assert "other.py" not in paths


def test_search_filter_by_tags() -> None:
    repo = _make_repo()
    tagged = Item(
        id=ItemId.generate(),
        path="tagged.py",
        name="tagged.py",
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("2" * 64),
        last_modified=0,
        tags=frozenset({"auth", "jwt"}),
        created_at=0,
        updated_at=0,
    )
    repo.upsert(tagged)
    repo.upsert(_make_item(path="plain.py"))
    result = repo.search(tags=["auth"], layer=None, language=None)
    assert isinstance(result, Right)
    paths = [i.path for i in result.value]
    assert "tagged.py" in paths
    assert "plain.py" not in paths


def test_llm_hash_round_trip() -> None:
    repo = _make_repo()
    item = Item(
        id=ItemId.generate(),
        path="enriched.py",
        name="enriched.py",
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("a" * 64),
        last_modified=0,
        needs_llm=False,
        llm_hash=ContentHash("b" * 64),
        llm_at=12345,
        layer=Layer.DOMAIN,
        stability=Stability.STABLE,
        created_at=0,
        updated_at=0,
    )
    repo.upsert(item)
    result = repo.find_by_path("enriched.py")
    assert isinstance(result, Right)
    found = result.value
    assert found is not None
    assert found.llm_hash is not None
    assert found.llm_hash.hex_value == "b" * 64
    assert found.llm_at == 12345
    assert found.layer == Layer.DOMAIN
    assert found.stability == Stability.STABLE
