from __future__ import annotations

import typer

from sourcemap_indexer.application.sync import run_sync
from sourcemap_indexer.cli._shared import _open_repo, _resolve_root, app
from sourcemap_indexer.config import index_yaml_path
from sourcemap_indexer.lib.either import Left


@app.command(help="Import index.yaml into the SQLite database (insert / update / soft-delete).")
def sync(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)
    index = index_yaml_path(project_root)
    sync_result = run_sync(index, repo)
    if isinstance(sync_result, Left):
        typer.echo(f"Error: {sync_result.error}", err=True)
        raise typer.Exit(1)
    report = sync_result.value
    typer.echo(
        f"Sync: inserted={report.inserted} updated={report.updated} "
        f"soft_deleted={report.soft_deleted} unchanged={report.unchanged}"
    )
