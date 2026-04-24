from __future__ import annotations

import math
import os
from dataclasses import dataclass

import typer
from rich.console import Console as _Console
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from sourcemap_indexer.application.sync import SyncReport, run_sync
from sourcemap_indexer.application.walk import run_walk
from sourcemap_indexer.cli._rendering import (
    _color_legend,
    _DotBarColumn,
    _enriched_bar,
    _lang_color,
    _panel,
    _proportional_width,
)
from sourcemap_indexer.cli._shared import _open_repo, _resolve_root, app
from sourcemap_indexer.config import (
    index_yaml_path,
    llm_cli_effort,
    llm_cli_model,
    llm_provider_name,
)
from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.infra.config.dotenv import load_dotenv
from sourcemap_indexer.infra.llm.llm_client import from_environ, is_llm_configured
from sourcemap_indexer.lib.either import Left


@dataclass(frozen=True)
class _Breakdowns:
    by_layer: dict[str, int]
    by_lang: dict[str, int]
    pending_by_layer: dict[str, int]
    pending_by_lang: dict[str, int]


def _compute_breakdowns(items: list[Item]) -> _Breakdowns:
    by_layer: dict[str, int] = {}
    by_lang: dict[str, int] = {}
    pending_by_layer: dict[str, int] = {}
    pending_by_lang: dict[str, int] = {}
    for item in items:
        by_layer[str(item.layer)] = by_layer.get(str(item.layer), 0) + 1
        by_lang[str(item.language)] = by_lang.get(str(item.language), 0) + 1
        if item.needs_llm:
            pending_by_layer[str(item.layer)] = pending_by_layer.get(str(item.layer), 0) + 1
            pending_by_lang[str(item.language)] = pending_by_lang.get(str(item.language), 0) + 1
    return _Breakdowns(by_layer, by_lang, pending_by_layer, pending_by_lang)


def _compute_pct(enriched: int, total: int) -> int:
    if total == 0:
        return 0
    return round(enriched / total * 100)


def _llm_summary_line() -> str:
    provider = llm_provider_name()
    if provider != "http":
        model = llm_cli_model() or "default"
        effort = llm_cli_effort()
        effort_str = f"  [dim]effort: {effort}[/dim]" if effort else ""
        return f"[bold]LLM[/bold]    {provider}  [dim]({model})[/dim]{effort_str}"
    if is_llm_configured():
        llm = from_environ()
        return f"[bold]LLM[/bold]    {llm.model}  [dim]({llm.url})[/dim]"
    return "[dim]LLM: not configured[/dim]"


def _print_layer_rows(
    console: _Console,
    by_layer: dict[str, int],
    pending_by_layer: dict[str, int],
) -> None:
    col = max((len(k) for k in by_layer), default=0)
    top = max(by_layer.values(), default=1)
    rows = []
    for name, cnt in sorted(by_layer.items(), key=lambda x: -x[1]):
        clr = _lang_color(pending_by_layer.get(name, 0))
        enriched_in_layer = cnt - pending_by_layer.get(name, 0)
        bar = _enriched_bar(enriched_in_layer, cnt, _proportional_width(cnt, top))
        rows.append(f"  {name:<{col}}  {cnt:>5}  [{clr}]{bar}[/{clr}]")
    console.print(_panel("\n".join(rows) or "[dim](no data)[/dim]", title="By layer"))


def _print_lang_rows(
    console: _Console,
    by_lang: dict[str, int],
    pending_by_lang: dict[str, int],
) -> None:
    col = max((len(k) for k in by_lang), default=0)
    top_lang = max(by_lang.values(), default=1)
    rows = []
    for lang, cnt in sorted(by_lang.items(), key=lambda x: -x[1]):
        clr = _lang_color(pending_by_lang.get(lang, 0))
        enriched_in_lang = cnt - pending_by_lang.get(lang, 0)
        wid = _proportional_width(cnt, top_lang)
        rows.append(
            f"  {lang:<{col}}  {cnt:>5}  [{clr}]{_enriched_bar(enriched_in_lang, cnt, wid)}[/{clr}]"
        )
    console.print(_panel("\n".join(rows) or "[dim](no data)[/dim]", title="By language"))


def _maybe_print_sync_report(console: _Console, report: SyncReport) -> None:
    if report.inserted or report.updated or report.soft_deleted:
        console.print(
            _panel(
                f"[bold]Inserted[/bold]: {report.inserted}   "
                f"[bold]Updated[/bold]: {report.updated}   "
                f"[bold]Soft-deleted[/bold]: {report.soft_deleted}",
                "Sync",
            )
        )


def _render_pending_files(
    console: _Console,
    pending_items: list[Item],
    pending: int,
    page: int,
    page_size: int,
) -> None:
    if not pending_items:
        return
    total_pages = math.ceil(pending / page_size)
    page = max(1, min(page, total_pages))
    page_slice = pending_items[(page - 1) * page_size : page * page_size]
    pending_rows = "\n".join(f"  [dim]{item.language:<6}[/dim]  {item.path}" for item in page_slice)
    footer = f"\n  [dim]page {page}/{total_pages} · {pending} total[/dim]"
    if total_pages > 1:
        footer += f"  [dim]--page N to navigate (1–{total_pages})[/dim]"
    console.print(_panel(pending_rows + footer, title="Pending", style="warn"))


_STATS_HELP = (
    "Show total, enriched, and pending counts broken down by layer and language."
    " Add --files to list pending files (combine with --page N)."
    " Page size: SOURCEMAP_PAGE_SIZE (default 20)."
)


@app.command(help=_STATS_HELP)
def stats(
    root: str | None = typer.Option(None, help="Project root"),
    files: bool = typer.Option(False, "--files", help="List pending files"),
    page: int = typer.Option(1, "--page", help="Page of pending files (requires --files)"),
) -> None:
    project_root = _resolve_root(root)
    load_dotenv(project_root / ".env")
    page_size = int(os.environ.get("SOURCEMAP_PAGE_SIZE", "20"))
    output = index_yaml_path(project_root)
    console = _Console()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        _DotBarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as prog:
        task_scan = prog.add_task("Scanning files...", total=None)
        walk_result = run_walk(project_root, output)
        if isinstance(walk_result, Left):
            typer.echo(f"Error: {walk_result.error}", err=True)
            raise typer.Exit(1)
        prog.update(task_scan, visible=False)
        task_sync = prog.add_task("Indexing...", total=walk_result.value)
        repo = _open_repo(project_root)
        sync_result = run_sync(
            output,
            repo,
            on_progress=lambda cur, _tot: prog.update(task_sync, completed=cur),
        )
        if isinstance(sync_result, Left):
            typer.echo(f"Error: {sync_result.error}", err=True)
            raise typer.Exit(1)

    _maybe_print_sync_report(console, sync_result.value)

    all_result = repo.search(tags=None, layer=None, language=None)
    if isinstance(all_result, Left):
        typer.echo(f"Error: {all_result.error}", err=True)
        raise typer.Exit(1)

    items = all_result.value
    total = len(items)
    enriched = sum(1 for item in items if not item.needs_llm)
    pending_items = [item for item in items if item.needs_llm]
    pending = len(pending_items)
    breakdowns = _compute_breakdowns(items)
    pct = _compute_pct(enriched, total)
    dot_filled = round(pct / 100 * 20)
    bar_clr = _lang_color(pending)
    dot_bar = (
        f"[{bar_clr}]"
        + "●" * dot_filled
        + f"[/{bar_clr}]"
        + "[dim]"
        + "○" * (20 - dot_filled)
        + "[/dim]"
    )
    summary = (
        f"[bold]Root[/bold]   {project_root}\n"
        f"{_llm_summary_line()}\n"
        f"[bold]Total[/bold]: {total:<6}  [bold]Enriched[/bold]: {enriched:<6}"
        f"  [bold]Pending[/bold]: {pending}\n"
        f"{dot_bar}  {pct}%"
    )
    console.print(_panel(summary, title="Stats"))
    _print_layer_rows(console, breakdowns.by_layer, breakdowns.pending_by_layer)
    _print_lang_rows(console, breakdowns.by_lang, breakdowns.pending_by_lang)
    console.print(_color_legend())
    if files:
        _render_pending_files(console, pending_items, pending, page, page_size)
