from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from sourcemap_indexer.cli import _lang_color, _proportional_width, app
from sourcemap_indexer.lib.either import right

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


def test_walk_also_syncs_db(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["walk", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "inserted" in result.output


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


def test_lang_color_yellow_when_pending() -> None:
    assert _lang_color(1) == "yellow"
    assert _lang_color(5) == "yellow"


def test_lang_color_green_when_no_pending() -> None:
    assert _lang_color(0) == "green"


def test_proportional_width_max_count_gets_full_width() -> None:
    assert _proportional_width(100, 100, 20) == 20


def test_proportional_width_half_count_gets_half_width() -> None:
    assert _proportional_width(50, 100, 20) == 10


def test_proportional_width_small_count_minimum_one() -> None:
    assert _proportional_width(1, 100, 20) == 1
    assert _proportional_width(2, 114, 20) == 1


def test_proportional_width_zero_max_returns_zero() -> None:
    assert _proportional_width(0, 0, 20) == 0


def test_stats_shows_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "LLM: not configured" in result.output


def test_stats_auto_walks_new_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    (tmp_path / "app.py").write_text("x = 1\n")
    result = runner.invoke(app, ["stats", "--root", str(tmp_path), "--files"])
    assert result.exit_code == 0
    assert "app.py" in result.output


def test_stats_show_flag_rejected(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path), "--show"])
    assert result.exit_code != 0


def test_stats_auto_walk_shows_sync_summary_when_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    (tmp_path / "new.py").write_text("y = 2\n")
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "inserted=1" in result.output


def test_stats_shows_model_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://myhost/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-model")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "my-model" in result.output
    assert "myhost" in result.output


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


def test_stats_succeeds_on_empty_uninitialised_dir(tmp_path: Path) -> None:
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Total: 0" in result.output


def test_enrich_fails_when_llm_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    monkeypatch.delenv("SOURCEMAP_LLM_MODEL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0
    assert "not configured" in result.output


def test_enrich_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport
    from sourcemap_indexer.lib.either import right

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(
        cli_module,
        "run_enrich",
        lambda *_args, **_kwargs: right(
            EnrichReport(enriched=2, failed=0, skipped=1, errors=("warn",))
        ),
    )
    monkeypatch.setattr(cli_module.LlamaClient, "ping", lambda _self: right(None))
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

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlamaClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(cli_module, "run_enrich", lambda *_args, **_kwargs: left("llm-error"))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0


def _init_sync(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])


def test_query_returns_results(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(
        app, ["query", "SELECT path, language FROM items", "--root", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "path" in result.output
    assert "language" in result.output
    assert "app.py" in result.output


def test_query_no_results(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(
        app, ["query", "SELECT path FROM items WHERE 1=0", "--root", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "no results" in result.output


def test_query_sql_error(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(
        app, ["query", "SELECT * FROM nonexistent_table", "--root", str(tmp_path)]
    )
    assert result.exit_code != 0


def test_query_no_index(tmp_path: Path) -> None:
    result = runner.invoke(app, ["query", "SELECT 1", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_overview_runs(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["overview", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "layer" in result.output


def test_domain_no_results_before_enrich(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["domain", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no results" in result.output


def test_effects_no_results_before_enrich(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["effects", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no results" in result.output


def test_tags_no_results_before_enrich(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["tags", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no results" in result.output


def test_unstable_no_results_before_enrich(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["unstable", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no results" in result.output


def test_profile_runs_after_walk(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["profile", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Stack" in result.output
    assert "py" in result.output
    assert "Top files" in result.output


def test_profile_shows_test_ratio(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_x(): pass\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def run(): pass\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    result = runner.invoke(app, ["profile", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Test ratio" in result.output


def test_profile_fails_without_index(tmp_path: Path) -> None:
    result = runner.invoke(app, ["profile", "--root", str(tmp_path / "missing")])
    assert result.exit_code != 0


def test_reset_confirmed_deletes_db(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    db_file = tmp_path / ".docs" / "maps" / "index.db"
    assert db_file.exists()
    result = runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\nn\n")
    assert result.exit_code == 0
    assert not db_file.exists()
    assert "irreversible" in result.output


def test_reset_with_backup_creates_bak_file(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    maps_dir = tmp_path / ".docs" / "maps"
    result = runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\ny\n")
    assert result.exit_code == 0
    bak_files = list(maps_dir.glob("index.*.bak"))
    assert len(bak_files) == 1
    assert "Backup saved" in result.output


def test_reset_without_backup_no_bak_file(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    maps_dir = tmp_path / ".docs" / "maps"
    runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\nn\n")
    assert not list(maps_dir.glob("index.*.bak"))


def test_reset_aborted_keeps_maps(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["reset", "--root", str(tmp_path)], input="n\n")
    assert result.exit_code == 0
    assert (tmp_path / ".docs" / "maps").exists()
    assert "Cancelled" in result.output


def test_reset_no_index_exits(tmp_path: Path) -> None:
    result = runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\n")
    assert result.exit_code != 0


def test_restore_no_maps_dir_exits(tmp_path: Path) -> None:
    result = runner.invoke(app, ["restore", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_restore_no_backups_found(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["restore", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No backups found" in result.output


def test_restore_lists_and_restores_backup(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    maps_dir = tmp_path / ".docs" / "maps"
    runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\ny\n")
    bak_files = list(maps_dir.glob("index.*.bak"))
    assert len(bak_files) == 1
    result = runner.invoke(app, ["restore", "--root", str(tmp_path)], input="1\n")
    assert result.exit_code == 0
    assert "Restored from" in result.output
    assert (maps_dir / "index.db").exists()


def test_restore_invalid_selection_exits(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    maps_dir = tmp_path / ".docs" / "maps"
    bak = maps_dir / "index.20240101_000000.bak"
    bak.write_bytes(b"fake")
    result = runner.invoke(app, ["restore", "--root", str(tmp_path)], input="99\n")
    assert result.exit_code != 0


def test_install_skill_creates_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["install-skill", "--target", str(tmp_path)])
    assert result.exit_code == 0
    skill = tmp_path / "sourcemap" / "SKILL.md"
    assert skill.exists()
    assert "sourcemap" in skill.read_text()
    assert "Skill installed" in result.output


def test_enrich_exports_default_prompt_to_md_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    export_file = tmp_path / "exported.md"
    monkeypatch.setenv("SOURCEMAP_EXPORT_LLM_PROMPT", str(export_file))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert export_file.exists()
    assert len(export_file.read_text()) > 0


def test_enrich_export_prompt_content_matches_system_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.infra.llama_client import SYSTEM_PROMPT

    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    export_file = tmp_path / "exported.md"
    monkeypatch.setenv("SOURCEMAP_EXPORT_LLM_PROMPT", str(export_file))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert export_file.read_text(encoding="utf-8") == SYSTEM_PROMPT


def test_enrich_uses_custom_prompt_from_import_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlamaClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(
        cli_module,
        "run_enrich",
        lambda *_args, **_kwargs: right(EnrichReport(enriched=1, failed=0, skipped=0, errors=())),
    )
    import_file = tmp_path / "custom-prompt.md"
    import_file.write_text("custom instructions here", encoding="utf-8")
    monkeypatch.setenv("SOURCEMAP_IMPORT_LLM_PROMPT", str(import_file))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "custom-prompt.md" in result.output


def test_enrich_fails_on_non_md_export_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCEMAP_EXPORT_LLM_PROMPT", str(tmp_path / "out.txt"))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_enrich_fails_on_non_md_import_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setenv("SOURCEMAP_IMPORT_LLM_PROMPT", str(tmp_path / "prompt.txt"))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0
