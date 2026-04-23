from __future__ import annotations

import sqlite3

import typer

from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import db_path

_SEP = "─" * 56

_SQL_CHAPTERS = (
    "SELECT path, layer, purpose FROM items "
    "WHERE deleted_at IS NULL AND needs_llm = 0 "
    "ORDER BY layer, path"
)

_SQL_CHAPTERS_FILTERED = (
    "SELECT path, layer, purpose FROM items "
    "WHERE deleted_at IS NULL AND needs_llm = 0 AND layer = ? "
    "ORDER BY layer, path"
)


def _fetch_chapters(conn: sqlite3.Connection, layer: str | None) -> list[sqlite3.Row]:
    if layer is None:
        return conn.execute(_SQL_CHAPTERS).fetchall()  # noqa: S608
    return conn.execute(_SQL_CHAPTERS_FILTERED, (layer,)).fetchall()  # noqa: S608


def _group_by_layer(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["layer"], []).append(row)
    return grouped


def _render_grouped(grouped: dict[str, list[sqlite3.Row]]) -> None:
    for layer in sorted(grouped):
        typer.echo(f"\n## {layer}")
        typer.echo(_SEP)
        for row in grouped[layer]:
            typer.echo(f"  {row['path']}")
            purpose = row["purpose"] or "(no purpose)"
            typer.echo(f"    {purpose}")


_CHAPTERS_HELP = (
    "Table of contents: enriched files grouped by layer, sorted by path. "
    "Ideal for documentation-heavy projects. Use --layer to filter."
)


@app.command(help=_CHAPTERS_HELP)
def chapters(
    root: str | None = typer.Option(None, help="Project root"),
    layer: str | None = typer.Option(None, "--layer", help="Filter by layer"),
) -> None:
    project_root = _resolve_root(root)
    db_file = db_path(project_root)
    if not db_file.exists():
        typer.echo("Error: index not found. Run 'sourcemap init' first.", err=True)
        raise typer.Exit(1)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        rows = _fetch_chapters(conn, layer)
        if not rows:
            typer.echo("No chapters found.")
            return
        typer.echo("# Chapters")
        typer.echo(_SEP)
        _render_grouped(_group_by_layer(rows))
    finally:
        conn.close()
