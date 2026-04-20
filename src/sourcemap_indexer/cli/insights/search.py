from __future__ import annotations

import typer

from sourcemap_indexer.cli._shared import (
    _FIND_HELP,
    _LANG_HELP,
    _LAYER_HELP,
    _open_repo,
    _resolve_root,
    app,
)
from sourcemap_indexer.domain.value_objects import Language, Layer
from sourcemap_indexer.lib.either import Left


@app.command(help=_FIND_HELP)
def find(
    root: str | None = typer.Option(None, help="Project root"),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag (free text)"),
    layer: str | None = typer.Option(None, "--layer", help=_LAYER_HELP),
    language: str | None = typer.Option(None, "--language", help=_LANG_HELP),
) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)
    layer_val = Layer(layer) if layer else None
    language_val = Language(language) if language else None
    tags_val = [tag] if tag else None
    search_result = repo.search(tags=tags_val, layer=layer_val, language=language_val)
    if isinstance(search_result, Left):
        typer.echo(f"Error: {search_result.error}", err=True)
        raise typer.Exit(1)
    items = search_result.value
    if not items:
        typer.echo("No items found.")
        return
    for item in items:
        purpose = item.purpose or "(no purpose)"
        typer.echo(f"{item.path}\t{item.language}\t{item.layer}\t{purpose}")


@app.command(help="Show full metadata for a specific file path.")
def show(
    path: str = typer.Argument(help="Relative file path"),
    root: str | None = typer.Option(None, help="Project root"),
) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)
    find_result = repo.find_by_path(path)
    if isinstance(find_result, Left):
        typer.echo(f"Error: {find_result.error}", err=True)
        raise typer.Exit(1)
    item = find_result.value
    if item is None:
        typer.echo(f"Not found: {path}", err=True)
        raise typer.Exit(1)
    typer.echo(f"path:      {item.path}")
    typer.echo(f"language:  {item.language}")
    typer.echo(f"layer:     {item.layer}")
    typer.echo(f"stability: {item.stability}")
    typer.echo(f"purpose:   {item.purpose or '(not enriched)'}")
    typer.echo(f"tags:      {', '.join(sorted(item.tags)) or '(none)'}")
    typer.echo(f"needs_llm: {item.needs_llm}")
    typer.echo(f"lines:     {item.lines}")
    typer.echo(f"size:      {item.size_bytes} bytes")


@app.command(help="List files whose content changed since the last enrich run.")
def stale(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)
    all_result = repo.search(tags=None, layer=None, language=None)
    if isinstance(all_result, Left):
        typer.echo(f"Error: {all_result.error}", err=True)
        raise typer.Exit(1)
    stale_items = [
        item
        for item in all_result.value
        if item.llm_hash is not None and item.llm_hash.hex_value != item.content_hash.hex_value
    ]
    if not stale_items:
        typer.echo("No stale items.")
        return
    for item in stale_items:
        typer.echo(f"{item.path}\t(content changed since last enrich)")
