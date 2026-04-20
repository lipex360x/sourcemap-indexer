from __future__ import annotations

import time
from pathlib import Path

import yaml

from sourcemap_indexer.infra.walker import walk_project
from sourcemap_indexer.lib.either import Either, Left, left, right


def _output_dir_pattern(root: Path, output_path: Path) -> str | None:
    try:
        return str(output_path.parent.parent.relative_to(root)) + "/"
    except ValueError:
        return None


def _relative_dir_pattern(root: Path, directory: Path) -> str | None:
    try:
        return str(directory.relative_to(root)) + "/"
    except ValueError:
        return None


def run_walk(
    root: Path,
    output_path: Path,
    known_files: dict[str, tuple[int, int, int, str]] | None = None,
    extra_ignore: list[str] | None = None,
    config_dir: Path | None = None,
) -> Either[str, int]:
    auto_exclude = filter(
        None,
        [
            _output_dir_pattern(root, output_path),
            _relative_dir_pattern(root, config_dir) if config_dir else None,
        ],
    )
    combined = list(extra_ignore or []) + list(auto_exclude)
    walked_result = walk_project(
        root, known_files=known_files, extra_ignore=combined or None, config_dir=config_dir
    )
    if isinstance(walked_result, Left):
        return walked_result
    walked = walked_result.value
    index = {
        "version": 1,
        "generated_at": int(time.time()),
        "root": str(root.resolve()),
        "files": [
            {
                "path": file.path,
                "language": str(file.language),
                "lines": file.lines,
                "size_bytes": file.size_bytes,
                "content_hash": file.content_hash.hex_value,
                "last_modified": file.last_modified,
            }
            for file in walked
        ],
    }
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml.dump(index, allow_unicode=True), encoding="utf-8")
    except OSError as error:
        return left(f"write-error: {error}")
    return right(len(walked))
