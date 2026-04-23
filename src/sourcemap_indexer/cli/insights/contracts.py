from __future__ import annotations

import sqlite3

import typer

from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import db_path

_SEP = "─" * 56

_SQL_CONTRACTS = (
    "SELECT i.layer, i.path, inv.invariant, inv.position "
    "FROM invariants inv JOIN items i ON i.id = inv.item_id "
    "WHERE i.deleted_at IS NULL "
    "ORDER BY i.layer, i.path, inv.position"
)

_SQL_CONTRACTS_FILTERED = (
    "SELECT i.layer, i.path, inv.invariant, inv.position "
    "FROM invariants inv JOIN items i ON i.id = inv.item_id "
    "WHERE i.deleted_at IS NULL AND i.layer = ? "
    "ORDER BY i.layer, i.path, inv.position"
)


def _fetch_contracts(conn: sqlite3.Connection, layer: str | None) -> list[sqlite3.Row]:
    if layer is None:
        return conn.execute(_SQL_CONTRACTS).fetchall()  # noqa: S608
    return conn.execute(_SQL_CONTRACTS_FILTERED, (layer,)).fetchall()  # noqa: S608


def _group_by_layer_and_path(
    rows: list[sqlite3.Row],
) -> dict[str, dict[str, list[str]]]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        grouped.setdefault(row["layer"], {}).setdefault(row["path"], []).append(row["invariant"])
    return grouped


def _render_grouped(grouped: dict[str, dict[str, list[str]]]) -> None:
    for layer in sorted(grouped):
        typer.echo(f"\n## {layer}")
        typer.echo(_SEP)
        files = grouped[layer]
        for path in sorted(files):
            typer.echo(f"  {path}")
            for invariant in files[path]:
                typer.echo(f"    · {invariant}")


_CONTRACTS_HELP = (
    "List invariants grouped by layer and file — semantic contracts captured during enrichment. "
    "Use --layer to filter a single layer."
)


@app.command(help=_CONTRACTS_HELP)
def contracts(
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
        rows = _fetch_contracts(conn, layer)
        if not rows:
            typer.echo("No contracts found.")
            return
        typer.echo("# Contracts")
        typer.echo(_SEP)
        _render_grouped(_group_by_layer_and_path(rows))
    finally:
        conn.close()
