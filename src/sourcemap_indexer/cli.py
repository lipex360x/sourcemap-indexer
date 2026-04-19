from __future__ import annotations

from pathlib import Path

import typer

from sourcemap_indexer.application.enrich import run_enrich
from sourcemap_indexer.application.sync import run_sync
from sourcemap_indexer.application.walk import run_walk
from sourcemap_indexer.config import db_path, find_project_root, index_yaml_path
from sourcemap_indexer.domain.value_objects import Language, Layer
from sourcemap_indexer.infra.llama_client import LlamaClient, from_environ
from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Left

app = typer.Typer(help="Codebase indexer powered by local LLM")

_DEFAULT_SOURCEMAPIGNORE = ".venv/\n.git/\n__pycache__/\n*.pyc\ndist/\nbuild/\n*.db\n*.sqlite\n"


def _resolve_root(root: str | None) -> Path:
    if root:
        return Path(root).resolve()
    result = find_project_root(Path.cwd())
    if isinstance(result, Left):
        typer.echo(f"Error: {result.error}", err=True)
        raise typer.Exit(1)
    return result.value


def _open_repo(root: Path) -> SqliteItemRepository:
    path = db_path(root)
    result = init_db(path)
    if isinstance(result, Left):
        typer.echo(f"Error: {result.error}", err=True)
        raise typer.Exit(1)
    return SqliteItemRepository(result.value)


@app.command()
def init(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    maps_dir = project_root / ".docs" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    ignore_file = project_root / ".sourcemapignore"
    if not ignore_file.exists():
        ignore_file.write_text(_DEFAULT_SOURCEMAPIGNORE, encoding="utf-8")
    result = init_db(db_path(project_root))
    if isinstance(result, Left):
        typer.echo(f"Error: {result.error}", err=True)
        raise typer.Exit(1)
    result.value.close()
    typer.echo(f"Initialized sourcemap at {project_root}")


@app.command()
def walk(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    output = index_yaml_path(project_root)
    walk_result = run_walk(project_root, output)
    if isinstance(walk_result, Left):
        typer.echo(f"Error: {walk_result.error}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Walked {walk_result.value} files → {output}")


@app.command()
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


@app.command()
def enrich(
    root: str | None = typer.Option(None, help="Project root"),
    limit: int | None = typer.Option(None, "--limit", help="Max items to enrich"),
) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)
    config = from_environ()
    client = LlamaClient(config)
    enrich_result = run_enrich(project_root, repo, client, batch_limit=limit)
    if isinstance(enrich_result, Left):
        typer.echo(f"Error: {enrich_result.error}", err=True)
        raise typer.Exit(1)
    report = enrich_result.value
    typer.echo(
        f"Enrich: enriched={report.enriched} failed={report.failed} skipped={report.skipped}"
    )
    for error in report.errors:
        typer.echo(f"  ! {error}", err=True)


@app.command()
def find(
    root: str | None = typer.Option(None, help="Project root"),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
    layer: str | None = typer.Option(None, "--layer", help="Filter by layer"),
    language: str | None = typer.Option(None, "--language", help="Filter by language"),
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


@app.command()
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


@app.command()
def stats(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)
    all_result = repo.search(tags=None, layer=None, language=None)
    if isinstance(all_result, Left):
        typer.echo(f"Error: {all_result.error}", err=True)
        raise typer.Exit(1)
    items = all_result.value
    total = len(items)
    enriched = sum(1 for i in items if not i.needs_llm)
    pending = total - enriched
    by_layer: dict[str, int] = {}
    by_lang: dict[str, int] = {}
    for item in items:
        by_layer[str(item.layer)] = by_layer.get(str(item.layer), 0) + 1
        by_lang[str(item.language)] = by_lang.get(str(item.language), 0) + 1
    typer.echo(f"Total: {total}  Enriched: {enriched}  Pending: {pending}")
    typer.echo("By layer:")
    for layer_name, count in sorted(by_layer.items()):
        typer.echo(f"  {layer_name}: {count}")
    typer.echo("By language:")
    for lang, count in sorted(by_lang.items()):
        typer.echo(f"  {lang}: {count}")


@app.command()
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
