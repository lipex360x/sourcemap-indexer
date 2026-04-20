from __future__ import annotations

from pathlib import Path

import pytest

from sourcemap_indexer.config import db_path, find_project_root, index_yaml_path, maps_dir
from sourcemap_indexer.lib.either import Left, Right


def test_find_project_root_finds_git_in_current(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    result = find_project_root(tmp_path)
    assert isinstance(result, Right)
    assert result.value == tmp_path


def test_find_project_root_finds_git_in_parent(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    subdir = tmp_path / "src" / "module"
    subdir.mkdir(parents=True)
    result = find_project_root(subdir)
    assert isinstance(result, Right)
    assert result.value == tmp_path


def test_find_project_root_returns_left_when_no_git(tmp_path: Path) -> None:
    isolated = tmp_path / "no_git"
    isolated.mkdir()
    result = find_project_root(isolated)
    assert isinstance(result, Left)
    assert result.error == "git-root-not-found"


def test_maps_dir_returns_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_MAPS_DIR", raising=False)
    assert maps_dir(tmp_path) == tmp_path / ".docs" / "maps"


def test_maps_dir_relative_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", ".sourcemap")
    assert maps_dir(tmp_path) == tmp_path / ".sourcemap"


def test_maps_dir_absolute_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    abs_dir = tmp_path / "custom" / "output"
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", str(abs_dir))
    assert maps_dir(tmp_path) == abs_dir


def test_db_path_uses_maps_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", ".sourcemap")
    assert db_path(tmp_path) == tmp_path / ".sourcemap" / "index.db"


def test_db_path_returns_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_MAPS_DIR", raising=False)
    assert db_path(tmp_path) == tmp_path / ".docs" / "maps" / "index.db"


def test_index_yaml_path_uses_maps_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", ".sourcemap")
    assert index_yaml_path(tmp_path) == tmp_path / ".sourcemap" / "index.yaml"


def test_index_yaml_path_returns_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_MAPS_DIR", raising=False)
    assert index_yaml_path(tmp_path) == tmp_path / ".docs" / "maps" / "index.yaml"
