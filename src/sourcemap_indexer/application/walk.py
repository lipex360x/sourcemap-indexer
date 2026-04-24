from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

import yaml

from sourcemap_indexer.infra.fs.walker import walk_project
from sourcemap_indexer.lib.either import Either, Left, left, right


def _maps_dir_pattern(root: Path, output_path: Path) -> str | None:
    try:
        return str(output_path.parent.relative_to(root)) + "/"
    except ValueError:
        return None


def run_walk(
    root: Path,
    output_path: Path,
    known_files: dict[str, tuple[int, int, int, str]] | None = None,
    extra_ignore: list[str] | None = None,
) -> Either[str, int]:
    sourcemap_dir = output_path.parent
    maps_pattern = _maps_dir_pattern(root, output_path)
    combined = list(extra_ignore or []) + ([maps_pattern] if maps_pattern else [])
    walked_result = walk_project(
        root,
        known_files=known_files,
        extra_ignore=combined or None,
        sourcemap_dir=sourcemap_dir,
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
    temp_path = output_path.with_suffix(".yaml.tmp")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(yaml.dump(index, allow_unicode=True), encoding="utf-8")
        os.replace(temp_path, output_path)
    except OSError as error:
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
        return left(f"write-error: {error}")
    return right(len(walked))
