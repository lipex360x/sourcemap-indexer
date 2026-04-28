from __future__ import annotations

import typer

from sourcemap_indexer.cli._shared import _open_repo, _resolve_root, app
from sourcemap_indexer.infra.fs.walker import walk_project
from sourcemap_indexer.lib.either import Left


@app.command(help="Check that every file on disk is indexed. Exit 1 if any are missing.")
def validate(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)

    db_result = repo.find_all_paths()
    if isinstance(db_result, Left):
        typer.echo(f"FAIL:{db_result.error}", err=True)
        raise typer.Exit(1)

    walk_result = walk_project(project_root)
    if isinstance(walk_result, Left):
        typer.echo(f"FAIL:{walk_result.error}", err=True)
        raise typer.Exit(1)

    db_paths = db_result.value
    disk_paths = {walked.path for walked in walk_result.value}
    missing = sorted(disk_paths - db_paths)

    if missing:
        for path in missing:
            typer.echo(f"MISSING:{path}")
        raise typer.Exit(1)

    typer.echo("PASS:sourcemap-db")
