from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sourcemap_indexer.cli import app

runner = CliRunner()


def _db(root: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(root / ".sourcemap" / "index.db"))


def _count(conn: sqlite3.Connection, where: str = "1=1") -> int:
    return conn.execute(f"SELECT COUNT(*) FROM items WHERE {where}").fetchone()[0]  # noqa: S608


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "main.py").write_text("def main(): pass\n")
    (tmp_path / "utils.py").write_text("def helper(): return 1\n")
    (tmp_path / "README.md").write_text("# Project\n")
    (tmp_path / "run.sh").write_text("#!/usr/bin/env bash\necho hi\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    return tmp_path


def test_init_walk_full_cycle(project: Path) -> None:
    result = runner.invoke(app, ["walk", "--root", str(project)])
    assert result.exit_code == 0
    assert "inserted" in result.output.lower()

    conn = _db(project)
    assert _count(conn) == 5
    assert _count(conn, "needs_llm=1") == 5
    conn.close()


def test_incremental_sync_after_changes(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])

    (project / "utils.py").write_text("def helper(): return 99\n")
    (project / "new_module.py").write_text("x = 42\n")
    (project / "run.sh").unlink()

    result = runner.invoke(app, ["walk", "--root", str(project)])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()
    assert "inserted" in result.output.lower()
    assert "soft-deleted" in result.output.lower()

    conn = _db(project)
    assert _count(conn, "deleted_at IS NULL") == 5
    assert _count(conn, "deleted_at IS NOT NULL") == 1
    conn.close()


def test_enrich_with_fake_client(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport
    from sourcemap_indexer.lib.either import right

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_args, **_kwargs: right(EnrichReport(enriched=5, failed=0, skipped=0, errors=())),
    )

    runner.invoke(app, ["walk", "--root", str(project)])

    result = runner.invoke(app, ["enrich", "--root", str(project)])
    assert result.exit_code == 0
    assert "Enriched" in result.output


def test_find_after_walk(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])

    result = runner.invoke(app, ["find", "--root", str(project)])
    assert result.exit_code == 0
    assert "main.py" in result.output
    assert "utils.py" in result.output


def test_stats_after_walk(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])

    result = runner.invoke(app, ["stats", "--root", str(project)])
    assert result.exit_code == 0
    assert "Total: 5" in result.output
    assert "Pending: 5" in result.output


def test_stale_after_content_change(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])

    conn = _db(project)
    fake_hash = "b" * 64
    conn.execute("UPDATE items SET llm_hash = ? WHERE path = 'main.py'", (fake_hash,))
    conn.commit()
    conn.close()

    (project / "main.py").write_text("def main(): return 42\n")
    runner.invoke(app, ["walk", "--root", str(project)])

    result = runner.invoke(app, ["stale", "--root", str(project)])
    assert result.exit_code == 0
    assert "main.py" in result.output


def test_show_item_details(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])

    result = runner.invoke(app, ["show", "main.py", "--root", str(project)])
    assert result.exit_code == 0
    assert "main.py" in result.output
    assert "language:  py" in result.output


def test_with_context_enriched_import_appears_in_prompt(tmp_path: Path) -> None:
    import time  # noqa: PLC0415

    from sourcemap_indexer.application.enrich import run_enrich  # noqa: PLC0415
    from sourcemap_indexer.domain.entities import Item  # noqa: PLC0415
    from sourcemap_indexer.domain.value_objects import (  # noqa: PLC0415
        ContentHash,
        ItemId,
        Language,
        Stability,
    )
    from sourcemap_indexer.infra.llm_client import EnrichmentResult  # noqa: PLC0415
    from sourcemap_indexer.infra.migrator import init_db  # noqa: PLC0415
    from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository  # noqa: PLC0415
    from sourcemap_indexer.lib.either import Either, Right  # noqa: PLC0415

    db_result = init_db(Path(":memory:"))
    assert isinstance(db_result, Right)
    repo = SqliteItemRepository(db_result.value)

    dep_path = "my_lib/helper.py"
    app_path = "app.py"

    (tmp_path / "my_lib").mkdir()
    (tmp_path / dep_path).write_text("def helper(): pass\n")
    (tmp_path / app_path).write_text("from my_lib.helper import helper\n")

    now = int(time.time())
    dep_item = Item(
        id=ItemId.generate(),
        path=dep_path,
        name="helper.py",
        language=Language.PY,
        lines=1,
        size_bytes=20,
        content_hash=ContentHash("b" * 64),
        last_modified=now,
        needs_llm=False,
        created_at=now,
        updated_at=now,
    ).with_llm_enrichment(
        purpose="Provides reusable helper utilities",
        layer="lib",
        stability=Stability.STABLE,
        tags=frozenset(),
        side_effects=frozenset(),
        invariants=(),
        llm_at=now,
    )
    repo.upsert(dep_item)

    app_item = Item(
        id=ItemId.generate(),
        path=app_path,
        name="app.py",
        language=Language.PY,
        lines=1,
        size_bytes=38,
        content_hash=ContentHash("c" * 64),
        last_modified=now,
        needs_llm=True,
        created_at=now,
        updated_at=now,
    )
    repo.upsert(app_item)

    captured_contexts: list[str | None] = []

    class _SpyClient:
        def enrich(
            self,
            path: str,
            language: Language,
            content: str,
            extra_instruction: str | None = None,
            import_context: str | None = None,
        ) -> Either[str, EnrichmentResult]:
            captured_contexts.append(import_context)
            return Right(
                EnrichmentResult(
                    purpose="Application entry",
                    tags=frozenset({"cli"}),
                    layer="application",
                    stability=Stability.STABLE,
                    side_effects=frozenset(),
                    invariants=(),
                )
            )

    run_enrich(tmp_path, repo, _SpyClient(), with_context=True)  # type: ignore[arg-type]
    assert len(captured_contexts) == 1
    assert captured_contexts[0] is not None
    assert "my_lib/helper.py" in captured_contexts[0]
    assert "Provides reusable helper utilities" in captured_contexts[0]


def test_with_context_false_no_context_in_prompt(tmp_path: Path) -> None:
    import time  # noqa: PLC0415

    from sourcemap_indexer.application.enrich import run_enrich  # noqa: PLC0415
    from sourcemap_indexer.domain.entities import Item  # noqa: PLC0415
    from sourcemap_indexer.domain.value_objects import (  # noqa: PLC0415
        ContentHash,
        ItemId,
        Language,
        Stability,
    )
    from sourcemap_indexer.infra.llm_client import EnrichmentResult  # noqa: PLC0415
    from sourcemap_indexer.infra.migrator import init_db  # noqa: PLC0415
    from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository  # noqa: PLC0415
    from sourcemap_indexer.lib.either import Either, Right  # noqa: PLC0415

    db_result = init_db(Path(":memory:"))
    assert isinstance(db_result, Right)
    repo = SqliteItemRepository(db_result.value)

    now = int(time.time())
    app_item = Item(
        id=ItemId.generate(),
        path="app.py",
        name="app.py",
        language=Language.PY,
        lines=1,
        size_bytes=38,
        content_hash=ContentHash("d" * 64),
        last_modified=now,
        needs_llm=True,
        created_at=now,
        updated_at=now,
    )
    repo.upsert(app_item)
    (tmp_path / "app.py").write_text("from my_lib.helper import helper\n")

    captured_contexts: list[str | None] = []

    class _SpyClient:
        def enrich(
            self,
            path: str,
            language: Language,
            content: str,
            extra_instruction: str | None = None,
            import_context: str | None = None,
        ) -> Either[str, EnrichmentResult]:
            captured_contexts.append(import_context)
            return Right(
                EnrichmentResult(
                    purpose="p",
                    tags=frozenset(),
                    layer="application",
                    stability=Stability.STABLE,
                    side_effects=frozenset(),
                    invariants=(),
                )
            )

    run_enrich(tmp_path, repo, _SpyClient(), with_context=False)  # type: ignore[arg-type]
    assert captured_contexts[0] is None


def test_topo_order_single_pass_context(tmp_path: Path) -> None:
    import time  # noqa: PLC0415

    from sourcemap_indexer.application.enrich import run_enrich  # noqa: PLC0415
    from sourcemap_indexer.domain.entities import Item  # noqa: PLC0415
    from sourcemap_indexer.domain.value_objects import (  # noqa: PLC0415
        ContentHash,
        ItemId,
        Language,
        Stability,
    )
    from sourcemap_indexer.infra.llm_client import EnrichmentResult  # noqa: PLC0415
    from sourcemap_indexer.infra.migrator import init_db  # noqa: PLC0415
    from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository  # noqa: PLC0415
    from sourcemap_indexer.lib.either import Either, Right  # noqa: PLC0415

    db_result = init_db(Path(":memory:"))
    assert isinstance(db_result, Right)
    repo = SqliteItemRepository(db_result.value)

    now = int(time.time())

    leaf_path = "utils/helper.py"
    dependent_path = "app.py"

    (tmp_path / "utils").mkdir()
    (tmp_path / leaf_path).write_text("def helper(): pass\n")
    (tmp_path / dependent_path).write_text("from utils.helper import helper\n")

    def _make_pending(path: str, size: int) -> Item:
        return Item(
            id=ItemId.generate(),
            path=path,
            name=path.split("/")[-1],
            language=Language.PY,
            lines=1,
            size_bytes=size,
            content_hash=ContentHash("f" * 64),
            last_modified=now,
            needs_llm=True,
            created_at=now,
            updated_at=now,
        )

    dependent_item = _make_pending(dependent_path, 38)
    leaf_item = _make_pending(leaf_path, 25)
    repo.upsert(dependent_item)
    repo.upsert(leaf_item)

    call_order: list[str] = []
    captured_for_dependent: list[str | None] = []

    class _SpyClient:
        def enrich(
            self,
            path: str,
            language: Language,
            content: str,
            extra_instruction: str | None = None,
            import_context: str | None = None,
        ) -> Either[str, EnrichmentResult]:
            call_order.append(path)
            if path == dependent_path:
                captured_for_dependent.append(import_context)
            return Right(
                EnrichmentResult(
                    purpose="Leaf utility" if path == leaf_path else "Application entry",
                    tags=frozenset(),
                    layer="lib" if path == leaf_path else "application",
                    stability=Stability.STABLE,
                    side_effects=frozenset(),
                    invariants=(),
                )
            )

    run_enrich(tmp_path, repo, _SpyClient(), with_context=True)  # type: ignore[arg-type]

    assert call_order.index(leaf_path) < call_order.index(dependent_path)
    assert len(captured_for_dependent) == 1
    assert captured_for_dependent[0] is not None
    assert "utils/helper.py" in captured_for_dependent[0]
    assert "Leaf utility" in captured_for_dependent[0]
