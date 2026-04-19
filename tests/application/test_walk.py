from __future__ import annotations

from pathlib import Path

import yaml

from sourcemap_indexer.application.walk import run_walk
from sourcemap_indexer.lib.either import Left, Right


def test_run_walk_returns_right_with_file_count(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    (tmp_path / "setup.sh").write_text("#!/usr/bin/env bash\necho hi\n")
    output = tmp_path / "index.yaml"
    result = run_walk(tmp_path, output)
    assert isinstance(result, Right)
    assert result.value == 2


def test_run_walk_writes_yaml_file(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("a = 1\n")
    output = tmp_path / "index.yaml"
    run_walk(tmp_path, output)
    assert output.exists()


def test_run_walk_yaml_has_correct_structure(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("a = 1\n")
    output = tmp_path / "index.yaml"
    run_walk(tmp_path, output)
    data = yaml.safe_load(output.read_text())
    assert data["version"] == 1
    assert "generated_at" in data
    assert "root" in data
    assert "files" in data
    assert len(data["files"]) == 1


def test_run_walk_yaml_file_entry_fields(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("line1\nline2\n")
    output = tmp_path / "index.yaml"
    run_walk(tmp_path, output)
    data = yaml.safe_load(output.read_text())
    entry = data["files"][0]
    assert entry["path"] == "app.py"
    assert entry["language"] == "py"
    assert entry["lines"] == 2
    assert "size_bytes" in entry
    assert "content_hash" in entry
    assert "last_modified" in entry


def test_run_walk_creates_parent_dirs(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    output = tmp_path / "nested" / "deep" / "index.yaml"
    result = run_walk(tmp_path, output)
    assert isinstance(result, Right)
    assert output.exists()


def test_run_walk_returns_left_when_walker_fails(tmp_path: Path) -> None:
    ignore_file = tmp_path / ".sourcemapignore"
    ignore_file.write_bytes(b"data")
    ignore_file.chmod(0o000)
    output = tmp_path / "index.yaml"
    result = run_walk(tmp_path, output)
    assert isinstance(result, Left)
    ignore_file.chmod(0o644)


def test_run_walk_returns_left_on_write_error(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    locked_dir = tmp_path / "out"
    locked_dir.mkdir()
    locked_dir.chmod(0o000)
    output = locked_dir / "index.yaml"
    result = run_walk(tmp_path, output)
    assert isinstance(result, Left)
    locked_dir.chmod(0o755)


def test_run_walk_yaml_root_is_absolute(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("x=1\n")
    output = tmp_path / "index.yaml"
    run_walk(tmp_path, output)
    data = yaml.safe_load(output.read_text())
    assert Path(data["root"]).is_absolute()
