from __future__ import annotations

from pathlib import Path

from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.walker import (
    WalkedFile,
    detect_language,
    load_ignore_patterns,
    walk_project,
)
from sourcemap_indexer.lib.either import Left, Right


def test_detect_language_python() -> None:
    assert detect_language(Path("app.py")) == Language.PY


def test_detect_language_typescript() -> None:
    assert detect_language(Path("component.ts")) == Language.TS


def test_detect_language_tsx() -> None:
    assert detect_language(Path("Component.tsx")) == Language.TSX


def test_detect_language_javascript() -> None:
    assert detect_language(Path("index.js")) == Language.JS


def test_detect_language_shell() -> None:
    assert detect_language(Path("setup.sh")) == Language.SH


def test_detect_language_sql() -> None:
    assert detect_language(Path("schema.sql")) == Language.SQL


def test_detect_language_markdown() -> None:
    assert detect_language(Path("README.md")) == Language.MD


def test_detect_language_yaml() -> None:
    assert detect_language(Path("config.yaml")) == Language.YAML
    assert detect_language(Path("config.yml")) == Language.YAML


def test_detect_language_json() -> None:
    assert detect_language(Path("package.json")) == Language.JSON


def test_detect_language_toml() -> None:
    assert detect_language(Path("pyproject.toml")) == Language.TOML


def test_detect_language_unknown_extension() -> None:
    assert detect_language(Path("binary.exe")) == Language.OTHER


def test_load_ignore_patterns_without_sourcemapignore(tmp_path: Path) -> None:
    result = load_ignore_patterns(tmp_path)
    assert isinstance(result, Right)


def test_load_ignore_patterns_with_sourcemapignore(tmp_path: Path) -> None:
    (tmp_path / ".sourcemapignore").write_text("secrets/\n*.env\n")
    result = load_ignore_patterns(tmp_path)
    assert isinstance(result, Right)
    spec = result.value
    assert spec.match_file("secrets/token.txt")
    assert spec.match_file("prod.env")


def test_load_ignore_patterns_returns_left_on_read_error(tmp_path: Path) -> None:
    ignore_file = tmp_path / ".sourcemapignore"
    ignore_file.write_bytes(b"data")
    ignore_file.chmod(0o000)
    result = load_ignore_patterns(tmp_path)
    assert isinstance(result, Left)
    ignore_file.chmod(0o644)


def test_walk_project_returns_walked_files(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hello')\n")
    (tmp_path / "setup.sh").write_text("#!/usr/bin/env bash\necho hi\n")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    assert len(result.value) == 2


def test_walk_project_paths_are_relative(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert "src/app.py" in paths


def test_walk_project_sorted_alphabetically(tmp_path: Path) -> None:
    (tmp_path / "z.py").write_text("z = 1\n")
    (tmp_path / "a.py").write_text("a = 1\n")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert paths == sorted(paths)


def test_walk_project_respects_default_ignores(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    node_mod = tmp_path / "node_modules"
    node_mod.mkdir()
    (node_mod / "lib.js").write_text("module.exports = {}\n")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert all("node_modules" not in p for p in paths)


def test_walk_project_respects_sourcemapignore(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    (tmp_path / "secret.py").write_text("token = 'abc'\n")
    (tmp_path / ".sourcemapignore").write_text("secret.py\n")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert "secret.py" not in paths
    assert "main.py" in paths


def test_walk_project_skips_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real.py"
    real.write_text("x = 1\n")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert "link.py" not in paths
    assert "real.py" in paths


def test_walk_project_counts_lines(tmp_path: Path) -> None:
    (tmp_path / "script.py").write_text("a = 1\nb = 2\nc = 3\n")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    walked = result.value[0]
    assert walked.lines == 3


def test_walk_project_other_language_has_zero_lines(tmp_path: Path) -> None:
    (tmp_path / "binary.exe").write_bytes(b"\x00\x01\x02\x03")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    walked = result.value[0]
    assert walked.language == Language.OTHER
    assert walked.lines == 0


def test_walk_project_returns_left_when_ignore_unreadable(tmp_path: Path) -> None:
    ignore_file = tmp_path / ".sourcemapignore"
    ignore_file.write_bytes(b"data")
    ignore_file.chmod(0o000)
    result = walk_project(tmp_path)
    assert isinstance(result, Left)
    ignore_file.chmod(0o644)


def test_walked_file_has_content_hash(tmp_path: Path) -> None:
    data = b"hello world"
    (tmp_path / "file.py").write_bytes(data)
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    walked = result.value[0]
    assert isinstance(walked, WalkedFile)
    assert len(walked.content_hash.hex_value) == 64
