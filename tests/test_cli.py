from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from sourcemap_indexer.cli import app

runner = CliRunner()


def test_init_creates_maps_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".docs" / "maps").is_dir()


def test_init_creates_db_file(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    assert (tmp_path / ".docs" / "maps" / "index.db").exists()


def test_init_creates_sourcemapignore(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    assert (tmp_path / ".sourcemapignore").exists()


def test_init_db_error_exits(tmp_path: Path) -> None:
    maps_dir = tmp_path / ".docs" / "maps"
    maps_dir.mkdir(parents=True)
    maps_dir.chmod(0o000)
    result = runner.invoke(app, ["init", "--root", str(tmp_path)])
    maps_dir.chmod(0o755)
    assert result.exit_code != 0


def test_walk_generates_yaml(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["walk", "--root", str(tmp_path)])
    assert result.exit_code == 0
    index = tmp_path / ".docs" / "maps" / "index.yaml"
    assert index.exists()
    data = yaml.safe_load(index.read_text())
    assert len(data["files"]) >= 1


def test_walk_error_exits(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    ignore = tmp_path / ".sourcemapignore"
    ignore.chmod(0o000)
    result = runner.invoke(app, ["walk", "--root", str(tmp_path)])
    ignore.chmod(0o644)
    assert result.exit_code != 0


def test_sync_after_walk_populates_db(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "inserted" in result.output.lower() or "1" in result.output


def test_sync_error_without_index(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["sync", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_find_returns_items(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["find", "--root", str(tmp_path)])
    assert result.exit_code == 0


def test_find_no_items(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["find", "--root", str(tmp_path), "--tag", "no-such-tag-xyz"])
    assert result.exit_code == 0
    assert "No items found" in result.output


def test_show_existing_path(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["show", "app.py", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "app.py" in result.output


def test_show_missing_path_exits_nonzero(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["show", "nonexistent.py", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_stats_shows_counts(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0


def test_stale_lists_items(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stale", "--root", str(tmp_path)])
    assert result.exit_code == 0


def test_stale_with_modified_items(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    db_path = tmp_path / ".docs" / "maps" / "index.db"
    conn = sqlite3.connect(str(db_path))
    fake_hash = "a" * 64
    conn.execute("UPDATE items SET llm_hash = ? WHERE path = 'app.py'", (fake_hash,))
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["stale", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "app.py" in result.output


def test_resolve_root_error_without_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolated = tmp_path / "no_git"
    isolated.mkdir()
    monkeypatch.chdir(isolated)
    result = runner.invoke(app, ["walk"])
    assert result.exit_code != 0


def test_open_repo_db_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["stats", "--root", str(tmp_path / "missing")])
    assert result.exit_code != 0


def test_enrich_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport
    from sourcemap_indexer.lib.either import right

    monkeypatch.setattr(
        cli_module,
        "run_enrich",
        lambda *_args, **_kwargs: right(
            EnrichReport(enriched=2, failed=0, skipped=1, errors=("warn",))
        ),
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "enriched=2" in result.output


def test_enrich_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.lib.either import left

    monkeypatch.setattr(cli_module, "run_enrich", lambda *_args, **_kwargs: left("llm-error"))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0
