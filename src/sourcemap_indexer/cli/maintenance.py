from __future__ import annotations

import shutil
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import typer

from sourcemap_indexer.cli._shared import _resolve_root, app
from sourcemap_indexer.config import db_path, index_yaml_path, maps_dir

_INSTALL_SKILL_HELP = "Install the skill file into an AI assistant's skills directory."


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
    for idx, bak in enumerate(backups, 1):
        typer.echo(f"  [{idx}] {bak.name}")
    choice = typer.prompt("Select backup to restore", type=int)
    if choice < 1 or choice > len(backups):
        typer.echo("Error: invalid selection.", err=True)
        raise typer.Exit(1)
    selected = backups[choice - 1]
    shutil.copy2(selected, db_path(project_root))
    typer.echo(f"Restored from {selected.name}")


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
