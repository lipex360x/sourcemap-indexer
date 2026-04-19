from __future__ import annotations

from pathlib import Path

from sourcemap_indexer.config import db_path, find_project_root, index_yaml_path
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


def test_db_path_returns_expected_path(tmp_path: Path) -> None:
    result = db_path(tmp_path)
    assert result == tmp_path / ".docs" / "maps" / "index.db"


def test_index_yaml_path_returns_expected_path(tmp_path: Path) -> None:
    result = index_yaml_path(tmp_path)
    assert result == tmp_path / ".docs" / "maps" / "index.yaml"
