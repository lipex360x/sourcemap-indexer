from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sourcemap_indexer.lib.either import Either, left, right


@dataclass(frozen=True, slots=True)
class ProjectMeta:
    name: str | None = None
    version: str | None = None
    purpose: str | None = None
    audience: str | None = None
    license_name: str | None = None


def _coerce_scalar(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _coerce_audience(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _any_field_set(meta: ProjectMeta) -> bool:
    return any((meta.name, meta.version, meta.purpose, meta.audience, meta.license_name))


def load_project_meta(config_directory: Path) -> Either[str, ProjectMeta | None]:
    project_file = config_directory / "project.yaml"
    if not project_file.exists():
        return right(None)
    try:
        data = yaml.safe_load(project_file.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return left("project-yaml-invalid")
    if not isinstance(data, dict):
        return right(None)
    meta = ProjectMeta(
        name=_coerce_scalar(data.get("name")),
        version=_coerce_scalar(data.get("version")),
        purpose=_coerce_scalar(data.get("purpose")),
        audience=_coerce_audience(data.get("audience")),
        license_name=_coerce_scalar(data.get("license")),
    )
    return right(meta if _any_field_set(meta) else None)
