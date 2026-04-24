from __future__ import annotations

from pathlib import Path

from sourcemap_indexer.infra.config.project_config import ProjectMeta, load_project_meta
from sourcemap_indexer.lib.either import Left, Right


def test_missing_file_returns_none(tmp_path: Path) -> None:
    result = load_project_meta(tmp_path)
    assert isinstance(result, Right)
    assert result.value is None


def test_valid_yaml_returns_all_fields(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text(
        "name: blueprint\n"
        "version: 1\n"
        "purpose: Language-agnostic foundation\n"
        "audience: claude, engineer\n"
        "license: MIT\n"
    )
    result = load_project_meta(tmp_path)
    assert isinstance(result, Right)
    assert result.value == ProjectMeta(
        name="blueprint",
        version="1",
        purpose="Language-agnostic foundation",
        audience="claude, engineer",
        license_name="MIT",
    )


def test_partial_fields_fill_none(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text("name: partial\npurpose: just these two\n")
    result = load_project_meta(tmp_path)
    assert isinstance(result, Right)
    assert result.value == ProjectMeta(
        name="partial",
        version=None,
        purpose="just these two",
        audience=None,
        license_name=None,
    )


def test_audience_list_joins_to_string(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text("audience:\n  - claude\n  - engineer\n")
    result = load_project_meta(tmp_path)
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.audience == "claude, engineer"


def test_version_int_coerced_to_string(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text("version: 2\n")
    result = load_project_meta(tmp_path)
    assert isinstance(result, Right)
    assert result.value is not None
    assert result.value.version == "2"


def test_malformed_yaml_returns_left(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text("name: [\nbroken")
    result = load_project_meta(tmp_path)
    assert isinstance(result, Left)
    assert result.error == "project-yaml-invalid"


def test_non_mapping_yaml_returns_empty_meta(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text("- just\n- a\n- list\n")
    result = load_project_meta(tmp_path)
    assert isinstance(result, Right)
    assert result.value is None


def test_empty_yaml_returns_none(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text("")
    result = load_project_meta(tmp_path)
    assert isinstance(result, Right)
    assert result.value is None
