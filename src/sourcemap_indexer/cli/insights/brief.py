from __future__ import annotations

import sqlite3

import typer

from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import db_path

_SQL_TOTALS = (
    "SELECT COUNT(*) AS total, "
    "SUM(CASE WHEN needs_llm = 0 THEN 1 ELSE 0 END) AS enriched "
    "FROM items WHERE deleted_at IS NULL"
)
_SQL_ARCHITECTURE = (
    "SELECT layer, language, COUNT(*) AS total FROM items "
    "WHERE deleted_at IS NULL GROUP BY layer, language ORDER BY layer, total DESC"
)
_SQL_DOMAIN = (
    "SELECT path, purpose FROM items "
    "WHERE layer = 'domain' AND needs_llm = 0 AND deleted_at IS NULL ORDER BY path LIMIT 10"
)
_SQL_EFFECTS = (
    "SELECT DISTINCT s.effect, COUNT(DISTINCT i.id) AS files FROM items i "
    "JOIN side_effects s ON s.item_id = i.id "
    "WHERE i.deleted_at IS NULL GROUP BY s.effect ORDER BY files DESC"
)
_SQL_TAGS = (
    "SELECT t.tag, COUNT(*) AS total FROM tags t "
    "JOIN items i ON i.id = t.item_id "
    "WHERE i.deleted_at IS NULL GROUP BY t.tag ORDER BY total DESC LIMIT 15"
)
_SQL_UNSTABLE = (
    "SELECT path, stability FROM items "
    "WHERE stability IN ('experimental', 'deprecated') AND deleted_at IS NULL "
    "ORDER BY stability, path"
)

_SEP = "─" * 56


def _section(title: str) -> None:
    typer.echo(f"\n## {title}")
    typer.echo(_SEP)


def _print_totals(conn: sqlite3.Connection) -> None:
    row = conn.execute(_SQL_TOTALS).fetchone()  # noqa: S608
    total = row["total"] if row else 0
    enriched = row["enriched"] if row else 0
    pending = total - enriched
    typer.echo(f"  Files: {total}   Enriched: {enriched}   Pending: {pending}")


def _print_architecture(conn: sqlite3.Connection) -> None:
    rows = conn.execute(_SQL_ARCHITECTURE).fetchall()  # noqa: S608
    if not rows:
        typer.echo("  no enriched data")
        return
    for row in rows:
        typer.echo(f"  {row['layer']:<16}  {row['language']:<6}  {row['total']:>4} files")


def _print_domain(conn: sqlite3.Connection) -> None:
    rows = conn.execute(_SQL_DOMAIN).fetchall()  # noqa: S608
    if not rows:
        typer.echo("  no enriched data")
        return
    for row in rows:
        typer.echo(f"  {row['path']}")
        if row["purpose"]:
            typer.echo(f"    {row['purpose']}")


def _print_effects(conn: sqlite3.Connection) -> None:
    rows = conn.execute(_SQL_EFFECTS).fetchall()  # noqa: S608
    if not rows:
        typer.echo("  no enriched data")
        return
    for row in rows:
        typer.echo(f"  {row['effect']:<20}  {row['files']:>4} files")


def _print_vocabulary(conn: sqlite3.Connection) -> None:
    rows = conn.execute(_SQL_TAGS).fetchall()  # noqa: S608
    if not rows:
        typer.echo("  no enriched data")
        return
    tags = ", ".join(f"{r['tag']} ({r['total']})" for r in rows)
    typer.echo(f"  {tags}")


def _print_risk(conn: sqlite3.Connection) -> None:
    rows = conn.execute(_SQL_UNSTABLE).fetchall()  # noqa: S608
    if not rows:
        typer.echo("  none")
        return
    for row in rows:
        typer.echo(f"  [{row['stability']}]  {row['path']}")


@app.command(help="Single-call project briefing for AI-assisted discovery.")
def brief(root: str | None = typer.Option(None, help="Project root")) -> None:
    db_file = db_path(_resolve_root(root))
    if not db_file.exists():
        typer.echo("Error: index not found. Run 'sourcemap init' first.", err=True)
        raise typer.Exit(1)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        typer.echo("# Project Brief")
        typer.echo(_SEP)
        _print_totals(conn)
        _section("Architecture")
        _print_architecture(conn)
        _section("Domain")
        _print_domain(conn)
        _section("I/O Boundaries")
        _print_effects(conn)
        _section("Vocabulary")
        _print_vocabulary(conn)
        _section("Risk Areas")
        _print_risk(conn)
    finally:
        conn.close()
