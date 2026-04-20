from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pathspec

from sourcemap_indexer.domain.value_objects import ContentHash, Language
from sourcemap_indexer.infra.default_ignore import DEFAULT_IGNORE
from sourcemap_indexer.infra.hasher import hash_content
from sourcemap_indexer.lib.either import Either, Left, left, right

_EXT_MAP: dict[str, Language] = {
    ".py": Language.PY,
    ".sh": Language.SH,
    ".ts": Language.TS,
    ".tsx": Language.TSX,
    ".js": Language.JS,
    ".sql": Language.SQL,
    ".md": Language.MD,
    ".yaml": Language.YAML,
    ".yml": Language.YAML,
    ".json": Language.JSON,
    ".toml": Language.TOML,
}


@dataclass(frozen=True, slots=True)
class WalkedFile:
    path: str
    language: Language
    lines: int
    size_bytes: int
    content_hash: ContentHash
    last_modified: int


def detect_language(path: Path) -> Language:
    return _EXT_MAP.get(path.suffix.lower(), Language.OTHER)


def load_ignore_patterns(root: Path) -> Either[str, pathspec.PathSpec]:
    patterns = list(DEFAULT_IGNORE)
    for ignore_file in (root / ".gitignore", root / ".sourcemapignore"):
        if ignore_file.exists():
            try:
                patterns.extend(ignore_file.read_text(encoding="utf-8").splitlines())
            except OSError as error:
                return left(f"ignore-read-error: {error}")
    return right(pathspec.PathSpec.from_lines("gitignore", patterns))


def _count_lines(data: bytes) -> int:
    return len(data.decode(encoding="utf-8", errors="replace").splitlines())


def walk_project(
    root: Path,
    known_files: dict[str, tuple[int, int, int, str]] | None = None,
) -> Either[str, list[WalkedFile]]:
    spec_result = load_ignore_patterns(root)
    if isinstance(spec_result, Left):
        return spec_result
    spec = spec_result.value

    try:
        all_paths = sorted(root.rglob("*"))
    except PermissionError as error:
        return left(f"walk-error: {error}")
    known = known_files if known_files is not None else {}
    walked: list[WalkedFile] = []
    for file_path in all_paths:
        if not file_path.is_file():
            continue
        if file_path.is_symlink():
            continue
        relative = file_path.relative_to(root)
        if spec.match_file(str(relative)):
            continue
        language = detect_language(file_path)
        file_stat = file_path.stat()
        mtime = int(file_stat.st_mtime)
        size_bytes = file_stat.st_size
        path_str = str(relative)
        cached = known.get(path_str)
        if cached is not None and cached[0] == mtime and cached[1] == size_bytes:
            walked.append(
                WalkedFile(
                    path=path_str,
                    language=language,
                    lines=cached[2],
                    size_bytes=size_bytes,
                    content_hash=ContentHash(cached[3]),
                    last_modified=mtime,
                )
            )
        else:
            data = file_path.read_bytes()
            lines = _count_lines(data) if language != Language.OTHER else 0
            walked.append(
                WalkedFile(
                    path=path_str,
                    language=language,
                    lines=lines,
                    size_bytes=len(data),
                    content_hash=hash_content(data),
                    last_modified=mtime,
                )
            )
    return right(walked)
