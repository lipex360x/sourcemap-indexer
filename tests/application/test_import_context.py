from __future__ import annotations

import time
from pathlib import Path

import pytest

from sourcemap_indexer.application.import_context import resolve_import_context
from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import ContentHash, ItemId, Language, Stability
from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Right


def _make_repo() -> SqliteItemRepository:
    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    return SqliteItemRepository(result.value)


def _make_item(path: str, language: Language = Language.PY) -> Item:
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


def _make_enriched_item(path: str, purpose: str) -> Item:
    base = _make_item(path)
    return base.with_llm_enrichment(
        purpose=purpose,
        layer="domain",
        stability=Stability.STABLE,
        tags=frozenset(),
        side_effects=frozenset(),
        invariants=(),
        llm_at=int(time.time()),
    )


def test_enriched_import_appears_in_block() -> None:
    repo = _make_repo()
    repo.upsert(_make_enriched_item("my_domain/entity.py", "Domain entity for orders"))
    item = _make_item("src/app.py")
    content = "from my_domain.entity import Entity\n"
    result = resolve_import_context(item, content, repo, max_chars=5000)
    assert "Context from direct imports:" in result
    assert "my_domain/entity.py" in result
    assert "Domain entity for orders" in result


def test_unenriched_import_silently_skipped() -> None:
    repo = _make_repo()
    repo.upsert(_make_item("my_domain/entity.py"))
    item = _make_item("src/app.py")
    content = "from my_domain.entity import Entity\n"
    result = resolve_import_context(item, content, repo, max_chars=5000)
    assert result == ""


def test_absent_import_silently_skipped() -> None:
    repo = _make_repo()
    item = _make_item("src/app.py")
    content = "from my_domain.entity import Entity\n"
    result = resolve_import_context(item, content, repo, max_chars=5000)
    assert result == ""


def test_unknown_language_returns_empty_string() -> None:
    repo = _make_repo()
    item = _make_item("src/script.sh", Language.SH)
    content = "import my_module\n"
    result = resolve_import_context(item, content, repo, max_chars=5000)
    assert result == ""


def test_max_chars_drops_whole_lines_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo()
    repo.upsert(_make_enriched_item("mod_one/util.py", "A" * 50))
    repo.upsert(_make_enriched_item("mod_two/helper.py", "B" * 50))
    item = _make_item("src/app.py")
    content = "from mod_one.util import foo\nfrom mod_two.helper import bar\n"
    first_line = "- mod_one/util.py: " + "A" * 50
    budget = len("Context from direct imports:\n") + len(first_line) + 1
    result = resolve_import_context(item, content, repo, max_chars=budget)
    assert "mod_one/util.py" in result
    assert "mod_two/helper.py" not in result
    assert result == result.rstrip("\n") + result[len(result.rstrip("\n")) :]


def test_empty_file_returns_empty_string() -> None:
    repo = _make_repo()
    item = _make_item("src/app.py")
    result = resolve_import_context(item, "", repo, max_chars=5000)
    assert result == ""


def test_no_local_imports_returns_empty_string() -> None:
    repo = _make_repo()
    item = _make_item("src/app.py")
    content = "import os\nimport sys\nfrom . import sibling\n"
    result = resolve_import_context(item, content, repo, max_chars=5000)
    assert result == ""


def test_multiple_enriched_imports_all_appear() -> None:
    repo = _make_repo()
    repo.upsert(_make_enriched_item("mod_one/util.py", "Utility helpers"))
    repo.upsert(_make_enriched_item("mod_two/repo.py", "Data access layer"))
    item = _make_item("src/app.py")
    content = "from mod_one.util import foo\nfrom mod_two.repo import Repo\n"
    result = resolve_import_context(item, content, repo, max_chars=5000)
    assert "mod_one/util.py" in result
    assert "mod_two/repo.py" in result
    assert "Utility helpers" in result
    assert "Data access layer" in result
