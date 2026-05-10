from __future__ import annotations

from pathlib import Path

import pytest

from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.fs.walker import (
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


@pytest.mark.parametrize(
    ("filename", "language"),
    [
        ("model.php", Language.PHP),
        ("script.rb", Language.RUBY),
        ("server.go", Language.GO),
        ("main.rs", Language.RUST),
        ("Service.java", Language.JAVA),
        ("App.kt", Language.KOTLIN),
        ("build.gradle.kts", Language.KOTLIN),
        ("View.swift", Language.SWIFT),
        ("Pipeline.scala", Language.SCALA),
        ("driver.c", Language.C),
        ("header.h", Language.C),
        ("vector.cpp", Language.CPP),
        ("matrix.cc", Language.CPP),
        ("util.cxx", Language.CPP),
        ("vector.hpp", Language.CPP),
        ("Program.cs", Language.CSHARP),
        ("AppDelegate.m", Language.OBJC),
        ("ViewController.mm", Language.OBJC),
        ("init.lua", Language.LUA),
        ("widget.dart", Language.DART),
        ("module.ex", Language.ELIXIR),
        ("script.exs", Language.ELIXIR),
        ("server.erl", Language.ERLANG),
        ("Lib.hs", Language.HASKELL),
        ("module.ml", Language.OCAML),
        ("module.mli", Language.OCAML),
        ("core.clj", Language.CLOJURE),
        ("core.cljs", Language.CLOJURE),
        ("script.pl", Language.PERL),
        ("Lib.pm", Language.PERL),
        ("analysis.r", Language.R),
        ("analysis.R", Language.R),
        ("solver.jl", Language.JULIA),
        ("App.vue", Language.VUE),
        ("App.svelte", Language.SVELTE),
        ("page.astro", Language.ASTRO),
        ("style.css", Language.CSS),
        ("theme.scss", Language.SCSS),
        ("theme.less", Language.LESS),
        ("index.html", Language.HTML),
        ("index.htm", Language.HTML),
        ("config.xml", Language.XML),
        ("schema.graphql", Language.GRAPHQL),
        ("schema.gql", Language.GRAPHQL),
        ("user.proto", Language.PROTO),
        ("main.tf", Language.TERRAFORM),
        ("vars.tfvars", Language.TERRAFORM),
        ("default.nix", Language.NIX),
    ],
)
def test_detect_language_extended_extensions(filename: str, language: Language) -> None:
    assert detect_language(Path(filename)) == language


def test_detect_language_dockerfile_by_name() -> None:
    assert detect_language(Path("Dockerfile")) == Language.DOCKERFILE
    assert detect_language(Path("services/api/Dockerfile")) == Language.DOCKERFILE


def test_detect_language_makefile_by_name() -> None:
    assert detect_language(Path("Makefile")) == Language.MAKEFILE
    assert detect_language(Path("subdir/Makefile")) == Language.MAKEFILE


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


def test_load_ignore_patterns_reads_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("vendor/\n*.log\n")
    result = load_ignore_patterns(tmp_path)
    assert isinstance(result, Right)
    spec = result.value
    assert spec.match_file("vendor/lib.js")
    assert spec.match_file("app.log")


def test_load_ignore_patterns_merges_gitignore_and_sourcemapignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("vendor/\n")
    (tmp_path / ".sourcemapignore").write_text("secrets/\n")
    result = load_ignore_patterns(tmp_path)
    assert isinstance(result, Right)
    spec = result.value
    assert spec.match_file("vendor/lib.js")
    assert spec.match_file("secrets/key.txt")


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


@pytest.mark.parametrize(
    "ignored_path",
    [
        "vendor/lib.php",
        ".idea/workspace.xml",
        ".vscode/settings.json",
        ".DS_Store",
        "subdir/.DS_Store",
        "data.sqlite3",
        "fonts/icons.woff",
        "fonts/icons.woff2",
        "fonts/icons.ttf",
        "fonts/icons.otf",
        "fonts/icons.eot",
        "img/logo.png",
        "img/photo.jpg",
        "img/photo.jpeg",
        "img/anim.gif",
        "img/icon.svg",
        "img/banner.webp",
        "img/favicon.ico",
        "img/sprite.bmp",
        "img/scan.tiff",
        "pnpm-lock.yaml",
        "composer.lock",
        "yarn.lock",
    ],
)
def test_walk_project_default_ignores_extended(tmp_path: Path, ignored_path: str) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    target = tmp_path / ignored_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"data")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert ignored_path not in paths
    assert "main.py" in paths


def test_walk_project_ignores_dotenv_by_default(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    (tmp_path / ".env").write_text("SECRET=abc\n")
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert ".env" not in paths
    assert "main.py" in paths


def test_walk_project_ignores_docs_dir_via_extra_ignore(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    docs = tmp_path / ".docs"
    docs.mkdir()
    (docs / "log.yaml").write_text("timestamp: now\n")
    result = walk_project(tmp_path, extra_ignore=[".docs/"])
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert not any(p.startswith(".docs") for p in paths)
    assert "main.py" in paths


def test_walk_project_extra_ignore_excludes_custom_dir(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    custom = tmp_path / ".myconfig"
    custom.mkdir()
    (custom / "index.db").write_text("")
    result = walk_project(tmp_path, extra_ignore=[".myconfig/"])
    assert isinstance(result, Right)
    paths = [f.path for f in result.value]
    assert not any(p.startswith(".myconfig") for p in paths)
    assert "main.py" in paths


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


def test_walk_project_skips_read_when_mtime_and_size_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x = 1\n"
    file_path = tmp_path / "app.py"
    file_path.write_bytes(content)
    file_stat = file_path.stat()
    mtime = int(file_stat.st_mtime)
    size_bytes = file_stat.st_size
    stored_hash = "ab" * 32
    stored_lines = 42

    read_count = 0
    original_read_bytes = Path.read_bytes

    def counting_read(self: Path) -> bytes:
        nonlocal read_count
        read_count += 1
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read)

    known_files = {"app.py": (mtime, size_bytes, stored_lines, stored_hash)}
    result = walk_project(tmp_path, known_files=known_files)

    assert isinstance(result, Right)
    assert read_count == 0
    walked = result.value[0]
    assert walked.content_hash.hex_value == stored_hash
    assert walked.lines == stored_lines


def test_walk_project_rehashes_when_mtime_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x = 1\n"
    file_path = tmp_path / "app.py"
    file_path.write_bytes(content)
    file_stat = file_path.stat()
    size_bytes = file_stat.st_size
    stale_mtime = int(file_stat.st_mtime) - 1

    read_count = 0
    original_read_bytes = Path.read_bytes

    def counting_read(self: Path) -> bytes:
        nonlocal read_count
        read_count += 1
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read)

    known_files = {"app.py": (stale_mtime, size_bytes, 1, "cd" * 32)}
    result = walk_project(tmp_path, known_files=known_files)

    assert isinstance(result, Right)
    assert read_count == 1


def test_walk_project_rehashes_when_size_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x = 1\n"
    file_path = tmp_path / "app.py"
    file_path.write_bytes(content)
    file_stat = file_path.stat()
    mtime = int(file_stat.st_mtime)
    wrong_size = file_stat.st_size + 1

    read_count = 0
    original_read_bytes = Path.read_bytes

    def counting_read(self: Path) -> bytes:
        nonlocal read_count
        read_count += 1
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read)

    known_files = {"app.py": (mtime, wrong_size, 1, "cd" * 32)}
    result = walk_project(tmp_path, known_files=known_files)

    assert isinstance(result, Right)
    assert read_count == 1


def test_walk_project_rehashes_new_file_not_in_known(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "app.py").write_bytes(b"x = 1\n")

    read_count = 0
    original_read_bytes = Path.read_bytes

    def counting_read(self: Path) -> bytes:
        nonlocal read_count
        read_count += 1
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read)

    result = walk_project(tmp_path, known_files={})

    assert isinstance(result, Right)
    assert read_count == 1


def test_walk_project_known_files_none_hashes_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "app.py").write_bytes(b"x = 1\n")
    (tmp_path / "other.py").write_bytes(b"y = 2\n")

    read_count = 0
    original_read_bytes = Path.read_bytes

    def counting_read(self: Path) -> bytes:
        nonlocal read_count
        read_count += 1
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read)

    result = walk_project(tmp_path, known_files=None)

    assert isinstance(result, Right)
    assert read_count == 2


def test_load_ignore_uses_config_dir_ignore_when_present(tmp_path: Path) -> None:
    config = tmp_path / ".sourcemap"
    config.mkdir()
    (config / "ignore").write_text("private/\n")
    result = load_ignore_patterns(tmp_path, sourcemap_dir=config)
    assert isinstance(result, Right)
    assert result.value.match_file("private/secret.txt")


def test_load_ignore_falls_back_to_root_sourcemapignore(tmp_path: Path) -> None:
    (tmp_path / ".sourcemapignore").write_text("legacy/\n")
    result = load_ignore_patterns(tmp_path, sourcemap_dir=tmp_path / ".sourcemap")
    assert isinstance(result, Right)
    assert result.value.match_file("legacy/old.py")


def test_load_ignore_config_dir_wins_over_root_sourcemapignore(tmp_path: Path) -> None:
    config = tmp_path / ".sourcemap"
    config.mkdir()
    (config / "ignore").write_text("new-pattern/\n")
    (tmp_path / ".sourcemapignore").write_text("old-pattern/\n")
    result = load_ignore_patterns(tmp_path, sourcemap_dir=config)
    assert isinstance(result, Right)
    spec = result.value
    assert spec.match_file("new-pattern/file.py")
    assert not spec.match_file("old-pattern/file.py")


def test_walk_project_returns_left_on_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_permission(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("access denied")

    monkeypatch.setattr(Path, "rglob", _raise_permission)
    result = walk_project(tmp_path)
    assert isinstance(result, Left)
    assert "walk-error" in result.error


def test_walk_project_skips_file_when_stat_raises_filenotfounderror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    original_stat = Path.stat

    def _raise_for_target(self: Path, **kwargs: object) -> object:
        if self.name == "app.py":
            raise FileNotFoundError("vanished")
        return original_stat(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "stat", _raise_for_target)
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    assert not any(walked.path == "app.py" for walked in result.value)


def test_walk_project_skips_file_when_read_bytes_raises_filenotfounderror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    original_read = Path.read_bytes

    def _raise_for_target(self: Path) -> bytes:
        if self.name == "app.py":
            raise FileNotFoundError("vanished")
        return original_read(self)

    monkeypatch.setattr(Path, "read_bytes", _raise_for_target)
    result = walk_project(tmp_path)
    assert isinstance(result, Right)
    assert not any(walked.path == "app.py" for walked in result.value)


def test_load_ignore_config_exists_oserror_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / ".sourcemap"
    config.mkdir()
    original_exists = Path.exists

    def _raise_for_ignore(self: Path) -> bool:
        if self.name == "ignore" and self.parent == config:
            raise PermissionError("access denied")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", _raise_for_ignore)
    result = load_ignore_patterns(tmp_path, sourcemap_dir=config)
    assert isinstance(result, Right)


def test_load_ignore_root_sourcemapignore_exists_oserror_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_exists = Path.exists

    def _raise_for_sourcemapignore(self: Path) -> bool:
        if self.name == ".sourcemapignore":
            raise PermissionError("access denied")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", _raise_for_sourcemapignore)
    result = load_ignore_patterns(tmp_path)
    assert isinstance(result, Right)
