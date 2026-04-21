from __future__ import annotations

import time
from pathlib import Path

import pytest

from sourcemap_indexer.application.enrich import _topologically_ordered
from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import ContentHash, ItemId, Language


def _item(path: str, language: Language = Language.PY) -> Item:
    return Item(
        id=ItemId.generate(),
        path=path,
        name=path.split("/")[-1],
        language=language,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("a" * 64),
        last_modified=int(time.time()),
        needs_llm=True,
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )


def _write(root: Path, path: str, content: str = "") -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _extractor_from_map(dep_map: dict[str, list[str]]):
    def extract(content: str, file_path: str) -> list[str]:
        return dep_map.get(file_path, [])

    return extract


def test_empty_list_returns_empty(tmp_path: Path) -> None:
    result = _topologically_ordered([], {}, tmp_path)
    assert result == []


def test_single_item_returned_as_is(tmp_path: Path) -> None:
    item = _item("a.py")
    _write(tmp_path, "a.py")
    result = _topologically_ordered([item], {Language.PY: _extractor_from_map({})}, tmp_path)
    assert result == [item]


def test_leaf_before_dependent(tmp_path: Path) -> None:
    leaf = _item("a.py")
    dependent = _item("b.py")
    _write(tmp_path, "a.py")
    _write(tmp_path, "b.py", "from a import x")
    dep_map = {"a.py": [], "b.py": ["a.py"]}
    extractors = {Language.PY: _extractor_from_map(dep_map)}
    result = _topologically_ordered([dependent, leaf], extractors, tmp_path)
    assert result.index(leaf) < result.index(dependent)


def test_three_level_chain_ordered_correctly(tmp_path: Path) -> None:
    item_a = _item("a.py")
    item_b = _item("b.py")
    item_c = _item("c.py")
    _write(tmp_path, "a.py")
    _write(tmp_path, "b.py", "from a import x")
    _write(tmp_path, "c.py", "from b import y")
    dep_map = {"a.py": [], "b.py": ["a.py"], "c.py": ["b.py"]}
    extractors = {Language.PY: _extractor_from_map(dep_map)}
    result = _topologically_ordered([item_c, item_b, item_a], extractors, tmp_path)
    assert result.index(item_a) < result.index(item_b)
    assert result.index(item_b) < result.index(item_c)


def test_cycle_returns_all_items_without_crash(tmp_path: Path) -> None:
    item_a = _item("a.py")
    item_b = _item("b.py")
    _write(tmp_path, "a.py", "from b import y")
    _write(tmp_path, "b.py", "from a import x")
    dep_map = {"a.py": ["b.py"], "b.py": ["a.py"]}
    extractors = {Language.PY: _extractor_from_map(dep_map)}
    result = _topologically_ordered([item_a, item_b], extractors, tmp_path)
    assert set(result) == {item_a, item_b}
    assert len(result) == 2


def test_missing_extractor_places_item_in_tier_zero(tmp_path: Path) -> None:
    js_item = _item("app.js", Language.JS)
    py_item = _item("main.py", Language.PY)
    _write(tmp_path, "app.js")
    _write(tmp_path, "main.py", "import app")
    dep_map = {"main.py": ["app.js"]}
    extractors = {Language.PY: _extractor_from_map(dep_map)}
    result = _topologically_ordered([py_item, js_item], extractors, tmp_path)
    assert js_item in result
    assert py_item in result
    assert len(result) == 2


def test_oserror_on_read_treats_item_as_leaf(tmp_path: Path) -> None:
    missing = _item("ghost.py")
    dependent = _item("main.py")
    _write(tmp_path, "main.py", "from ghost import x")
    dep_map = {"main.py": ["ghost.py"]}
    extractors = {Language.PY: _extractor_from_map(dep_map)}
    result = _topologically_ordered([dependent, missing], extractors, tmp_path)
    assert missing in result
    assert dependent in result
    assert len(result) == 2


def test_extractor_raises_syntax_error_treats_item_as_leaf(tmp_path: Path) -> None:
    broken = _item("broken.py")
    dependent = _item("main.py")
    _write(tmp_path, "broken.py", "def")
    _write(tmp_path, "main.py", "from broken import x")

    def _raising_extractor(content: str, file_path: str) -> list[str]:
        if "def" in content and not content.strip().endswith(":"):
            raise SyntaxError("invalid syntax")
        return []

    extractors = {Language.PY: _raising_extractor}
    result = _topologically_ordered([dependent, broken], extractors, tmp_path)
    assert broken in result
    assert dependent in result
    assert len(result) == 2


def test_deps_outside_pending_set_are_ignored(tmp_path: Path) -> None:
    already_enriched_path = "already_done.py"
    item = _item("main.py")
    _write(tmp_path, "main.py", "from already_done import x")
    dep_map = {"main.py": [already_enriched_path]}
    extractors = {Language.PY: _extractor_from_map(dep_map)}
    result = _topologically_ordered([item], extractors, tmp_path)
    assert result == [item]


def test_stable_order_within_tier(tmp_path: Path) -> None:
    items = [_item(f"file{i}.py") for i in range(5)]
    for item in items:
        _write(tmp_path, item.path)
    extractors = {Language.PY: _extractor_from_map({})}
    result = _topologically_ordered(items, extractors, tmp_path)
    assert result == items


@pytest.mark.parametrize("count", [1, 2, 10])
def test_result_contains_all_items(tmp_path: Path, count: int) -> None:
    items = [_item(f"file{i}.py") for i in range(count)]
    for item in items:
        _write(tmp_path, item.path)
    extractors = {Language.PY: _extractor_from_map({})}
    result = _topologically_ordered(items, extractors, tmp_path)
    assert len(result) == count
    assert set(result) == set(items)
