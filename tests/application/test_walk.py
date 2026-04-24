from __future__ import annotations

from pathlib import Path

import pytest
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


def test_run_walk_known_files_none_behaves_as_today(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    output = tmp_path / "index.yaml"
    result = run_walk(tmp_path, output, known_files=None)
    assert isinstance(result, Right)
    assert result.value == 1


def test_run_walk_skips_read_when_known_files_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x = 1\n"
    file_path = tmp_path / "app.py"
    file_path.write_bytes(content)
    file_stat = file_path.stat()
    mtime = int(file_stat.st_mtime)
    size_bytes = file_stat.st_size
    stored_hash = "ab" * 32

    read_count = 0
    original_read_bytes = Path.read_bytes

    def counting_read(self: Path) -> bytes:
        nonlocal read_count
        read_count += 1
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read)

    known_files = {"app.py": (mtime, size_bytes, 1, stored_hash)}
    output = tmp_path / "index.yaml"
    result = run_walk(tmp_path, output, known_files=known_files)

    assert isinstance(result, Right)
    assert read_count == 0


def test_run_walk_ignores_output_dir_dynamically(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    output = tmp_path / ".myoutput" / "maps" / "index.yaml"
    (tmp_path / ".myoutput" / "maps").mkdir(parents=True)
    (tmp_path / ".myoutput" / "maps" / "index.db").write_text("")
    result = run_walk(tmp_path, output)
    assert isinstance(result, Right)
    data = yaml.safe_load(output.read_text())
    paths = [f["path"] for f in data["files"]]
    assert not any(p.startswith(".myoutput") for p in paths)
    assert "main.py" in paths


def test_run_walk_output_outside_root_does_not_add_ignore_pattern(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n")
    outside_dir = tmp_path.parent / "external_output"
    outside_dir.mkdir(exist_ok=True)
    output = outside_dir / "index.yaml"
    result = run_walk(tmp_path / "src", output)
    assert isinstance(result, Right)
    (outside_dir / "index.yaml").unlink(missing_ok=True)
    outside_dir.rmdir()


def test_run_walk_output_path_absent_when_tmp_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    output = tmp_path / "index.yaml"
    temp_file = output.with_suffix(".yaml.tmp")

    original_write = Path.write_text

    def fail_on_temp(self: Path, text: str, **kwargs: object) -> None:
        if self == temp_file:
            raise OSError("simulated mid-write failure")
        return original_write(self, text, **kwargs)  # type: ignore[return-value]

    monkeypatch.setattr(Path, "write_text", fail_on_temp)
    result = run_walk(tmp_path, output)

    assert isinstance(result, Left)
    assert not output.exists()


def test_run_walk_no_leftover_temp_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    output = tmp_path / "index.yaml"
    temp_file = output.with_suffix(".yaml.tmp")
    temp_file.write_text("stale")

    def always_fail(self: Path, text: str, **kwargs: object) -> None:
        raise OSError("simulated disk-full failure")

    monkeypatch.setattr(Path, "write_text", always_fail)
    run_walk(tmp_path, output)

    assert not temp_file.exists()


def test_run_walk_no_leftover_temp_on_success(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    output = tmp_path / "index.yaml"
    temp_file = output.with_suffix(".yaml.tmp")
    temp_file.write_text("stale")

    result = run_walk(tmp_path, output)

    assert isinstance(result, Right)
    assert not temp_file.exists()
