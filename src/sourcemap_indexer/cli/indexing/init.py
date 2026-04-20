from __future__ import annotations

import typer

from sourcemap_indexer.cli._shared import _DEFAULT_SOURCEMAPIGNORE, _resolve_root, app
from sourcemap_indexer.config import db_path, maps_dir
from sourcemap_indexer.infra.migrator import init_db
from sourcemap_indexer.lib.either import Left

_LAYERS_YAML_TEMPLATE = (
    "# Add custom layer names below (one per line).\n"
    "# Defaults already included: domain, infra, application, cli, hook,\n"
    "#   lib, config, doc, test, unknown\n"
    "#\n"
    "# Example:\n"
    "# layers:\n"
    "#   - controller\n"
    "#   - service\n"
    "#   - usecase\n"
    "layers: []\n"
)


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
    layers_file = output_dir / "layers.yaml"
    if not layers_file.exists():
        layers_file.write_text(_LAYERS_YAML_TEMPLATE, encoding="utf-8")
    typer.echo(f"Initialized sourcemap at {project_root}")
