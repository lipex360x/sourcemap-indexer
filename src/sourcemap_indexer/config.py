from __future__ import annotations

import os
from pathlib import Path

from sourcemap_indexer.lib.either import Either, left, right

_DEFAULT_MAPS_DIR = ".docs/maps"


def find_project_root(start: Path) -> Either[str, Path]:
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return right(current)
        parent = current.parent
        if parent == current:
            return left("git-root-not-found")
        current = parent


def maps_dir(root: Path) -> Path:
    custom = os.environ.get("SOURCEMAP_MAPS_DIR", "")
    if custom:
        custom_path = Path(custom)
        return custom_path if custom_path.is_absolute() else root / custom_path
    return root / _DEFAULT_MAPS_DIR


def db_path(root: Path) -> Path:
    return maps_dir(root) / "index.db"


def index_yaml_path(root: Path) -> Path:
    return maps_dir(root) / "index.yaml"


def logs_dir(root: Path) -> Path:
    if os.environ.get("SOURCEMAP_MAPS_DIR", ""):
        return maps_dir(root) / "logs"
    return maps_dir(root).parent / "logs"


def import_prompt_path() -> Either[str, Path | None]:
    val = os.environ.get("SOURCEMAP_IMPORT_LLM_PROMPT", "")
    if not val:
        return right(None)
    path = Path(val)
    if path.suffix != ".md":
        return left("import-prompt-must-be-md")
    return right(path)


def default_prompt_export_path(root: Path) -> Path:
    return maps_dir(root) / "prompt.md"
