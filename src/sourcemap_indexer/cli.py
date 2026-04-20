from __future__ import annotations

import math
import os
import shutil
import sqlite3
import time
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import typer
from rich.console import Console as _Console
from rich.panel import Panel as _Panel
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TextColumn,
)
from rich.text import Text as _Text

from sourcemap_indexer.application.enrich import run_enrich
from sourcemap_indexer.application.sync import run_sync
from sourcemap_indexer.application.walk import run_walk
from sourcemap_indexer.config import (
    db_path,
    default_prompt_export_path,
    find_project_root,
    import_prompt_path,
    index_yaml_path,
    logs_dir,
    maps_dir,
)
from sourcemap_indexer.domain.value_objects import Language, Layer
from sourcemap_indexer.infra.dotenv import load_dotenv
from sourcemap_indexer.infra.llama_client import (
    SYSTEM_PROMPT,
    LlamaClient,
    from_environ,
    is_llm_configured,
)
from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.infra.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Left
from sourcemap_indexer.lib.llm_log import create_llm_log


class _DotBarColumn(ProgressColumn):
    def render(self, task: Task) -> _Text:
        width = 20
        if task.total is None or task.total == 0:
            pulse = int(time.time() * 4) % width
            dots = "○" * pulse + "●" + "○" * (width - pulse - 1)
            return _Text(dots, style="yellow")
        filled = round(task.completed / task.total * width)
        return _Text("●" * filled + "○" * (width - filled), style="green")


_APP_HELP = (
    "Codebase indexer powered by LLM\n\n"
    "Manage the tool:\n\n"
    "  uv tool upgrade sourcemap-indexer\n\n"
    "  uv tool uninstall sourcemap-indexer"
)
app = typer.Typer(help=_APP_HELP)

_DEFAULT_SOURCEMAPIGNORE = ".venv/\n.git/\n__pycache__/\n*.pyc\ndist/\nbuild/\n*.db\n*.sqlite\n"
_LAYER_VALUES = "domain|infra|application|cli|hook|lib|config|doc|test|unknown"
_LANG_VALUES = "py|sh|ts|tsx|js|sql|md|yaml|json|toml|other"
_LAYER_HELP = f"Filter by layer: {_LAYER_VALUES}"
_LANG_HELP = f"Filter by language: {_LANG_VALUES}"
_FILE_HELP = "Single file path to enrich (sets --force)"
_FIND_HELP = f"Search files by --tag TEXT, --layer ({_LAYER_VALUES}), --language ({_LANG_VALUES})."


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


@app.command(help="Create the maps output directory and initialize the SQLite index.")
def init(root: str | None = typer.Option(None, help="Project root")) -> None:
    project_root = _resolve_root(root)
    output_dir = maps_dir(project_root)
    output_dir.mkdir(parents=True, exist_ok=True)
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


_ENRICH_HELP = (
    "Enrich pending files via LLM. --limit N, --force (re-enrich),"
    f" --layer ({_LAYER_VALUES}), --language ({_LANG_VALUES}),"
    " --file PATH (single file), -m INSTRUCTION.\n\n"
    "  Examples:\n"
    "    sourcemap enrich --limit 10\n"
    "    sourcemap enrich --force --file src/app.py\n"
    "    sourcemap enrich --force --layer unknown -m 'write in English'"
)


@app.command(help=_ENRICH_HELP)
def enrich(
    root: str | None = typer.Option(None, help="Project root"),
    limit: int | None = typer.Option(None, "--limit", help="Max items to enrich"),
    force: bool = typer.Option(False, "--force", help="Re-enrich already enriched files"),
    layer: str | None = typer.Option(None, "--layer", help=_LAYER_HELP),
    language: str | None = typer.Option(None, "--language", help=_LANG_HELP),
    message: str | None = typer.Option(None, "-m", help="Extra instruction injected into prompt"),
    file: str | None = typer.Option(None, "--file", help=_FILE_HELP),
    export_llm_prompt: bool = typer.Option(
        False, "--export-llm-prompt", help="Write the active LLM prompt to a .md file"
    ),
    output: str | None = typer.Option(
        None, "--output", help="Destination for --export-llm-prompt (default: maps dir)"
    ),
) -> None:
    project_root = _resolve_root(root)
    load_dotenv(project_root / ".env")

    import_result = import_prompt_path()
    if isinstance(import_result, Left):
        typer.echo(f"Error: {import_result.error}", err=True)
        raise typer.Exit(1)

    import_path = import_result.value
    custom_prompt = (
        import_path.read_text(encoding="utf-8") if import_path and import_path.exists() else None
    )

    if export_llm_prompt:
        export_path = Path(output) if output else default_prompt_export_path(project_root)
        if export_path.suffix != ".md":
            typer.echo("Error: --output must have a .md extension", err=True)
            raise typer.Exit(1)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(custom_prompt or SYSTEM_PROMPT, encoding="utf-8")
        typer.echo(f"Prompt exported to {export_path}")
        raise typer.Exit(0)

    if not is_llm_configured():
        _Console(stderr=True).print(
            _Panel(
                "LLM not configured.\n"
                "Set [bold]SOURCEMAP_LLM_URL[/bold] in your environment or [bold].env[/bold] file.",
                title="Error",
                border_style="red",
                title_align="left",
            )
        )
        raise typer.Exit(1)
    repo = _open_repo(project_root)
    config = from_environ()
    llm_log = create_llm_log(logs_dir(project_root))
    client = LlamaClient(config, llm_log=llm_log, system_prompt=custom_prompt)
    typer.echo(f"Model: {config.model}  ({config.url})")
    if import_path is not None:
        typer.echo(f"Prompt: {import_path}")
    if message:
        typer.echo(f"Instruction: {message}")
    ping_result = client.ping()
    if isinstance(ping_result, Left):
        typer.echo(f"Error: LLM unreachable — {ping_result.error}", err=True)
        typer.echo(f"  Check that your LLM server is running at: {config.url}", err=True)
        raise typer.Exit(1)

    layer_val = Layer(layer) if layer else None
    language_val = Language(language) if language else None
    if file:
        force = True

    def _progress(path: str, success: bool, current: int, total: int) -> None:
        bar_width = 20
        filled = round(current / total * bar_width) if total else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = round(current / total * 100) if total else 0
        pad = len(str(total))
        symbol = "✓" if success else "✗"
        typer.echo(f"  [{current:>{pad}}/{total}] [{bar}] {pct:>3}%  {symbol} {path}")

    started = time.perf_counter()
    enrich_result = run_enrich(
        project_root,
        repo,
        client,
        batch_limit=limit,
        on_progress=_progress,
        force=force,
        layer_filter=layer_val,
        language_filter=language_val,
        extra_instruction=message,
        path_filter=file,
    )
    elapsed = time.perf_counter() - started
    if isinstance(enrich_result, Left):
        typer.echo(f"Error: {enrich_result.error}", err=True)
        raise typer.Exit(1)
    report = enrich_result.value
    typer.echo(
        f"\nEnrich: enriched={report.enriched} failed={report.failed} skipped={report.skipped}"
        f" elapsed={elapsed:.1f}s"
    )
    for error in report.errors:
        typer.echo(f"  ! {error}", err=True)
    typer.echo("")
    stats(root=root, files=False, page=1)


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


def _bar(value: int, maximum: int, width: int = 18) -> str:
    filled = round(value / maximum * width) if maximum else 0
    return "●" * filled + "○" * (width - filled)


def _lang_color(pending_count: int) -> str:
    return "yellow" if pending_count > 0 else "green"


def _proportional_width(count: int, max_count: int, max_width: int = 20) -> int:
    if max_count == 0:
        return 0
    return max(1, round(count / max_count * max_width))


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
        typer.echo(
            f"Sync: inserted={report.inserted} updated={report.updated} "
            f"soft_deleted={report.soft_deleted}"
        )
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
    pending_by_lang: dict[str, int] = {}
    for item in items:
        by_layer[str(item.layer)] = by_layer.get(str(item.layer), 0) + 1
        by_lang[str(item.language)] = by_lang.get(str(item.language), 0) + 1
        if item.needs_llm:
            pending_by_lang[str(item.language)] = pending_by_lang.get(str(item.language), 0) + 1

    pct = round(enriched / total * 100) if total else 0
    dot_filled = round(pct / 100 * 20)
    dot_bar = (
        "[green]" + "●" * dot_filled + "[/green]" + "[dim]" + "○" * (20 - dot_filled) + "[/dim]"
    )

    if is_llm_configured():
        llm = from_environ()
        llm_line = f"[bold]Model[/bold]  {llm.model}  [dim]({llm.url})[/dim]"
    else:
        llm_line = "[dim]LLM: not configured[/dim]"

    summary = (
        f"{llm_line}\n"
        f"[bold]Total[/bold]: {total:<6}  [bold]Enriched[/bold]: {enriched:<6}"
        f"  [bold]Pending[/bold]: {pending}\n"
        f"{dot_bar}  {pct}%"
    )
    console.print(_Panel(summary, title="Stats", border_style="blue", title_align="left"))

    col = max((len(k) for k in by_layer), default=0)
    top = max(by_layer.values(), default=1)
    layer_rows = "\n".join(
        f"  {name:<{col}}  {cnt:>5}  [green]{_bar(cnt, top)}[/green]"
        for name, cnt in sorted(by_layer.items(), key=lambda x: -x[1])
    )
    console.print(
        _Panel(
            layer_rows or "[dim](no data)[/dim]",
            title="By layer",
            border_style="blue",
            title_align="left",
        )
    )

    col = max((len(k) for k in by_lang), default=0)
    top_lang = max(by_lang.values(), default=1)
    lang_row_list: list[str] = []
    for lang, cnt in sorted(by_lang.items(), key=lambda x: -x[1]):
        clr = _lang_color(pending_by_lang.get(lang, 0))
        wid = _proportional_width(cnt, top_lang)
        lang_row_list.append(
            f"  {lang:<{col}}  {cnt:>5}  [{clr}]{_bar(cnt, top_lang, wid)}[/{clr}]"
        )
    lang_rows = "\n".join(lang_row_list)
    console.print(
        _Panel(
            lang_rows or "[dim](no data)[/dim]",
            title="By language",
            border_style="blue",
            title_align="left",
        )
    )

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
        console.print(
            _Panel(
                pending_rows + footer,
                title="Pending",
                border_style="yellow",
                title_align="left",
            )
        )


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
    output_dir = maps_dir(project_root)
    db_file = db_path(project_root)
    index_yaml = index_yaml_path(project_root)
    if not output_dir.exists():
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
        backup = output_dir / f"index.{timestamp}.bak"
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
    output_dir = maps_dir(project_root)
    if not output_dir.exists():
        typer.echo("Error: no maps directory found.", err=True)
        raise typer.Exit(1)
    backups = sorted(output_dir.glob("index.*.bak"), reverse=True)
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


_SQL_PROFILE_STACK = (
    "SELECT language, COUNT(*) AS files, SUM(lines) AS lines "
    "FROM items WHERE deleted_at IS NULL GROUP BY language ORDER BY files DESC"
)
_SQL_PROFILE_LAYERS = """
SELECT
  CASE
    WHEN path LIKE 'tests/%' OR path LIKE '%/tests/%' THEN 'test'
    WHEN path LIKE '%/domain/%' THEN 'domain'
    WHEN path LIKE '%/infra/%' THEN 'infra'
    WHEN path LIKE '%/application/%' THEN 'application'
    WHEN path LIKE '%/lib/%' THEN 'lib'
    WHEN path LIKE 'scripts/%' OR path LIKE '%.sh' THEN 'script'
    WHEN path LIKE '%.md' THEN 'doc'
    WHEN path LIKE '%.toml' OR path LIKE '%.sql' OR path LIKE '%ignore'
      OR path LIKE '%.json' OR path LIKE '%.yaml' OR path LIKE '%.yml' THEN 'config'
    ELSE 'unknown'
  END AS inferred_layer,
  COUNT(*) AS files,
  SUM(lines) AS lines
FROM items WHERE deleted_at IS NULL
GROUP BY inferred_layer ORDER BY files DESC
"""
_SQL_PROFILE_RATIO = """
SELECT
  SUM(CASE WHEN path LIKE 'tests/%' OR path LIKE '%/tests/%' THEN 1 ELSE 0 END) AS test_files,
  SUM(CASE WHEN path LIKE 'tests/%' OR path LIKE '%/tests/%' THEN lines ELSE 0 END) AS test_lines,
  SUM(CASE WHEN path NOT LIKE 'tests/%' AND path NOT LIKE '%/tests/%'
    AND path NOT LIKE '%.md' AND path NOT LIKE '%.toml'
    AND path NOT LIKE '%ignore' AND path NOT LIKE '%.sql' THEN 1 ELSE 0 END) AS src_files,
  SUM(CASE WHEN path NOT LIKE 'tests/%' AND path NOT LIKE '%/tests/%'
    AND path NOT LIKE '%.md' AND path NOT LIKE '%.toml'
    AND path NOT LIKE '%ignore' AND path NOT LIKE '%.sql' THEN lines ELSE 0 END) AS src_lines
FROM items WHERE deleted_at IS NULL
"""
_SQL_PROFILE_TOP = (
    "SELECT path, language, lines FROM items WHERE deleted_at IS NULL ORDER BY lines DESC LIMIT 10"
)


@app.command(help="Structural profile from walk data only — no LLM required.")
def profile(root: str | None = typer.Option(None, help="Project root")) -> None:
    db_file = db_path(_resolve_root(root))
    if not db_file.exists():
        typer.echo("Error: index not found. Run 'sourcemap init' first.", err=True)
        raise typer.Exit(1)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row

    sep = "━" * 52
    typer.echo(sep)
    typer.echo("  Profile  (walk data — no LLM required)")
    typer.echo(sep)

    typer.echo("")
    typer.echo("  Stack")
    rows = conn.execute(_SQL_PROFILE_STACK).fetchall()  # noqa: S608
    top = max((r["files"] for r in rows), default=1)
    for row in rows:
        typer.echo(
            f"  {row['language']:<8}  {row['files']:>4} files  "
            f"{row['lines']:>6} lines  {_bar(row['files'], top)}"
        )

    typer.echo("")
    typer.echo("  Inferred layers  (from directory names)")
    rows = conn.execute(_SQL_PROFILE_LAYERS).fetchall()  # noqa: S608
    top = max((r["files"] for r in rows), default=1)
    for row in rows:
        typer.echo(
            f"  {row['inferred_layer']:<14}  {row['files']:>4} files  "
            f"{row['lines']:>6} lines  {_bar(row['files'], top)}"
        )

    typer.echo("")
    typer.echo("  Test ratio")
    row = conn.execute(_SQL_PROFILE_RATIO).fetchone()  # noqa: S608
    if row and row["src_files"]:
        ratio = round(row["test_lines"] / row["src_lines"], 2) if row["src_lines"] else 0
        health = "healthy" if ratio >= 0.8 else "low"
        typer.echo(f"  Source  {row['src_files']:>4} files  {row['src_lines']:>6} lines")
        typer.echo(
            f"  Tests   {row['test_files']:>4} files  {row['test_lines']:>6} lines"
            f"  (ratio: {ratio}× — {health})"
        )
    else:
        typer.echo("  No test files detected.")

    typer.echo("")
    typer.echo("  Top files by complexity")
    rows = conn.execute(_SQL_PROFILE_TOP).fetchall()  # noqa: S608
    top_lines = max((r["lines"] for r in rows), default=1)
    for row in rows:
        typer.echo(f"  {row['path']:<50}  {row['lines']:>5} lines  {_bar(row['lines'], top_lines)}")

    conn.close()
    typer.echo("")
