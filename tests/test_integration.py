from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sourcemap_indexer.cli import app

runner = CliRunner()


def _db(root: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(root / ".docs" / "maps" / "index.db"))


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


def test_init_walk_sync_full_cycle(project: Path) -> None:
    result = runner.invoke(app, ["walk", "--root", str(project)])
    assert result.exit_code == 0

    result = runner.invoke(app, ["sync", "--root", str(project)])
    assert result.exit_code == 0
    assert "inserted=5" in result.output

    conn = _db(project)
    assert _count(conn) == 5
    assert _count(conn, "needs_llm=1") == 5
    conn.close()


def test_incremental_sync_after_changes(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])
    runner.invoke(app, ["sync", "--root", str(project)])

    (project / "utils.py").write_text("def helper(): return 99\n")
    (project / "new_module.py").write_text("x = 42\n")
    (project / "run.sh").unlink()

    result = runner.invoke(app, ["walk", "--root", str(project)])
    assert result.exit_code == 0

    result = runner.invoke(app, ["sync", "--root", str(project)])
    assert result.exit_code == 0
    assert "updated=1" in result.output
    assert "inserted=1" in result.output
    assert "soft_deleted=1" in result.output

    conn = _db(project)
    assert _count(conn, "deleted_at IS NULL") == 5
    assert _count(conn, "deleted_at IS NOT NULL") == 1
    conn.close()


def test_enrich_with_fake_client(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport
    from sourcemap_indexer.lib.either import right

    monkeypatch.setattr(
        cli_module,
        "run_enrich",
        lambda *_args, **_kwargs: right(EnrichReport(enriched=5, failed=0, skipped=0, errors=())),
    )

    runner.invoke(app, ["walk", "--root", str(project)])
    runner.invoke(app, ["sync", "--root", str(project)])

    result = runner.invoke(app, ["enrich", "--root", str(project)])
    assert result.exit_code == 0
    assert "enriched=5" in result.output


def test_find_after_sync(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])
    runner.invoke(app, ["sync", "--root", str(project)])

    result = runner.invoke(app, ["find", "--root", str(project)])
    assert result.exit_code == 0
    assert "main.py" in result.output
    assert "utils.py" in result.output


def test_stats_after_sync(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])
    runner.invoke(app, ["sync", "--root", str(project)])

    result = runner.invoke(app, ["stats", "--root", str(project)])
    assert result.exit_code == 0
    assert "Total: 5" in result.output
    assert "Pending: 5" in result.output


def test_stale_after_content_change(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])
    runner.invoke(app, ["sync", "--root", str(project)])

    conn = _db(project)
    fake_hash = "b" * 64
    conn.execute("UPDATE items SET llm_hash = ? WHERE path = 'main.py'", (fake_hash,))
    conn.commit()
    conn.close()

    (project / "main.py").write_text("def main(): return 42\n")
    runner.invoke(app, ["walk", "--root", str(project)])
    runner.invoke(app, ["sync", "--root", str(project)])

    result = runner.invoke(app, ["stale", "--root", str(project)])
    assert result.exit_code == 0
    assert "main.py" in result.output


def test_show_item_details(project: Path) -> None:
    runner.invoke(app, ["walk", "--root", str(project)])
    runner.invoke(app, ["sync", "--root", str(project)])

    result = runner.invoke(app, ["show", "main.py", "--root", str(project)])
    assert result.exit_code == 0
    assert "main.py" in result.output
    assert "language:  py" in result.output
    assert "needs_llm: True" in result.output
