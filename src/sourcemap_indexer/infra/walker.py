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
    ignore_file = root / ".sourcemapignore"
    if ignore_file.exists():
        try:
            patterns.extend(ignore_file.read_text(encoding="utf-8").splitlines())
        except OSError as error:
            return left(f"ignore-read-error: {error}")
    return right(pathspec.PathSpec.from_lines("gitignore", patterns))


def _count_lines(data: bytes) -> int:
    return len(data.decode(encoding="utf-8", errors="replace").splitlines())


def walk_project(root: Path) -> Either[str, list[WalkedFile]]:
    spec_result = load_ignore_patterns(root)
    if isinstance(spec_result, Left):
        return spec_result
    spec = spec_result.value

    walked: list[WalkedFile] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.is_symlink():
            continue
        relative = file_path.relative_to(root)
        if spec.match_file(str(relative)):
            continue
        language = detect_language(file_path)
        data = file_path.read_bytes()
        lines = _count_lines(data) if language != Language.OTHER else 0
        walked.append(
            WalkedFile(
                path=str(relative),
                language=language,
                lines=lines,
                size_bytes=len(data),
                content_hash=hash_content(data),
                last_modified=int(file_path.stat().st_mtime),
            )
        )
    return right(walked)
