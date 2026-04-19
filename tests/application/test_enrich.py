from __future__ import annotations

import time
from pathlib import Path

from sourcemap_indexer.application.enrich import EnrichReport, run_enrich
from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import (
    ContentHash,
    ItemId,
    Language,
    Layer,
    Stability,
)
from sourcemap_indexer.infra.llama_client import EnrichmentResult
from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Either, Right, left, right


def _make_repo() -> SqliteItemRepository:
    result = init_db(Path(":memory:"))
    assert isinstance(result, Right)
    return SqliteItemRepository(result.value)


def _make_item(path: str, root: Path) -> Item:
    return Item(
        id=ItemId.generate(),
        path=path,
        name=path.split("/")[-1],
        language=Language.PY,
        lines=1,
        size_bytes=10,
        content_hash=ContentHash("a" * 64),
        last_modified=int(time.time()),
        needs_llm=True,
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )


_VALID_RESULT = EnrichmentResult(
    purpose="Ponto de entrada da aplicação",
    tags=frozenset({"cli", "entry-point"}),
    layer=Layer.APPLICATION,
    stability=Stability.STABLE,
    side_effects=frozenset(),
    invariants=(),
)


class _StubClient:
    def __init__(self, response: Either[str, EnrichmentResult]) -> None:
        self._response = response

    def enrich(self, path: str, language: Language, content: str) -> Either[str, EnrichmentResult]:
        return self._response


def _stub(response: Either[str, EnrichmentResult]) -> _StubClient:
    return _StubClient(response)


def test_enrich_happy_path(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    client = _stub(right(_VALID_RESULT))
    result = run_enrich(tmp_path, repo, client)  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.enriched == 1
    assert result.value.failed == 0


def test_enrich_sets_needs_llm_false(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    client = _stub(right(_VALID_RESULT))
    run_enrich(tmp_path, repo, client)  # type: ignore[arg-type]
    found = repo.find_by_path("app.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.needs_llm is False
    assert found.value.llm_hash is not None


def test_enrich_client_failure_marks_failed(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    client = _stub(left("llm-timeout"))
    result = run_enrich(tmp_path, repo, client)  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.failed == 1
    assert result.value.enriched == 0
    assert len(result.value.errors) == 1


def test_enrich_client_failure_preserves_needs_llm_true(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    client = _stub(left("llm-timeout"))
    run_enrich(tmp_path, repo, client)  # type: ignore[arg-type]
    found = repo.find_by_path("app.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.needs_llm is True


def test_enrich_missing_file_marks_failed(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("missing.py", tmp_path)
    repo.upsert(item)
    client = _stub(right(_VALID_RESULT))
    result = run_enrich(tmp_path, repo, client)  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.failed == 1
    assert result.value.enriched == 0


def test_enrich_respects_batch_limit(tmp_path: Path) -> None:
    repo = _make_repo()
    for i in range(5):
        item = _make_item(f"file{i}.py", tmp_path)
        (tmp_path / f"file{i}.py").write_text("x = 1\n")
        repo.upsert(item)
    client = _stub(right(_VALID_RESULT))
    result = run_enrich(tmp_path, repo, client, batch_limit=2)  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.enriched == 2


def test_enrich_partial_failure(tmp_path: Path) -> None:
    repo = _make_repo()
    for i in range(3):
        item = _make_item(f"file{i}.py", tmp_path)
        (tmp_path / f"file{i}.py").write_text("x = 1\n")
        repo.upsert(item)

    call_count = 0

    class _MixedClient:
        def enrich(
            self, path: str, language: Language, content: str
        ) -> Either[str, EnrichmentResult]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return left("llm-timeout")
            return right(_VALID_RESULT)

    result = run_enrich(tmp_path, repo, _MixedClient())  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.enriched == 2
    assert result.value.failed == 1


def test_enrich_report_fields() -> None:
    report = EnrichReport(enriched=1, failed=2, skipped=0, errors=("e1",))
    assert report.enriched == 1
    assert report.failed == 2
    assert report.skipped == 0
    assert report.errors == ("e1",)


def test_on_progress_callback_called_per_file(tmp_path: Path) -> None:
    repo = _make_repo()
    for i in range(3):
        item = _make_item(f"file{i}.py", tmp_path)
        (tmp_path / f"file{i}.py").write_text("x = 1\n")
        repo.upsert(item)
    calls: list[tuple[str, bool, int, int]] = []

    def _cb(path: str, success: bool, cur: int, tot: int) -> None:
        calls.append((path, success, cur, tot))

    client = _stub(right(_VALID_RESULT))
    run_enrich(tmp_path, repo, client, on_progress=_cb)  # type: ignore[arg-type]
    assert len(calls) == 3
    assert all(success for _, success, _, _ in calls)
    assert [cur for _, _, cur, _ in calls] == [1, 2, 3]
    assert all(tot == 3 for _, _, _, tot in calls)


def test_on_progress_callback_reports_failure(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    calls: list[tuple[str, bool, int, int]] = []

    def _cb(path: str, success: bool, cur: int, tot: int) -> None:
        calls.append((path, success, cur, tot))

    client = _stub(left("llm-timeout"))
    run_enrich(tmp_path, repo, client, on_progress=_cb)  # type: ignore[arg-type]
    assert calls == [("app.py", False, 1, 1)]
