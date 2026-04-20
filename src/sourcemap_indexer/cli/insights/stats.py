from __future__ import annotations

import math
import os

import typer
from rich.console import Console as _Console
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from sourcemap_indexer.application.sync import run_sync
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
from sourcemap_indexer.config import config_dir, index_yaml_path
from sourcemap_indexer.infra.dotenv import load_dotenv
from sourcemap_indexer.infra.llm_client import from_environ, is_llm_configured
from sourcemap_indexer.lib.either import Left

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
        walk_result = run_walk(project_root, output, config_dir=config_dir(project_root))
        if isinstance(walk_result, Left):
            typer.echo(f"Error: {walk_result.error}", err=True)
            raise typer.Exit(1)
        file_count = walk_result.value
        prog.update(task_scan, visible=False)

        task_sync = prog.add_task("Indexing...", total=file_count)
        repo = _open_repo(project_root)
        sync_result = run_sync(
            output,
            repo,
            on_progress=lambda cur, _tot: prog.update(task_sync, completed=cur),
        )
        if isinstance(sync_result, Left):
            typer.echo(f"Error: {sync_result.error}", err=True)
            raise typer.Exit(1)

    report = sync_result.value
    if report.inserted or report.updated or report.soft_deleted:
        sync_body = (
            f"[bold]Inserted[/bold]: {report.inserted}   "
            f"[bold]Updated[/bold]: {report.updated}   "
            f"[bold]Soft-deleted[/bold]: {report.soft_deleted}"
        )
        console.print(_panel(sync_body, "Sync"))
    all_result = repo.search(tags=None, layer=None, language=None)
    if isinstance(all_result, Left):
        typer.echo(f"Error: {all_result.error}", err=True)
        raise typer.Exit(1)
    items = all_result.value
    total = len(items)
    enriched = sum(1 for i in items if not i.needs_llm)
    pending_items = [i for i in items if i.needs_llm]
    pending = len(pending_items)
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

    pct = round(enriched / total * 100) if total else 0
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

    if is_llm_configured():
        llm = from_environ()
        llm_line = f"[bold]LLM[/bold]    {llm.model}  [dim]({llm.url})[/dim]"
    else:
        llm_line = "[dim]LLM: not configured[/dim]"

    summary = (
        f"[bold]Root[/bold]   {project_root}\n"
        f"{llm_line}\n"
        f"[bold]Total[/bold]: {total:<6}  [bold]Enriched[/bold]: {enriched:<6}"
        f"  [bold]Pending[/bold]: {pending}\n"
        f"{dot_bar}  {pct}%"
    )
    console.print(_panel(summary, title="Stats"))

    col = max((len(k) for k in by_layer), default=0)
    top = max(by_layer.values(), default=1)
    layer_row_list: list[str] = []
    for name, cnt in sorted(by_layer.items(), key=lambda x: -x[1]):
        clr = _lang_color(pending_by_layer.get(name, 0))
        enriched_in_layer = cnt - pending_by_layer.get(name, 0)
        wid_layer = _proportional_width(cnt, top)
        bar_layer = _enriched_bar(enriched_in_layer, cnt, wid_layer)
        layer_row_list.append(f"  {name:<{col}}  {cnt:>5}  [{clr}]{bar_layer}[/{clr}]")
    layer_rows = "\n".join(layer_row_list)
    console.print(_panel(layer_rows or "[dim](no data)[/dim]", title="By layer"))

    col = max((len(k) for k in by_lang), default=0)
    top_lang = max(by_lang.values(), default=1)
    lang_row_list: list[str] = []
    for lang, cnt in sorted(by_lang.items(), key=lambda x: -x[1]):
        clr = _lang_color(pending_by_lang.get(lang, 0))
        enriched_in_lang = cnt - pending_by_lang.get(lang, 0)
        wid = _proportional_width(cnt, top_lang)
        lang_row_list.append(
            f"  {lang:<{col}}  {cnt:>5}  [{clr}]{_enriched_bar(enriched_in_lang, cnt, wid)}[/{clr}]"
        )
    lang_rows = "\n".join(lang_row_list)
    console.print(_panel(lang_rows or "[dim](no data)[/dim]", title="By language"))
    console.print(_color_legend())

    if files and pending_items:
        total_pages = math.ceil(pending / page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        page_slice = pending_items[start : start + page_size]
        pending_rows = "\n".join(
            f"  [dim]{item.language:<6}[/dim]  {item.path}" for item in page_slice
        )
        footer = f"\n  [dim]page {page}/{total_pages} · {pending} total[/dim]"
        if total_pages > 1:
            footer += f"  [dim]--page N to navigate (1–{total_pages})[/dim]"
        console.print(_panel(pending_rows + footer, title="Pending", style="warn"))
