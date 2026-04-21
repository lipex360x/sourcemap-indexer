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
    assert (tmp_path / ".sourcemap").is_dir()


def test_init_creates_db_file(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    assert (tmp_path / ".sourcemap" / "index.db").exists()


def test_init_creates_sourcemapignore(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    assert (tmp_path / ".sourcemapignore").exists()


def test_init_db_error_exits(tmp_path: Path) -> None:
    maps_dir = tmp_path / ".sourcemap"
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
    index = tmp_path / ".sourcemap" / "index.yaml"
    assert index.exists()
    data = yaml.safe_load(index.read_text())
    assert len(data["files"]) >= 1


def test_walk_also_syncs_db(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["walk", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "inserted" in result.output.lower()


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
    assert "Inserted" in result.output


def test_stats_shows_model_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://myhost/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-model")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "my-model" in result.output
    assert "myhost" in result.output
    assert "LLM" in result.output


def test_stats_header_label_is_llm_not_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "LLM" in result.output
    assert "Model" not in result.output


def test_stats_shows_project_root_in_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Root" in result.output


class _MockTask:
    def __init__(self, completed: float, total: float | None) -> None:
        self.completed = completed
        self.total = total


def test_panel_default_style_is_info() -> None:
    from rich.panel import Panel

    from sourcemap_indexer.cli._rendering import _panel

    result = _panel("content", "Title")
    assert isinstance(result, Panel)
    assert result.border_style == "bright_blue"


def test_panel_warn_style() -> None:
    from sourcemap_indexer.cli._rendering import _panel

    result = _panel("content", "Title", style="warn")
    assert result.border_style == "yellow"


def test_panel_error_style() -> None:
    from sourcemap_indexer.cli._rendering import _panel

    result = _panel("content", "Title", style="error")
    assert result.border_style == "red"


def test_enriched_bar_full_when_all_enriched() -> None:
    from sourcemap_indexer.cli._rendering import _enriched_bar

    assert _enriched_bar(3, 3, 3) == "●●●"


def test_enriched_bar_empty_when_none_enriched() -> None:
    from sourcemap_indexer.cli._rendering import _enriched_bar

    assert _enriched_bar(0, 3, 3) == "○○○"


def test_enriched_bar_partial_fill() -> None:
    from sourcemap_indexer.cli._rendering import _enriched_bar

    assert _enriched_bar(1, 2, 4) == "●●○○"


def test_enriched_bar_single_enriched_shows_filled_dot() -> None:
    from sourcemap_indexer.cli._rendering import _enriched_bar

    assert _enriched_bar(1, 1, 1) == "●"


def test_enriched_bar_zero_total_returns_empty_width() -> None:
    from sourcemap_indexer.cli._rendering import _enriched_bar

    assert _enriched_bar(0, 0, 3) == "○○○"


def test_color_legend_is_right_aligned() -> None:
    from rich.align import Align

    from sourcemap_indexer.cli._rendering import _color_legend

    assert isinstance(_color_legend(), Align)


def test_color_legend_contains_symbols_separated_by_pipe() -> None:
    from rich.console import Console
    from rich.text import Text

    from sourcemap_indexer.cli._rendering import _color_legend

    console = Console(highlight=False)
    with console.capture() as cap:
        console.print(_color_legend())
    plain = Text.from_ansi(cap.get()).plain
    assert plain.count("●") >= 2
    assert "○" in plain
    assert "|" in plain
    assert "=" not in plain


def test_stats_by_language_shows_filled_bar_for_enriched_small_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    for idx in range(10):
        (tmp_path / f"app{idx}.py").write_text(f"x = {idx}\n")
    (tmp_path / "README.md").write_text("# readme\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    db_file = tmp_path / ".sourcemap" / "index.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("UPDATE items SET needs_llm = 0, llm_hash = content_hash WHERE language = 'md'")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    output_lines = result.output.splitlines()
    md_line = next((line for line in output_lines if "md" in line and "●" in line), None)
    assert md_line is not None, "expected filled bar for enriched md file"


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
    db_path = tmp_path / ".sourcemap" / "index.db"
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


def test_stats_shows_legend_below_by_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "●" in result.output
    assert "|" in result.output


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
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_args, **_kwargs: right(
            EnrichReport(enriched=2, failed=0, skipped=1, errors=("warn",))
        ),
    )
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["walk", "--root", str(tmp_path)])
    runner.invoke(app, ["sync", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Enriched" in result.output


def test_enrich_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.lib.either import left

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_args, **_kwargs: left("llm-error"),
    )
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


def test_brief_runs_after_walk(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Structure" in result.output
    assert "Vocabulary" not in result.output


def test_brief_contains_all_sections(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Structure" in result.output
    assert "Domain" in result.output
    assert "I/O Boundaries" in result.output
    assert "System Contracts" in result.output
    assert "Vocabulary" not in result.output


def test_brief_fails_without_index(tmp_path: Path) -> None:
    result = runner.invoke(app, ["brief", "--root", str(tmp_path / "missing")])
    assert result.exit_code != 0


def test_brief_shows_no_data_when_not_enriched(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no enriched data" in result.output


def test_brief_contains_workflows_section(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Workflows" in result.output


def test_brief_contains_system_contracts_section(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "System Contracts" in result.output
    assert "Invariants" not in result.output


def test_brief_stability_not_in_header(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Stability" not in result.output


def test_brief_contracts_grouped_by_file(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'domain/entities.py', 'entities.py', 'py', 'domain', 'stable', "
        "'entity', 50, 500, 'abc', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) "
        "VALUES (1, 0, 'frozen after creation')"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "domain/entities.py" in result.output
    assert "frozen after creation" in result.output


def test_brief_contracts_capped_at_three(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'domain/repo.py', 'repo.py', 'py', 'domain', 'stable', "
        "'repo', 50, 500, 'abc', 0, 0, 0)"
    )
    for pos, inv in enumerate(["inv_a", "inv_b", "inv_c", "inv_d"]):
        conn.execute(
            f"INSERT INTO invariants (item_id, position, invariant) VALUES (1, {pos}, '{inv}')"
        )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "inv_a" in result.output
    assert "inv_b" in result.output
    assert "inv_c" in result.output
    assert "inv_d" not in result.output


def test_brief_contracts_filters_cli_layer(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'domain/e.py', 'e.py', 'py', 'domain', 'stable', "
        "'entity', 50, 500, 'abc', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (2, 'cli/cmd.py', 'cmd.py', 'py', 'cli', 'stable', "
        "'cmd', 50, 500, 'def', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) VALUES (1, 0, 'domain contract')"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) VALUES (2, 0, 'cli contract')"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "domain contract" in result.output
    assert "cli contract" not in result.output


def test_brief_risk_shows_purpose(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'src/exp.py', 'exp.py', 'py', 'infra', 'experimental', "
        "'experimental feature purpose', 50, 500, 'abc', 0, 0, 0)"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "src/exp.py" in result.output
    assert "experimental feature purpose" in result.output


def test_brief_risk_shows_enrichment_gap(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'src/gap.py', 'gap.py', 'py', 'infra', 'unknown', "
        "NULL, 50, 500, 'abc', 0, 0, 0)"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "src/gap.py" in result.output
    assert "enrichment-gap" in result.output


def test_brief_structure_has_support_line(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'tests/test_x.py', 'test_x.py', 'py', 'test', 'stable', "
        "NULL, 10, 100, 'abc', 1, 0, 0)"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "support:" in result.output
    assert "test 1" in result.output


def test_brief_effects_shows_path_for_single_file(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'infra/llm.py', 'llm.py', 'py', 'infra', 'stable', "
        "NULL, 50, 500, 'abc', 0, 0, 0)"
    )
    conn.execute("INSERT INTO side_effects (item_id, effect) VALUES (1, 'network')")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "network" in result.output
    assert "infra/llm.py" in result.output


def test_brief_domain_excludes_init_files(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'domain/__init__.py', '__init__.py', 'py', 'domain', 'stable', "
        "'pkg init', 0, 0, 'abc', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (2, 'domain/entity.py', 'entity.py', 'py', 'domain', 'stable', "
        "'the entity', 50, 500, 'def', 0, 0, 0)"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "domain/__init__.py" not in result.output
    assert "domain/entity.py" in result.output


def test_brief_invariants_excludes_test_layer(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'src/app.py', 'app.py', 'py', 'application', 'stable', "
        "'the app', 50, 500, 'abc', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (2, 'tests/test_app.py', 'test_app.py', 'py', 'test', 'stable', "
        "'tests', 50, 500, 'def', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) VALUES (1, 0, 'system contract')"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) VALUES (2, 0, 'test convention')"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "system contract" in result.output
    assert "test convention" not in result.output


def test_reset_confirmed_deletes_db(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    db_file = tmp_path / ".sourcemap" / "index.db"
    assert db_file.exists()
    result = runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\nn\n")
    assert result.exit_code == 0
    assert not db_file.exists()
    assert "irreversible" in result.output


def test_reset_with_backup_creates_bak_file(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    maps_dir = tmp_path / ".sourcemap"
    result = runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\ny\n")
    assert result.exit_code == 0
    bak_files = list(maps_dir.glob("index.*.bak"))
    assert len(bak_files) == 1
    assert "Backup saved" in result.output


def test_reset_without_backup_no_bak_file(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    maps_dir = tmp_path / ".sourcemap"
    runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\nn\n")
    assert not list(maps_dir.glob("index.*.bak"))


def test_reset_aborted_keeps_maps(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["reset", "--root", str(tmp_path)], input="n\n")
    assert result.exit_code == 0
    assert (tmp_path / ".sourcemap").exists()
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
    maps_dir = tmp_path / ".sourcemap"
    runner.invoke(app, ["reset", "--root", str(tmp_path)], input="y\ny\n")
    bak_files = list(maps_dir.glob("index.*.bak"))
    assert len(bak_files) == 1
    result = runner.invoke(app, ["restore", "--root", str(tmp_path)], input="1\n")
    assert result.exit_code == 0
    assert "Restored from" in result.output
    assert (maps_dir / "index.db").exists()


def test_restore_invalid_selection_exits(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    maps_dir = tmp_path / ".sourcemap"
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


def test_enrich_export_llm_prompt_exits_without_enriching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path), "--export-llm-prompt"])
    assert result.exit_code == 0
    assert "exported" in result.output


def test_enrich_export_llm_prompt_creates_default_md_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["enrich", "--root", str(tmp_path), "--export-llm-prompt"])
    default_file = tmp_path / ".sourcemap" / "prompt.md"
    assert default_file.exists()
    assert len(default_file.read_text()) > 0


def test_enrich_export_llm_prompt_content_matches_system_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.infra.llm_client import SYSTEM_PROMPT

    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["enrich", "--root", str(tmp_path), "--export-llm-prompt"])
    default_file = tmp_path / ".sourcemap" / "prompt.md"
    assert default_file.read_text(encoding="utf-8") == SYSTEM_PROMPT


def test_enrich_export_llm_prompt_with_custom_output_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    out_file = tmp_path / "my-prompt.md"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(
        app, ["enrich", "--root", str(tmp_path), "--export-llm-prompt", "--output", str(out_file)]
    )
    assert out_file.exists()
    assert len(out_file.read_text()) > 0


def test_enrich_uses_custom_prompt_from_import_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_args, **_kwargs: right(EnrichReport(enriched=1, failed=0, skipped=0, errors=())),
    )
    import_file = tmp_path / "custom-prompt.md"
    import_file.write_text("custom instructions here", encoding="utf-8")
    monkeypatch.setenv("SOURCEMAP_IMPORT_LLM_PROMPT", str(import_file))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "custom-prompt.md" in result.output


def test_enrich_export_llm_prompt_fails_on_non_md_output(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(
        app,
        [
            "enrich",
            "--root",
            str(tmp_path),
            "--export-llm-prompt",
            "--output",
            str(tmp_path / "out.txt"),
        ],
    )
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


def test_enrich_runs_walk_before_enrich(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport
    from sourcemap_indexer.application.sync import SyncReport
    from sourcemap_indexer.lib.either import right

    call_order: list[str] = []
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_walk",
        lambda *_a, **_kw: (call_order.append("walk"), right(0))[1],
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_sync",
        lambda *_a, **_kw: (call_order.append("sync"), right(SyncReport(0, 0, 0, 0)))[1],
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_a, **_kw: (call_order.append("enrich"), right(EnrichReport(0, 0, 0, ())))[1],
    )
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert "walk" in call_order
    assert "enrich" in call_order
    assert call_order.index("walk") < call_order.index("enrich")


def test_enrich_shows_sync_insertions_from_pre_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sourcemap_indexer.cli as cli_module
    from sourcemap_indexer.application.enrich import EnrichReport
    from sourcemap_indexer.application.sync import SyncReport
    from sourcemap_indexer.lib.either import right

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_walk",
        lambda *_a, **_kw: right(3),
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_sync",
        lambda *_a, **_kw: right(SyncReport(inserted=3, updated=0, soft_deleted=0, unchanged=0)),
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_a, **_kw: right(EnrichReport(enriched=3, failed=0, skipped=0, errors=())),
    )
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Inserted" in result.output


def test_build_enrich_header_shows_provider_name() -> None:
    from sourcemap_indexer.cli.indexing.enrich import _build_enrich_header  # noqa: PLC0415

    result = _build_enrich_header(None, None, None, "claude-cli")
    assert "claude-cli" in result


def test_build_enrich_header_shows_cli_model_when_set() -> None:
    from sourcemap_indexer.cli.indexing.enrich import _build_enrich_header  # noqa: PLC0415

    result = _build_enrich_header(
        None, None, None, "claude-cli", cli_model="claude-haiku-4-5-20251001"
    )
    assert "claude-haiku-4-5-20251001" in result


def test_build_enrich_header_shows_cli_effort_when_set() -> None:
    from sourcemap_indexer.cli.indexing.enrich import _build_enrich_header  # noqa: PLC0415

    result = _build_enrich_header(None, None, None, "claude-cli", cli_effort="high")
    assert "high" in result


def test_build_enrich_header_omits_model_effort_when_not_set() -> None:
    from sourcemap_indexer.cli.indexing.enrich import _build_enrich_header  # noqa: PLC0415

    result = _build_enrich_header(None, None, None, "claude-cli")
    assert "Model" not in result
    assert "Effort" not in result


def test_llm_summary_line_shows_claude_cli_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib  # noqa: PLC0415

    monkeypatch.setenv("SOURCEMAP_LLM_PROVIDER", "claude-cli")
    monkeypatch.delenv("SOURCEMAP_LLM_CLI_MODEL", raising=False)
    monkeypatch.delenv("SOURCEMAP_LLM_CLI_EFFORT", raising=False)
    import sourcemap_indexer.cli.insights.stats as stats_mod  # noqa: PLC0415

    importlib.reload(stats_mod)
    result = stats_mod._llm_summary_line()
    assert "claude-cli" in result
    assert "not configured" not in result


def test_llm_summary_line_shows_cli_model_and_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib  # noqa: PLC0415

    monkeypatch.setenv("SOURCEMAP_LLM_PROVIDER", "claude-cli")
    monkeypatch.setenv("SOURCEMAP_LLM_CLI_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("SOURCEMAP_LLM_CLI_EFFORT", "high")
    import sourcemap_indexer.cli.insights.stats as stats_mod  # noqa: PLC0415

    importlib.reload(stats_mod)
    result = stats_mod._llm_summary_line()
    assert "claude-haiku-4-5-20251001" in result


def test_enrich_with_context_flag_passes_true_to_run_enrich(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sourcemap_indexer.cli as cli_module  # noqa: PLC0415
    from sourcemap_indexer.application.enrich import EnrichReport  # noqa: PLC0415
    from sourcemap_indexer.lib.either import right  # noqa: PLC0415

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    captured: list[bool] = []

    def _spy(*_args: object, **kwargs: object) -> object:
        captured.append(bool(kwargs.get("with_context", False)))
        return right(EnrichReport(enriched=0, failed=0, skipped=0, errors=()))

    monkeypatch.setattr("sourcemap_indexer.cli.indexing.enrich.run_enrich", _spy)
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["enrich", "--with-context", "--root", str(tmp_path)])
    assert captured and captured[0] is True


def test_enrich_without_context_flag_passes_false_to_run_enrich(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sourcemap_indexer.cli as cli_module  # noqa: PLC0415
    from sourcemap_indexer.application.enrich import EnrichReport  # noqa: PLC0415
    from sourcemap_indexer.lib.either import right  # noqa: PLC0415

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    captured: list[bool] = []

    def _spy(*_args: object, **kwargs: object) -> object:
        captured.append(bool(kwargs.get("with_context", False)))
        return right(EnrichReport(enriched=0, failed=0, skipped=0, errors=()))

    monkeypatch.setattr("sourcemap_indexer.cli.indexing.enrich.run_enrich", _spy)
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert captured and captured[0] is False


def test_show_loading_runs_without_error() -> None:
    from unittest.mock import patch  # noqa: PLC0415

    with patch("time.sleep"):
        result = runner.invoke(app, ["show-loading", "--files", "3"])
    assert result.exit_code == 0
