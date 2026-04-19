from __future__ import annotations

from pathlib import Path

from sourcemap_indexer.lib.either import Either, left, right


def find_project_root(start: Path) -> Either[str, Path]:
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return right(current)
        parent = current.parent
        if parent == current:
            return left("git-root-not-found")
        current = parent


def db_path(root: Path) -> Path:
    return root / ".docs" / "maps" / "index.db"


def index_yaml_path(root: Path) -> Path:
    return root / ".docs" / "maps" / "index.yaml"
