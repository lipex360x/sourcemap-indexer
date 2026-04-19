from __future__ import annotations

import time
from pathlib import Path

import yaml

from sourcemap_indexer.application.sync import SyncReport, run_sync
from sourcemap_indexer.domain.value_objects import Layer
from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Left, Right


def _make_repo() -> SqliteItemRepository:
    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    return SqliteItemRepository(result.value)


def _write_index(path: Path, files: list[dict[str, object]]) -> None:
    index = {
        "version": 1,
        "generated_at": int(time.time()),
        "root": str(path.parent),
        "files": files,
    }
    path.write_text(yaml.dump(index, allow_unicode=True), encoding="utf-8")


def _file_entry(
    file_path: str = "src/app.py",
    language: str = "py",
    lines: int = 10,
    size_bytes: int = 200,
    content_hash: str = "a" * 64,
) -> dict[str, object]:
    return {
        "path": file_path,
        "language": language,
        "lines": lines,
        "size_bytes": size_bytes,
        "content_hash": content_hash,
        "last_modified": int(time.time()),
    }


def test_sync_inserts_new_item(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("src/app.py")])
    result = run_sync(index, repo)
    assert isinstance(result, Right)
    assert result.value.inserted == 1
    assert result.value.updated == 0
    assert result.value.unchanged == 0
    assert result.value.soft_deleted == 0


def test_sync_inserted_item_has_needs_llm_true(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py")])
    run_sync(index, repo)
    found = repo.find_by_path("app.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.needs_llm is True


def test_sync_unchanged_when_hash_identical(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    entry = _file_entry("app.py", content_hash="b" * 64)
    _write_index(index, [entry])
    run_sync(index, repo)
    result = run_sync(index, repo)
    assert isinstance(result, Right)
    assert result.value.unchanged == 1
    assert result.value.inserted == 0


def test_sync_updates_when_hash_differs(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py", content_hash="a" * 64)])
    run_sync(index, repo)
    _write_index(index, [_file_entry("app.py", content_hash="b" * 64)])
    result = run_sync(index, repo)
    assert isinstance(result, Right)
    assert result.value.updated == 1
    assert result.value.inserted == 0


def test_sync_update_sets_needs_llm_true(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py", content_hash="a" * 64)])
    run_sync(index, repo)
    _write_index(index, [_file_entry("app.py", content_hash="b" * 64)])
    run_sync(index, repo)
    found = repo.find_by_path("app.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.needs_llm is True


def test_sync_preserves_semantic_fields_on_update(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py", content_hash="a" * 64)])
    run_sync(index, repo)
    found_first = repo.find_by_path("app.py")
    assert isinstance(found_first, Right)
    assert found_first.value is not None
    enriched = found_first.value.with_llm_enrichment(
        purpose="entry point",
        layer=Layer.APPLICATION,
        stability=found_first.value.stability,
        tags=frozenset({"main", "cli"}),
        side_effects=frozenset(),
        invariants=(),
        llm_at=int(time.time()),
    )
    repo.upsert(enriched)
    _write_index(index, [_file_entry("app.py", content_hash="b" * 64)])
    run_sync(index, repo)
    found = repo.find_by_path("app.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.purpose == "entry point"
    assert found.value.tags == frozenset({"main", "cli"})
    assert found.value.layer == Layer.APPLICATION


def test_sync_soft_deletes_missing_paths(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("a.py"), _file_entry("b.py")])
    run_sync(index, repo)
    _write_index(index, [_file_entry("a.py")])
    result = run_sync(index, repo)
    assert isinstance(result, Right)
    assert result.value.soft_deleted == 1
    gone = repo.find_by_path("b.py")
    assert isinstance(gone, Right)
    assert gone.value is None


def test_sync_returns_left_for_missing_index(tmp_path: Path) -> None:
    repo = _make_repo()
    result = run_sync(tmp_path / "missing.yaml", repo)
    assert isinstance(result, Left)


def test_sync_returns_left_for_invalid_yaml(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    index.write_text("not: valid: yaml: [}", encoding="utf-8")
    result = run_sync(index, repo)
    assert isinstance(result, Left)


def test_sync_report_is_dataclass() -> None:
    report = SyncReport(inserted=1, updated=2, soft_deleted=3, unchanged=4)
    assert report.inserted == 1
    assert report.updated == 2
    assert report.soft_deleted == 3
    assert report.unchanged == 4


def test_sync_returns_left_for_non_dict_yaml(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    index.write_text("- item1\n- item2\n", encoding="utf-8")
    result = run_sync(index, repo)
    assert isinstance(result, Left)
    assert result.error == "index-invalid-format"


def test_sync_returns_left_on_index_read_error(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    index.write_bytes(b"data")
    index.chmod(0o000)
    result = run_sync(index, repo)
    assert isinstance(result, Left)
    index.chmod(0o644)


def test_sync_multiple_inserts(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    entries = [_file_entry(f"file{i}.py", content_hash=chr(ord("a") + i) * 64) for i in range(3)]
    _write_index(index, entries)
    result = run_sync(index, repo)
    assert isinstance(result, Right)
    assert result.value.inserted == 3
