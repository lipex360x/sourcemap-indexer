from __future__ import annotations

from pathlib import Path

import yaml

from sourcemap_indexer.lib.either import Either, left, right


def load_user_layers(config_directory: Path) -> Either[str, frozenset[str]]:
    layers_file = config_directory / "layers.yaml"
    if not layers_file.exists():
        return right(frozenset())
    try:
        data = yaml.safe_load(layers_file.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return left("layers-yaml-invalid")
    if not isinstance(data, dict):
        return right(frozenset())
    raw = data.get("layers", [])
    if not isinstance(raw, list):
        return right(frozenset())
    return right(frozenset(str(item) for item in raw))
