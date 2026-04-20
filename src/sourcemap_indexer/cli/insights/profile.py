from __future__ import annotations

import sqlite3

import typer

from sourcemap_indexer.cli._rendering import _bar
from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import db_path

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
