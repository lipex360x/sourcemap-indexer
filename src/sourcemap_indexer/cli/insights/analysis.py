from __future__ import annotations

import sqlite3
from pathlib import Path

import typer

from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import db_path

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
