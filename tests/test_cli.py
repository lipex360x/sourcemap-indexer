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


def test_brief_shows_project_meta_when_configured(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    (tmp_path / ".sourcemap" / "project.yaml").write_text(
        "name: demo\nversion: 1\npurpose: testing the brief\naudience: claude\nlicense: MIT\n"
    )
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "name" in result.output
    assert "demo" in result.output
    assert "testing the brief" in result.output
    assert "MIT" in result.output


def test_brief_omits_project_section_when_absent(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "license" not in result.output
    assert "audience" not in result.output


def test_brief_renders_partial_project_fields(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    (tmp_path / ".sourcemap" / "project.yaml").write_text("name: partial\n")
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "partial" in result.output
    assert "audience" not in result.output
    assert "license" not in result.output


def test_brief_fails_on_malformed_project_yaml(tmp_path: Path) -> None:
    _init_sync(tmp_path)
    (tmp_path / ".sourcemap" / "project.yaml").write_text("name: [\nbroken")
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code != 0
    assert "project-yaml-invalid" in result.output


def _seed_verbose_db(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'stacks/python.yaml', 'python.yaml', 'yaml', 'stacks', 'stable', "
        "'Python 3.11+ mapping', 50, 500, 'abc', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (2, 'enforcement/03-tools.yaml', '03-tools.yaml', 'yaml', "
        "'enforcement', 'stable', 'Tool categories', 60, 600, 'def', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (3, 'unfinished.md', 'unfinished.md', 'md', 'doc', 'unknown', "
        "NULL, 10, 100, 'ghi', 1, 0, 0)"
    )
    conn.commit()
    conn.close()


def test_brief_verbose_lists_files_by_layer(tmp_path: Path) -> None:
    _seed_verbose_db(tmp_path)
    result = runner.invoke(app, ["brief", "--verbose", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Files by layer" in result.output
    assert "stacks/python.yaml" in result.output
    assert "Python 3.11+ mapping" in result.output
    assert "enforcement/03-tools.yaml" in result.output
    assert "Tool categories" in result.output


def test_brief_verbose_short_flag(tmp_path: Path) -> None:
    _seed_verbose_db(tmp_path)
    result = runner.invoke(app, ["brief", "-v", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Files by layer" in result.output


def test_brief_default_hides_verbose_section(tmp_path: Path) -> None:
    _seed_verbose_db(tmp_path)
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Files by layer" not in result.output


def test_brief_verbose_lists_pending_with_stale_purpose(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'stacks/python.yaml', 'python.yaml', 'yaml', 'stacks', 'stable', "
        "'Python stack config', 50, 500, 'abc', 1, 0, 0)"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--verbose", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "stacks/python.yaml" in result.output
    assert "[pending]" in result.output
    assert "Python stack config" in result.output


def test_brief_verbose_lists_pending_without_purpose(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'stacks/new.yaml', 'new.yaml', 'yaml', 'stacks', 'unknown', "
        "NULL, 10, 100, 'ghi', 1, 0, 0)"
    )
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["brief", "--verbose", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "stacks/new.yaml" in result.output
    assert "[pending]" in result.output


def test_brief_verbose_groups_layer_header(tmp_path: Path) -> None:
    _seed_verbose_db(tmp_path)
    result = runner.invoke(app, ["brief", "--verbose", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "stacks/" in result.output
    assert "enforcement/" in result.output


def test_brief_verbose_empty_when_no_items(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["brief", "--verbose", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Files by layer" in result.output
    assert "no enriched data" in result.output


def _seed_contracts_db(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (1, 'foundations/01-philosophy.md', '01-philosophy.md', 'md', "
        "'foundations', 'core', 'principles', 100, 500, 'abc', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (2, 'enforcement/03-tools.yaml', '03-tools.yaml', 'yaml', "
        "'enforcement', 'stable', 'tool categories', 100, 500, 'def', 0, 0, 0)"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) "
        "VALUES (1, 0, 'Rules enforced by gates')"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) "
        "VALUES (1, 1, 'Violations impossible to commit')"
    )
    conn.execute(
        "INSERT INTO invariants (item_id, position, invariant) "
        "VALUES (2, 0, 'Each tool category defines enforces property')"
    )
    conn.commit()
    conn.close()


def test_contracts_shows_invariants_grouped_by_layer(tmp_path: Path) -> None:
    _seed_contracts_db(tmp_path)
    result = runner.invoke(app, ["contracts", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "foundations" in result.output
    assert "enforcement" in result.output
    assert "Rules enforced by gates" in result.output
    assert "Each tool category defines enforces property" in result.output


def test_contracts_filters_by_layer(tmp_path: Path) -> None:
    _seed_contracts_db(tmp_path)
    result = runner.invoke(app, ["contracts", "--root", str(tmp_path), "--layer", "foundations"])
    assert result.exit_code == 0
    assert "Rules enforced by gates" in result.output
    assert "Each tool category defines enforces property" not in result.output


def test_contracts_empty_state(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["contracts", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No contracts found" in result.output


def test_contracts_fails_without_index(tmp_path: Path) -> None:
    result = runner.invoke(app, ["contracts", "--root", str(tmp_path / "missing")])
    assert result.exit_code != 0


def test_contracts_includes_path_under_layer(tmp_path: Path) -> None:
    _seed_contracts_db(tmp_path)
    result = runner.invoke(app, ["contracts", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "foundations/01-philosophy.md" in result.output
    assert "enforcement/03-tools.yaml" in result.output


def _seed_chapters_db(tmp_path: Path) -> None:
    db_file = tmp_path / ".sourcemap" / "index.db"
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    conn = sqlite3.connect(str(db_file))
    rows = [
        (
            1,
            "foundations/00-overview.md",
            "00-overview.md",
            "md",
            "foundations",
            "stable",
            "entry point",
        ),
        (
            2,
            "foundations/01-philosophy.md",
            "01-philosophy.md",
            "md",
            "foundations",
            "core",
            "principles",
        ),
        (
            3,
            "enforcement/03-tools.yaml",
            "03-tools.yaml",
            "yaml",
            "enforcement",
            "stable",
            "tool categories",
        ),
        (4, "pending.md", "pending.md", "md", "unknown", "unknown", None),
    ]
    for item in rows[:3]:
        conn.execute(
            "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
            "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 100, 500, 'abc', 0, 0, 0)",
            item,
        )
    conn.execute(
        "INSERT INTO items (id, path, name, language, layer, stability, purpose, "
        "lines, size_bytes, content_hash, needs_llm, created_at, updated_at) "
        "VALUES (4, 'pending.md', 'pending.md', 'md', 'unknown', 'unknown', NULL, "
        "10, 50, 'def', 1, 0, 0)"
    )
    conn.commit()
    conn.close()


def test_chapters_lists_enriched_files_grouped_by_layer(tmp_path: Path) -> None:
    _seed_chapters_db(tmp_path)
    result = runner.invoke(app, ["chapters", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "foundations" in result.output
    assert "enforcement" in result.output
    assert "00-overview.md" in result.output
    assert "03-tools.yaml" in result.output


def test_chapters_preserves_alphabetical_path_order(tmp_path: Path) -> None:
    _seed_chapters_db(tmp_path)
    result = runner.invoke(app, ["chapters", "--root", str(tmp_path)])
    assert result.exit_code == 0
    idx_00 = result.output.find("00-overview.md")
    idx_01 = result.output.find("01-philosophy.md")
    assert idx_00 < idx_01


def test_chapters_shows_purpose_per_file(tmp_path: Path) -> None:
    _seed_chapters_db(tmp_path)
    result = runner.invoke(app, ["chapters", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "entry point" in result.output
    assert "tool categories" in result.output


def test_chapters_excludes_non_enriched(tmp_path: Path) -> None:
    _seed_chapters_db(tmp_path)
    result = runner.invoke(app, ["chapters", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "pending.md" not in result.output


def test_chapters_filters_by_layer(tmp_path: Path) -> None:
    _seed_chapters_db(tmp_path)
    result = runner.invoke(app, ["chapters", "--root", str(tmp_path), "--layer", "enforcement"])
    assert result.exit_code == 0
    assert "03-tools.yaml" in result.output
    assert "00-overview.md" not in result.output


def test_chapters_empty_state(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["chapters", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No chapters found" in result.output


def test_chapters_fails_without_index(tmp_path: Path) -> None:
    result = runner.invoke(app, ["chapters", "--root", str(tmp_path / "missing")])
    assert result.exit_code != 0


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
    from sourcemap_indexer.infra.llm.llm_client import SYSTEM_PROMPT

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


def test_enrich_shows_layer_mismatches_in_summary(
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
        lambda *_a, **_kw: right(1),
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_sync",
        lambda *_a, **_kw: right(SyncReport(inserted=0, updated=0, soft_deleted=0, unchanged=1)),
    )
    report = EnrichReport(
        enriched=1,
        failed=0,
        skipped=0,
        errors=(),
        layer_mismatches=(("foundations/intro.md", "doc", "foundations"),),
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_a, **_kw: right(report),
    )
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Layer mismatches" in result.output
    assert "foundations/intro.md" in result.output
    assert "doc" in result.output
    assert "foundations" in result.output


def test_enrich_without_mismatches_omits_mismatch_section(
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
        lambda *_a, **_kw: right(1),
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_sync",
        lambda *_a, **_kw: right(SyncReport(inserted=0, updated=0, soft_deleted=0, unchanged=1)),
    )
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_a, **_kw: right(EnrichReport(enriched=1, failed=0, skipped=0, errors=())),
    )
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Layer mismatches" not in result.output


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


def test_open_repo_exits_on_init_db_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    monkeypatch.setattr("sourcemap_indexer.cli._shared.init_db", lambda _p: mk_left("db-error"))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["walk", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_resolve_root_exits_when_find_project_root_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    monkeypatch.setattr(
        "sourcemap_indexer.cli._shared.find_project_root", lambda _p: mk_left("no-root")
    )
    result = runner.invoke(app, ["walk"])
    assert result.exit_code != 0


def test_load_enrich_context_returns_left_when_layers_config_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.load_user_layers",
        lambda _p: mk_left("layers-yaml-invalid"),
    )
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path), "--export-llm-prompt"])
    assert result.exit_code != 0


def test_create_http_client_exits_on_ping_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sourcemap_indexer.cli as cli_module  # noqa: PLC0415
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: mk_left("llm-unreachable"))
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_create_provider_non_http_returns_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.application.enrich import EnrichReport  # noqa: PLC0415
    from sourcemap_indexer.lib.either import right as mk_right  # noqa: PLC0415

    monkeypatch.setenv("SOURCEMAP_LLM_PROVIDER", "claude-cli")
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_enrich",
        lambda *_a, **_kw: mk_right(EnrichReport(enriched=0, failed=0, skipped=0, errors=())),
    )
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_kw: subprocess.CompletedProcess([], 0, "", "")
    )
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code == 0


def test_build_enrich_header_shows_instruction_when_message_set() -> None:
    from sourcemap_indexer.cli.indexing.enrich import _build_enrich_header  # noqa: PLC0415

    result = _build_enrich_header(None, None, "write in English", "claude-cli")
    assert "Instruction" in result
    assert "write in English" in result


def test_enrich_walk_failure_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sourcemap_indexer.cli as cli_module  # noqa: PLC0415
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://test/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    monkeypatch.setattr(cli_module.LlmClient, "ping", lambda _self: right(None))
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.enrich.run_walk",
        lambda *_a, **_kw: mk_left("walk-error"),
    )
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_walk_command_exits_on_sync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    (tmp_path / "app.py").write_text("x = 1\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.cli.indexing.walk.run_sync",
        lambda *_a, **_kw: mk_left("sync-failed"),
    )
    result = runner.invoke(app, ["walk", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_find_command_exits_on_search_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.infra.db.sqlite_repo.SqliteItemRepository.search",
        lambda _self, **_kw: mk_left("db-error"),
    )
    result = runner.invoke(app, ["find", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_show_command_exits_on_find_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.infra.db.sqlite_repo.SqliteItemRepository.find_by_path",
        lambda _self, _p: mk_left("db-error"),
    )
    result = runner.invoke(app, ["show", "app.py", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_stale_command_exits_on_search_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.infra.db.sqlite_repo.SqliteItemRepository.search",
        lambda _self, **_kw: mk_left("db-error"),
    )
    result = runner.invoke(app, ["stale", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_stats_walk_failure_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.cli.insights.stats.run_walk",
        lambda *_a, **_kw: mk_left("walk-error"),
    )
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_stats_sync_failure_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.cli.insights.stats.run_sync",
        lambda *_a, **_kw: mk_left("sync-error"),
    )
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_stats_search_failure_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sourcemap_indexer.lib.either import left as mk_left  # noqa: PLC0415

    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.infra.db.sqlite_repo.SqliteItemRepository.search",
        lambda _self, **_kw: mk_left("search-error"),
    )
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_stats_files_flag_returns_early_when_no_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path), "--files"])
    assert result.exit_code == 0


def test_stats_files_flag_multi_page_shows_navigation_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    monkeypatch.setenv("SOURCEMAP_PAGE_SIZE", "1")
    for idx in range(3):
        (tmp_path / f"file{idx}.py").write_text(f"x = {idx}\n")
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path), "--files"])
    assert result.exit_code == 0
    assert "--page" in result.output


def test_brief_structure_shows_no_data_on_empty_db(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["brief", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no data" in result.output


def test_profile_no_src_files_shows_fallback(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["profile", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No test files detected" in result.output


def test_enrich_exits_on_unknown_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setenv("SOURCEMAP_LLM_PROVIDER", "unknown-xyz")
    result = runner.invoke(app, ["enrich", "--root", str(tmp_path)])
    assert result.exit_code != 0


def test_stats_pending_section_skipped_when_no_pending(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--root", str(tmp_path)])
    result = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert result.exit_code == 0


def test_resolve_root_success_returns_value_from_find_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sourcemap_indexer.lib.either import right as mk_right  # noqa: PLC0415

    runner.invoke(app, ["init", "--root", str(tmp_path)])
    monkeypatch.setattr(
        "sourcemap_indexer.cli._shared.find_project_root", lambda _p: mk_right(tmp_path)
    )
    result = runner.invoke(app, ["walk"])
    assert result.exit_code == 0


def test_render_pending_files_returns_early_when_empty() -> None:
    from io import StringIO  # noqa: PLC0415

    from rich.console import Console as _RichConsole  # noqa: PLC0415

    from sourcemap_indexer.cli.insights.stats import _render_pending_files  # noqa: PLC0415

    console = _RichConsole(file=StringIO())
    _render_pending_files(console, [], 0, 1, 20)
