from __future__ import annotations

from pathlib import Path

from sourcemap_indexer.infra.layers_config import load_user_layers
from sourcemap_indexer.lib.either import Left, Right


def test_missing_file_returns_empty_set(tmp_path: Path) -> None:
    result = load_user_layers(tmp_path)
    assert isinstance(result, Right)
    assert result.value == frozenset()


def test_valid_yaml_returns_layers(tmp_path: Path) -> None:
    (tmp_path / "layers.yaml").write_text("layers:\n  - controller\n  - service\n")
    result = load_user_layers(tmp_path)
    assert isinstance(result, Right)
    assert result.value == frozenset({"controller", "service"})


def test_empty_layers_list_returns_empty_set(tmp_path: Path) -> None:
    (tmp_path / "layers.yaml").write_text("layers: []\n")
    result = load_user_layers(tmp_path)
    assert isinstance(result, Right)
    assert result.value == frozenset()


def test_yaml_without_layers_key_returns_empty_set(tmp_path: Path) -> None:
    (tmp_path / "layers.yaml").write_text("other_key: value\n")
    result = load_user_layers(tmp_path)
    assert isinstance(result, Right)
    assert result.value == frozenset()


def test_malformed_yaml_returns_left(tmp_path: Path) -> None:
    (tmp_path / "layers.yaml").write_text("layers: [\nbroken")
    result = load_user_layers(tmp_path)
    assert isinstance(result, Left)
    assert result.error == "layers-yaml-invalid"


def test_layers_values_are_strings(tmp_path: Path) -> None:
    (tmp_path / "layers.yaml").write_text("layers:\n  - usecase\n  - gateway\n")
    result = load_user_layers(tmp_path)
    assert isinstance(result, Right)
    assert all(isinstance(layer, str) for layer in result.value)
