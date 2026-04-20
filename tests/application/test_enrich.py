from __future__ import annotations

import time
from pathlib import Path

from sourcemap_indexer.application.enrich import EnrichReport, run_enrich
from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.value_objects import (
    ContentHash,
    ItemId,
    Language,
    Stability,
)
from sourcemap_indexer.infra.llm_client import EnrichmentResult
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
    purpose="Application entry point",
    tags=frozenset({"cli", "entry-point"}),
    layer="application",
    stability=Stability.STABLE,
    side_effects=frozenset(),
    invariants=(),
)


class _StubClient:
    def __init__(self, response: Either[str, EnrichmentResult]) -> None:
        self._response = response

    def enrich(
        self,
        path: str,
        language: Language,
        content: str,
        extra_instruction: str | None = None,
    ) -> Either[str, EnrichmentResult]:
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


def test_on_progress_total_reflects_actual_count_not_limit(tmp_path: Path) -> None:
    repo = _make_repo()
    for i in range(8):
        item = _make_item(f"file{i}.py", tmp_path)
        (tmp_path / f"file{i}.py").write_text("x = 1\n")
        repo.upsert(item)
    totals: list[int] = []

    def _cb(path: str, success: bool, cur: int, tot: int) -> None:
        totals.append(tot)

    client = _stub(right(_VALID_RESULT))
    run_enrich(tmp_path, repo, client, on_progress=_cb, batch_limit=10)  # type: ignore[arg-type]
    assert all(tot == 8 for tot in totals)


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
            self,
            path: str,
            language: Language,
            content: str,
            extra_instruction: str | None = None,
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


def _make_empty_item(path: str, root: Path) -> Item:
    return Item(
        id=ItemId.generate(),
        path=path,
        name=path.split("/")[-1],
        language=Language.PY,
        lines=0,
        size_bytes=0,
        content_hash=ContentHash("a" * 64),
        last_modified=int(time.time()),
        needs_llm=True,
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )


def test_empty_file_skips_llm_call(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_empty_item("empty.py", tmp_path)
    (tmp_path / "empty.py").write_bytes(b"")
    repo.upsert(item)
    called = []

    class _TrackingClient:
        def enrich(
            self,
            path: str,
            language: Language,
            content: str,
            extra_instruction: str | None = None,
        ) -> Either[str, EnrichmentResult]:
            called.append(path)
            return right(_VALID_RESULT)

    run_enrich(tmp_path, repo, _TrackingClient())  # type: ignore[arg-type]
    assert called == []


def test_empty_file_counted_as_enriched(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_empty_item("empty.py", tmp_path)
    (tmp_path / "empty.py").write_bytes(b"")
    repo.upsert(item)
    result = run_enrich(tmp_path, repo, _stub(right(_VALID_RESULT)))  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.enriched == 1
    assert result.value.failed == 0


def test_empty_file_sets_needs_llm_false(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_empty_item("empty.py", tmp_path)
    (tmp_path / "empty.py").write_bytes(b"")
    repo.upsert(item)
    run_enrich(tmp_path, repo, _stub(right(_VALID_RESULT)))  # type: ignore[arg-type]
    found = repo.find_by_path("empty.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.needs_llm is False


def test_empty_file_saved_with_stub_purpose(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_empty_item("empty.py", tmp_path)
    (tmp_path / "empty.py").write_bytes(b"")
    repo.upsert(item)
    run_enrich(tmp_path, repo, _stub(right(_VALID_RESULT)))  # type: ignore[arg-type]
    found = repo.find_by_path("empty.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.purpose == "Empty file"
    assert "empty-file" in found.value.tags


def test_invalid_layer_marks_failed_and_preserves_needs_llm(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    invalid_result = EnrichmentResult(
        purpose="p",
        tags=frozenset({"t"}),
        layer="nonexistent_layer",
        stability=Stability.STABLE,
        side_effects=frozenset(),
        invariants=(),
    )
    client = _stub(right(invalid_result))
    valid_layers = frozenset({"domain", "infra", "unknown"})
    result = run_enrich(tmp_path, repo, client, valid_layers=valid_layers)  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.failed == 1
    assert result.value.enriched == 0
    found = repo.find_by_path("app.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.needs_llm is True


def test_valid_user_layer_is_accepted(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    custom_result = EnrichmentResult(
        purpose="p",
        tags=frozenset({"t"}),
        layer="controller",
        stability=Stability.STABLE,
        side_effects=frozenset(),
        invariants=(),
    )
    client = _stub(right(custom_result))
    valid_layers = frozenset({"domain", "controller", "unknown"})
    result = run_enrich(tmp_path, repo, client, valid_layers=valid_layers)  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.enriched == 1
    found = repo.find_by_path("app.py")
    assert isinstance(found, Right)
    assert found.value is not None
    assert found.value.layer == "controller"


def test_no_valid_layers_accepts_any_layer(tmp_path: Path) -> None:
    repo = _make_repo()
    item = _make_item("app.py", tmp_path)
    (tmp_path / "app.py").write_text("x = 1\n")
    repo.upsert(item)
    custom_result = EnrichmentResult(
        purpose="p",
        tags=frozenset({"t"}),
        layer="anything",
        stability=Stability.STABLE,
        side_effects=frozenset(),
        invariants=(),
    )
    client = _stub(right(custom_result))
    result = run_enrich(tmp_path, repo, client)  # type: ignore[arg-type]
    assert isinstance(result, Right)
    assert result.value.enriched == 1
