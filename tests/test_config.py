from __future__ import annotations

from pathlib import Path

import pytest

from sourcemap_indexer.config import (
    db_path,
    default_prompt_export_path,
    find_project_root,
    import_prompt_path,
    index_yaml_path,
    llm_cli_effort,
    llm_cli_model,
    llm_provider_name,
    logs_dir,
    maps_dir,
)
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
    assert maps_dir(tmp_path) == tmp_path / ".sourcemap"


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
    assert db_path(tmp_path) == tmp_path / ".sourcemap" / "index.db"


def test_index_yaml_path_uses_maps_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", ".sourcemap")
    assert index_yaml_path(tmp_path) == tmp_path / ".sourcemap" / "index.yaml"


def test_index_yaml_path_returns_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_MAPS_DIR", raising=False)
    assert index_yaml_path(tmp_path) == tmp_path / ".sourcemap" / "index.yaml"


def test_logs_dir_default_is_inside_maps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_MAPS_DIR", raising=False)
    assert logs_dir(tmp_path) == tmp_path / ".sourcemap" / "logs"


def test_logs_dir_follows_custom_maps_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", "my/maps")
    assert logs_dir(tmp_path) == tmp_path / "my" / "maps" / "logs"


def test_logs_dir_absolute_maps_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    abs_maps = tmp_path / "data" / "maps"
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", str(abs_maps))
    assert logs_dir(tmp_path) == abs_maps / "logs"


def test_import_prompt_path_none_when_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_IMPORT_LLM_PROMPT", raising=False)
    result = import_prompt_path()
    assert isinstance(result, Right)
    assert result.value is None


def test_import_prompt_path_returns_path_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt_file = tmp_path / "my-prompt.md"
    monkeypatch.setenv("SOURCEMAP_IMPORT_LLM_PROMPT", str(prompt_file))
    result = import_prompt_path()
    assert isinstance(result, Right)
    assert result.value == prompt_file


def test_import_prompt_path_rejects_non_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_IMPORT_LLM_PROMPT", str(tmp_path / "prompt.txt"))
    result = import_prompt_path()
    assert isinstance(result, Left)
    assert result.error == "import-prompt-must-be-md"


def test_default_prompt_export_path_is_inside_maps_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCEMAP_MAPS_DIR", raising=False)
    assert default_prompt_export_path(tmp_path) == tmp_path / ".sourcemap" / "prompt.md"


def test_default_prompt_export_path_follows_custom_maps_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCEMAP_MAPS_DIR", "out/maps")
    assert default_prompt_export_path(tmp_path) == tmp_path / "out" / "maps" / "prompt.md"


def test_llm_provider_name_defaults_to_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_PROVIDER", raising=False)
    assert llm_provider_name() == "http"


def test_llm_provider_name_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_PROVIDER", "claude-cli")
    assert llm_provider_name() == "claude-cli"


def test_llm_cli_model_none_when_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_CLI_MODEL", raising=False)
    assert llm_cli_model() is None


def test_llm_cli_model_returns_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_CLI_MODEL", "claude-sonnet-4-6")
    assert llm_cli_model() == "claude-sonnet-4-6"


def test_llm_cli_effort_none_when_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_CLI_EFFORT", raising=False)
    assert llm_cli_effort() is None


def test_llm_cli_effort_returns_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_CLI_EFFORT", "high")
    assert llm_cli_effort() == "high"
