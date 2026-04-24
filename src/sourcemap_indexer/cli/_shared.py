from __future__ import annotations

from pathlib import Path

import typer

from sourcemap_indexer.config import db_path, find_project_root
from sourcemap_indexer.infra.db.migrator import init_db
from sourcemap_indexer.infra.db.sqlite_repo import SqliteItemRepository
from sourcemap_indexer.lib.either import Left

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
