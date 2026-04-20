#!/usr/bin/env python3
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from sourcemap_indexer.infra.walker import WalkedFile, walk_project  # noqa: E402

KnownFiles = dict[str, tuple[int, int, int, str]]


def _measure(root: Path, known_files: KnownFiles | None) -> tuple[float, int]:
    read_bytes_total = 0
    original_read_bytes = Path.read_bytes

    def tracking_read(self: Path) -> bytes:
        nonlocal read_bytes_total
        data = original_read_bytes(self)
        read_bytes_total += len(data)
        return data

    Path.read_bytes = tracking_read  # type: ignore[method-assign]
    try:
        start = time.perf_counter()
        result = walk_project(root, known_files=known_files)
        elapsed = time.perf_counter() - start
    finally:
        Path.read_bytes = original_read_bytes  # type: ignore[method-assign]

    if not hasattr(result, "value"):
        raise RuntimeError(f"walk failed: {result}")

    return elapsed, read_bytes_total


def _build_known(walked: list[WalkedFile]) -> KnownFiles:
    return {
        file.path: (file.last_modified, file.size_bytes, file.lines, file.content_hash.hex_value)
        for file in walked
    }


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"target: {root}")

    first_elapsed, first_bytes = _measure(root, None)
    print(f"first walk  — {first_elapsed:.3f}s, {first_bytes:,} bytes read")

    first_result = walk_project(root, known_files=None)
    known_files = _build_known(first_result.value)  # type: ignore[union-attr]

    second_elapsed, second_bytes = _measure(root, known_files)
    print(f"second walk — {second_elapsed:.3f}s, {second_bytes:,} bytes read (all unchanged)")

    if first_bytes > 0:
        ratio = second_bytes / first_bytes
        print(f"bytes ratio — {ratio:.1%} of first walk")


if __name__ == "__main__":
    main()
