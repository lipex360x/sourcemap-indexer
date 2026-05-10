from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pathspec

from sourcemap_indexer.domain.value_objects import ContentHash, Language
from sourcemap_indexer.infra.fs.default_ignore import DEFAULT_IGNORE
from sourcemap_indexer.infra.fs.hasher import hash_content
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
    ".php": Language.PHP,
    ".rb": Language.RUBY,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".java": Language.JAVA,
    ".kt": Language.KOTLIN,
    ".kts": Language.KOTLIN,
    ".swift": Language.SWIFT,
    ".scala": Language.SCALA,
    ".sc": Language.SCALA,
    ".c": Language.C,
    ".h": Language.C,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".hh": Language.CPP,
    ".hxx": Language.CPP,
    ".cs": Language.CSHARP,
    ".m": Language.OBJC,
    ".mm": Language.OBJC,
    ".lua": Language.LUA,
    ".dart": Language.DART,
    ".ex": Language.ELIXIR,
    ".exs": Language.ELIXIR,
    ".erl": Language.ERLANG,
    ".hrl": Language.ERLANG,
    ".hs": Language.HASKELL,
    ".ml": Language.OCAML,
    ".mli": Language.OCAML,
    ".clj": Language.CLOJURE,
    ".cljs": Language.CLOJURE,
    ".cljc": Language.CLOJURE,
    ".edn": Language.CLOJURE,
    ".pl": Language.PERL,
    ".pm": Language.PERL,
    ".r": Language.R,
    ".jl": Language.JULIA,
    ".vue": Language.VUE,
    ".svelte": Language.SVELTE,
    ".astro": Language.ASTRO,
    ".css": Language.CSS,
    ".scss": Language.SCSS,
    ".less": Language.LESS,
    ".html": Language.HTML,
    ".htm": Language.HTML,
    ".xml": Language.XML,
    ".graphql": Language.GRAPHQL,
    ".gql": Language.GRAPHQL,
    ".proto": Language.PROTO,
    ".tf": Language.TERRAFORM,
    ".tfvars": Language.TERRAFORM,
    ".nix": Language.NIX,
}

_NAME_MAP: dict[str, Language] = {
    "dockerfile": Language.DOCKERFILE,
    "makefile": Language.MAKEFILE,
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
    suffix = path.suffix.lower()
    if suffix:
        return _EXT_MAP.get(suffix, Language.OTHER)
    return _NAME_MAP.get(path.name.lower(), Language.OTHER)


def _resolve_sourcemapignore(root: Path, sourcemap_dir: Path | None) -> Path | None:
    config_ignore = (sourcemap_dir / "ignore") if sourcemap_dir else None
    try:
        if config_ignore is not None and config_ignore.exists():
            return config_ignore
    except OSError:
        pass
    root_sourcemapignore = root / ".sourcemapignore"
    try:
        if root_sourcemapignore.exists():
            return root_sourcemapignore
    except OSError:
        pass
    return None


def load_ignore_patterns(
    root: Path,
    extra_ignore: list[str] | None = None,
    sourcemap_dir: Path | None = None,
) -> Either[str, pathspec.PathSpec]:
    patterns = list(DEFAULT_IGNORE) + list(extra_ignore or [])
    sourcemapignore = _resolve_sourcemapignore(root, sourcemap_dir)
    for ignore_file in filter(None, (root / ".gitignore", sourcemapignore)):
        if ignore_file.exists():
            try:
                patterns.extend(ignore_file.read_text(encoding="utf-8").splitlines())
            except OSError as error:
                return left(f"ignore-read-error: {error}")
    return right(pathspec.PathSpec.from_lines("gitignore", patterns))


def _count_lines(data: bytes) -> int:
    return len(data.decode(encoding="utf-8", errors="replace").splitlines())


def _walk_file(
    file_path: Path,
    root: Path,
    spec: pathspec.PathSpec,
    known: dict[str, tuple[int, int, int, str]],
) -> WalkedFile | None:
    try:
        if not file_path.is_file() or file_path.is_symlink():
            return None
        relative = file_path.relative_to(root)
        if spec.match_file(str(relative)):
            return None
        language = detect_language(file_path)
        file_stat = file_path.stat()
        mtime = int(file_stat.st_mtime)
        size_bytes = file_stat.st_size
        path_str = str(relative)
        cached = known.get(path_str)
        if cached is not None and cached[0] == mtime and cached[1] == size_bytes:
            return WalkedFile(
                path=path_str,
                language=language,
                lines=cached[2],
                size_bytes=size_bytes,
                content_hash=ContentHash(cached[3]),
                last_modified=mtime,
            )
        data = file_path.read_bytes()
        lines = _count_lines(data) if language != Language.OTHER else 0
        return WalkedFile(
            path=path_str,
            language=language,
            lines=lines,
            size_bytes=len(data),
            content_hash=hash_content(data),
            last_modified=mtime,
        )
    except OSError:
        return None


def walk_project(
    root: Path,
    known_files: dict[str, tuple[int, int, int, str]] | None = None,
    extra_ignore: list[str] | None = None,
    sourcemap_dir: Path | None = None,
) -> Either[str, list[WalkedFile]]:
    spec_result = load_ignore_patterns(root, extra_ignore=extra_ignore, sourcemap_dir=sourcemap_dir)
    if isinstance(spec_result, Left):
        return spec_result
    spec = spec_result.value
    try:
        all_paths = sorted(root.rglob("*"))
    except PermissionError as error:
        return left(f"walk-error: {error}")
    known = known_files if known_files is not None else {}
    return right(list(filter(None, (_walk_file(p, root, spec, known) for p in all_paths))))
