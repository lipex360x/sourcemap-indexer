from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from sourcemap_indexer.application.sync import SyncReport, run_sync
from sourcemap_indexer.infra.db.migrator import init_db
from sourcemap_indexer.infra.db.sqlite_repo import SqliteItemRepository
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
        layer="application",
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
    assert found.value.layer == "application"


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


def test_sync_calls_on_progress(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    entries = [_file_entry(f"f{i}.py", content_hash=chr(ord("a") + i) * 64) for i in range(3)]
    _write_index(index, entries)
    calls: list[tuple[int, int]] = []
    run_sync(index, repo, on_progress=lambda cur, tot: calls.append((cur, tot)))
    assert len(calls) == 3
    assert calls[0] == (1, 3)
    assert calls[-1] == (3, 3)


def test_sync_on_progress_none_does_not_raise(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("f.py")])
    result = run_sync(index, repo, on_progress=None)
    assert isinstance(result, Right)


def test_sync_returns_left_when_insert_upsert_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    repo = _make_repo()
    monkeypatch.setattr(repo, "upsert", lambda _item: mk_left("upsert-failed"))
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py")])
    result = run_sync(index, repo)
    assert isinstance(result, Left)
    assert "upsert-failed" in result.error


def test_sync_returns_left_when_update_upsert_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py", content_hash="a" * 64)])
    run_sync(index, repo)
    monkeypatch.setattr(repo, "upsert", lambda _item: mk_left("upsert-failed"))
    _write_index(index, [_file_entry("app.py", content_hash="b" * 64)])
    result = run_sync(index, repo)
    assert isinstance(result, Left)


def test_sync_returns_left_when_find_by_path_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    repo = _make_repo()
    monkeypatch.setattr(repo, "find_by_path", lambda _p: mk_left("db-error"))
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py")])
    result = run_sync(index, repo)
    assert isinstance(result, Left)
    assert "db-error" in result.error


def test_sync_returns_left_when_find_all_paths_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("app.py")])
    run_sync(index, repo)
    monkeypatch.setattr(repo, "find_all_paths", lambda: mk_left("paths-error"))
    _write_index(index, [_file_entry("other.py")])
    result = run_sync(index, repo)
    assert isinstance(result, Left)
    assert "paths-error" in result.error


def test_sync_soft_delete_returns_zero_for_path_not_in_db(tmp_path: Path) -> None:
    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("a.py"), _file_entry("b.py")])
    run_sync(index, repo)
    repo._connection.execute("DELETE FROM items WHERE path = 'b.py'")  # noqa: SLF001
    repo._connection.commit()  # noqa: SLF001
    _write_index(index, [_file_entry("a.py")])
    result = run_sync(index, repo)
    assert isinstance(result, Right)


def test_sync_returns_left_when_soft_delete_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    repo = _make_repo()
    index = tmp_path / "index.yaml"
    _write_index(index, [_file_entry("a.py"), _file_entry("b.py")])
    run_sync(index, repo)
    monkeypatch.setattr(repo, "soft_delete", lambda _item_id, _now: mk_left("delete-error"))
    _write_index(index, [_file_entry("a.py")])
    result = run_sync(index, repo)
    assert isinstance(result, Left)
    assert "delete-error" in result.error


def test_soft_delete_gone_skips_when_path_not_in_db() -> None:
    from sourcemap_indexer.application.sync import _soft_delete_gone  # noqa: PLC0415

    class _MockRepo:
        def find_by_path(self, _path: str) -> Right:
            return Right(None)

    result = _soft_delete_gone("gone.py", _MockRepo(), int(time.time()))  # type: ignore
    assert isinstance(result, Right)
    assert result.value == 0


def test_soft_delete_gone_returns_left_when_find_by_path_fails() -> None:
    from sourcemap_indexer.application.sync import _soft_delete_gone  # noqa: PLC0415
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    class _MockRepo:
        def find_by_path(self, _path: str) -> Left:
            return mk_left("db-error")

    result = _soft_delete_gone("gone.py", _MockRepo(), int(time.time()))  # type: ignore
    assert isinstance(result, Left)
    assert result.error == "db-error"
