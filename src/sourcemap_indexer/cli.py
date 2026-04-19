from __future__ import annotations

import shutil
import sqlite3
import time
from datetime import datetime
from importlib.resources import files
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

app = typer.Typer(help="Codebase indexer powered by LLM")

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


@app.command(help="Create .docs/maps/ directory and initialize the SQLite index.")
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


@app.command(help="Scan the project and sync file metadata into the database.")
def walk(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    output = index_yaml_path(project_root)
    walk_result = run_walk(project_root, output)
    if isinstance(walk_result, Left):
        typer.echo(f"Error: {walk_result.error}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Walked {walk_result.value} files → {output}")
    repo = _open_repo(project_root)
    sync_result = run_sync(output, repo)
    if isinstance(sync_result, Left):
        typer.echo(f"Error: {sync_result.error}", err=True)
        raise typer.Exit(1)
    report = sync_result.value
    typer.echo(
        f"Sync: inserted={report.inserted} updated={report.updated} "
        f"soft_deleted={report.soft_deleted} unchanged={report.unchanged}"
    )


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


@app.command(help="Send pending files to the LLM and store purpose, tags, layer, and side effects.")
def enrich(
    root: str | None = typer.Option(None, help="Project root"),
    limit: int | None = typer.Option(None, "--limit", help="Max items to enrich"),
) -> None:
    project_root = _resolve_root(root)
    repo = _open_repo(project_root)
    config = from_environ()
    client = LlamaClient(config)
    ping_result = client.ping()
    if isinstance(ping_result, Left):
        typer.echo(f"Error: LLM unreachable — {ping_result.error}", err=True)
        typer.echo(f"  Check that your LLM server is running at: {config.url}", err=True)
        raise typer.Exit(1)

    def _progress(path: str, success: bool, current: int, total: int) -> None:
        bar_width = 20
        filled = round(current / total * bar_width) if total else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = round(current / total * 100) if total else 0
        pad = len(str(total))
        symbol = "✓" if success else "✗"
        typer.echo(f"  [{current:>{pad}}/{total}] [{bar}] {pct:>3}%  {symbol} {path}")

    started = time.perf_counter()
    enrich_result = run_enrich(project_root, repo, client, batch_limit=limit, on_progress=_progress)
    elapsed = time.perf_counter() - started
    if isinstance(enrich_result, Left):
        typer.echo(f"Error: {enrich_result.error}", err=True)
        raise typer.Exit(1)
    report = enrich_result.value
    typer.echo(
        f"Enrich: enriched={report.enriched} failed={report.failed} skipped={report.skipped}"
        f" elapsed={elapsed:.1f}s"
    )
    for error in report.errors:
        typer.echo(f"  ! {error}", err=True)


@app.command(help="Search enriched files by tag, layer, or language.")
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


def _bar(value: int, maximum: int, width: int = 18) -> str:
    filled = round(value / maximum * width) if maximum else 0
    return "█" * filled + "░" * (width - filled)


@app.command(help="Show total, enriched, and pending counts broken down by layer and language.")
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

    sep = "━" * 52
    pct = round(enriched / total * 100) if total else 0
    prog_filled = round(pct / 100 * 20)
    progress = "█" * prog_filled + "░" * (20 - prog_filled)

    typer.echo(sep)
    typer.echo(f"  Total: {total:<6}  Enriched: {enriched:<6}  Pending: {pending}")
    typer.echo(f"  [{progress}] {pct}%")
    typer.echo("")

    col = max((len(k) for k in by_layer), default=0)
    top = max(by_layer.values(), default=1)
    typer.echo("  By layer")
    for name, cnt in sorted(by_layer.items(), key=lambda x: -x[1]):
        typer.echo(f"  {name:<{col}}  {cnt:>5}  {_bar(cnt, top)}")
    typer.echo("")

    col = max((len(k) for k in by_lang), default=0)
    top = max(by_lang.values(), default=1)
    typer.echo("  By language")
    for lang, cnt in sorted(by_lang.items(), key=lambda x: -x[1]):
        typer.echo(f"  {lang:<{col}}  {cnt:>5}  {_bar(cnt, top)}")
    typer.echo(sep)


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


@app.command(help="Delete the index (offers a timestamped backup before wiping).")
def reset(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    maps_dir = project_root / ".docs" / "maps"
    db_file = db_path(project_root)
    index_yaml = index_yaml_path(project_root)
    if not maps_dir.exists():
        typer.echo("Error: index not found. Nothing to reset.", err=True)
        raise typer.Exit(1)
    typer.echo(
        "WARNING: this operation is irreversible. "
        "The index will be deleted and must be rebuilt with init + walk + sync + enrich."
    )
    if not typer.confirm("Confirm reset?"):
        typer.echo("Cancelled.")
        return
    if db_file.exists() and typer.confirm("Backup current database?", default=True):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = maps_dir / f"index.{timestamp}.bak"
        shutil.copy2(db_file, backup)
        typer.echo(f"Backup saved: {backup.name}")
    if db_file.exists():
        db_file.unlink()
    if index_yaml.exists():
        index_yaml.unlink()
    typer.echo("Reset complete. Run: sourcemap init && sourcemap walk")


@app.command(help="Restore index.db from a previously saved .bak file.")
def restore(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    maps_dir = project_root / ".docs" / "maps"
    if not maps_dir.exists():
        typer.echo("Error: no maps directory found.", err=True)
        raise typer.Exit(1)
    backups = sorted(maps_dir.glob("index.*.bak"), reverse=True)
    if not backups:
        typer.echo("No backups found.")
        return
    typer.echo("Available backups:")
    for i, bak in enumerate(backups, 1):
        typer.echo(f"  [{i}] {bak.name}")
    choice = typer.prompt("Select backup to restore", type=int)
    if choice < 1 or choice > len(backups):
        typer.echo("Error: invalid selection.", err=True)
        raise typer.Exit(1)
    selected = backups[choice - 1]
    shutil.copy2(selected, db_path(project_root))
    typer.echo(f"Restored from {selected.name}")


_INSTALL_SKILL_HELP = "Install the skill file into an AI assistant's skills directory."


@app.command(name="install-skill", help=_INSTALL_SKILL_HELP)
def install_skill(
    target: str = typer.Option(..., "--target", help="Skills directory (e.g. ~/.claude/skills)"),
) -> None:
    skill_src = files("sourcemap_indexer.skill").joinpath("SKILL.md")
    dest_dir = Path(target).expanduser() / "sourcemap"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "SKILL.md"
    dest.write_text(skill_src.read_text(encoding="utf-8"), encoding="utf-8")
    typer.echo(f"Skill installed at {dest}")


_SQL_OVERVIEW = (
    "SELECT layer, language, COUNT(*) AS total FROM items "
    "WHERE deleted_at IS NULL GROUP BY layer, language ORDER BY layer, total DESC"
)
_SQL_DOMAIN = (
    "SELECT path, purpose FROM items WHERE layer = 'domain' AND needs_llm = 0 ORDER BY path"
)
_SQL_EFFECTS = (
    "SELECT i.path, s.effect FROM items i "
    "JOIN side_effects s ON s.item_id = i.id "
    "WHERE s.effect IN ('network', 'git') ORDER BY i.path"
)
_SQL_TAGS = (
    "SELECT t.tag, COUNT(*) AS total FROM tags t "
    "JOIN items i ON i.id = t.item_id "
    "WHERE i.deleted_at IS NULL GROUP BY t.tag ORDER BY total DESC LIMIT 30"
)
_SQL_UNSTABLE = (
    "SELECT path, layer, stability, purpose FROM items "
    "WHERE stability IN ('experimental', 'deprecated') "
    "AND deleted_at IS NULL ORDER BY stability, path"
)


def _run_query(db_file: Path, sql: str) -> None:
    if not db_file.exists():
        typer.echo("Error: index not found. Run 'sourcemap init' first.", err=True)
        raise typer.Exit(1)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql)  # noqa: S608
        rows = cursor.fetchall()
        if not rows:
            typer.echo("(no results)")
            return
        headers = list(rows[0].keys())
        widths = [max(len(h), max(len(str(r[h])) for r in rows)) for h in headers]
        typer.echo("  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)))
        typer.echo("  ".join("-" * w for w in widths))
        for row in rows:
            cells = (str(row[h]).ljust(w) for h, w in zip(headers, widths, strict=True))
            typer.echo("  ".join(cells))
    except sqlite3.Error as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from None
    finally:
        conn.close()


@app.command(help="Run a free-form SQL query against the index database.")
def query(
    sql: str = typer.Argument(help="SQL query to run against the index"),
    root: str | None = typer.Option(None, help="Project root"),
) -> None:
    _run_query(db_path(_resolve_root(root)), sql)


@app.command(help="Layer × language matrix — project structure at a glance.")
def overview(root: str | None = typer.Option(None, help="Project root")) -> None:
    _run_query(db_path(_resolve_root(root)), _SQL_OVERVIEW)


@app.command(help="List enriched domain-layer files with their purpose.")
def domain(root: str | None = typer.Option(None, help="Project root")) -> None:
    _run_query(db_path(_resolve_root(root)), _SQL_DOMAIN)


@app.command(help="List files with network or git side effects (I/O boundaries).")
def effects(root: str | None = typer.Option(None, help="Project root")) -> None:
    _run_query(db_path(_resolve_root(root)), _SQL_EFFECTS)


@app.command(help="Top 30 semantic tags by frequency across the codebase.")
def tags(root: str | None = typer.Option(None, help="Project root")) -> None:
    _run_query(db_path(_resolve_root(root)), _SQL_TAGS)


@app.command(help="List experimental or deprecated files — risk areas.")
def unstable(root: str | None = typer.Option(None, help="Project root")) -> None:
    _run_query(db_path(_resolve_root(root)), _SQL_UNSTABLE)
