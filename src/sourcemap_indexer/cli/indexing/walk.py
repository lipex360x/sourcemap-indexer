from __future__ import annotations

import time

import typer
from rich.console import Console as _Console

from sourcemap_indexer.application.sync import run_sync
from sourcemap_indexer.application.walk import run_walk
from sourcemap_indexer.cli._rendering import _panel
from sourcemap_indexer.cli._shared import _open_repo, _resolve_root, app
from sourcemap_indexer.config import index_yaml_path
from sourcemap_indexer.lib.either import Left


@app.command(help="Scan the project and sync file metadata into the database.")
def walk(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    output = index_yaml_path(project_root)
    repo = _open_repo(project_root)
    console = _Console()

    walk_start = time.perf_counter()
    walk_result = run_walk(project_root, output, known_files=repo.load_known_files())
    walk_elapsed = time.perf_counter() - walk_start

    if isinstance(walk_result, Left):
        typer.echo(f"Error: {walk_result.error}", err=True)
        raise typer.Exit(1)

    sync_start = time.perf_counter()
    sync_result = run_sync(output, repo)
    sync_elapsed = time.perf_counter() - sync_start

    if isinstance(sync_result, Left):
        typer.echo(f"Error: {sync_result.error}", err=True)
        raise typer.Exit(1)

    report = sync_result.value
    walk_body = (
        f"  [bold]Root[/bold]   {project_root}\n"
        f"  [bold]Files[/bold]  {walk_result.value}  [dim]scanned in {walk_elapsed:.2f}s[/dim]"
    )
    console.print(_panel(walk_body, title="Walk"))
    sync_body = (
        f"  [bold]Inserted[/bold]      {report.inserted}\n"
        f"  [bold]Updated[/bold]       {report.updated}\n"
        f"  [bold]Soft-deleted[/bold]  {report.soft_deleted}\n"
        f"  [bold]Unchanged[/bold]     {report.unchanged}  "
        f"[dim]synced in {sync_elapsed:.2f}s[/dim]"
    )
    console.print(_panel(sync_body, title="Sync"))
