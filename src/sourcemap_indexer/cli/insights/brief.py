from __future__ import annotations

import sqlite3

import typer

from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import db_path

_BEHAVIOR_LAYERS = frozenset({"domain", "application", "infra", "lib"})

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
    "WHERE layer = 'domain' AND needs_llm = 0 AND deleted_at IS NULL "
    "AND size_bytes > 100 ORDER BY path LIMIT 10"
)
_SQL_WORKFLOWS = (
    "SELECT path, purpose FROM items "
    "WHERE layer = 'application' AND needs_llm = 0 AND deleted_at IS NULL "
    "AND size_bytes > 100 ORDER BY path LIMIT 10"
)
_SQL_EFFECTS = (
    "SELECT s.effect, COUNT(DISTINCT i.id) AS files, MIN(i.path) AS sample_path "
    "FROM items i JOIN side_effects s ON s.item_id = i.id "
    "WHERE i.deleted_at IS NULL GROUP BY s.effect ORDER BY files DESC"
)
_SQL_CONTRACTS = (
    "SELECT i.layer, i.name, inv.invariant, inv.position "
    "FROM invariants inv JOIN items i ON i.id = inv.item_id "
    "WHERE i.deleted_at IS NULL AND i.layer IN ('domain','application','infra','lib') "
    "ORDER BY i.layer, i.name, inv.position"
)
_SQL_UNSTABLE = (
    "SELECT path, stability, purpose FROM items "
    "WHERE stability IN ('experimental', 'deprecated') AND deleted_at IS NULL "
    "ORDER BY stability, path"
)
_SQL_ENRICHMENT_GAP = (
    "SELECT path, purpose FROM items "
    "WHERE stability = 'unknown' AND needs_llm = 0 AND deleted_at IS NULL "
    "ORDER BY path"
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
    typer.echo(f"  {total} files · {enriched} enriched · {pending} pending")


def _fmt_arch_row(row: sqlite3.Row) -> str:
    total = row["total"]
    label = "file" if total == 1 else "files"
    return f"  {row['layer']:<16}  {row['language']:<6}  {total:>3} {label}"


def _collect_support(rows: list[sqlite3.Row]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        if row["layer"] not in _BEHAVIOR_LAYERS:
            counts[row["layer"]] = counts.get(row["layer"], 0) + row["total"]
    return " · ".join(f"{layer} {n}" for layer, n in sorted(counts.items()))


def _print_structure(conn: sqlite3.Connection) -> None:
    rows = conn.execute(_SQL_ARCHITECTURE).fetchall()  # noqa: S608
    if not rows:
        typer.echo("  no data")
        return
    for row in rows:
        if row["layer"] in _BEHAVIOR_LAYERS:
            typer.echo(_fmt_arch_row(row))
    support = _collect_support(rows)
    if support:
        typer.echo(f"  ─ support: {support}")


def _print_layer_files(conn: sqlite3.Connection, sql: str) -> None:
    rows = conn.execute(sql).fetchall()  # noqa: S608
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
        files = row["files"]
        label = "file" if files == 1 else "files"
        suffix = f"  → {row['sample_path']}" if files == 1 else ""
        typer.echo(f"  {row['effect']:<20}  {files:>3} {label}{suffix}")


def _group_contracts(rows: list[sqlite3.Row]) -> dict[tuple[str, str], list[str]]:
    result: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        key = (row["layer"], row["name"])
        if key not in result:
            result[key] = []
        if len(result[key]) < 3:
            result[key].append(row["invariant"])
    return result


def _print_contracts(conn: sqlite3.Connection) -> None:
    rows = conn.execute(_SQL_CONTRACTS).fetchall()  # noqa: S608
    if not rows:
        typer.echo("  no enriched data")
        return
    for (layer, name), invs in _group_contracts(rows).items():
        typer.echo(f"  {layer}/{name}")
        for inv in invs:
            typer.echo(f"    · {inv}")


def _print_risk_row(prefix: str, path: str, purpose: str | None) -> None:
    typer.echo(f"  [{prefix}]  {path}")
    if purpose:
        typer.echo(f"    {purpose}")


def _print_risk(conn: sqlite3.Connection) -> None:
    unstable = conn.execute(_SQL_UNSTABLE).fetchall()  # noqa: S608
    gaps = conn.execute(_SQL_ENRICHMENT_GAP).fetchall()  # noqa: S608
    if not unstable and not gaps:
        typer.echo("  none")
        return
    for row in unstable:
        _print_risk_row(row["stability"], row["path"], row["purpose"])
    for row in gaps:
        _print_risk_row("enrichment-gap", row["path"], row["purpose"])


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
        _section("Structure")
        _print_structure(conn)
        _section("Domain")
        _print_layer_files(conn, _SQL_DOMAIN)
        _section("Workflows")
        _print_layer_files(conn, _SQL_WORKFLOWS)
        _section("I/O Boundaries")
        _print_effects(conn)
        _section("System Contracts")
        _print_contracts(conn)
        _section("Risk Areas")
        _print_risk(conn)
    finally:
        conn.close()
