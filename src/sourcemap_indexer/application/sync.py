from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.repository import ItemRepository
from sourcemap_indexer.domain.value_objects import (
    ContentHash,
    ItemId,
    Language,
)
from sourcemap_indexer.lib.either import Either, Left, left, right


@dataclass(frozen=True)
class SyncReport:
    inserted: int
    updated: int
    soft_deleted: int
    unchanged: int


def _load_index(index_path: Path) -> Either[str, dict[str, Any]]:
    try:
        data = yaml.safe_load(index_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return left("index-invalid-format")
        return right(data)
    except FileNotFoundError:
        return left("index-not-found")
    except yaml.YAMLError as error:
        return left(f"index-parse-error: {error}")
    except OSError as error:
        return left(f"index-read-error: {error}")


def run_sync(index_path: Path, repository: ItemRepository) -> Either[str, SyncReport]:
    load_result = _load_index(index_path)
    if isinstance(load_result, Left):
        return load_result
    data = load_result.value

    files: list[dict[str, Any]] = data.get("files", [])
    inserted = 0
    updated = 0
    unchanged = 0
    now = int(time.time())

    yaml_paths: set[str] = set()
    for entry in files:
        file_path: str = entry["path"]
        yaml_paths.add(file_path)
        new_hash = ContentHash(str(entry["content_hash"]))
        language = Language(str(entry["language"]))

        find_result = repository.find_by_path(file_path)
        if isinstance(find_result, Left):
            return find_result

        existing = find_result.value
        if existing is None:
            item = Item(
                id=ItemId.generate(),
                path=file_path,
                name=file_path.split("/")[-1],
                language=language,
                lines=int(entry.get("lines", 0)),
                size_bytes=int(entry.get("size_bytes", 0)),
                content_hash=new_hash,
                last_modified=int(entry.get("last_modified", 0)),
                needs_llm=True,
                created_at=now,
                updated_at=now,
            )
            upsert_result = repository.upsert(item)
            if isinstance(upsert_result, Left):
                return upsert_result
            inserted += 1
        elif existing.content_hash.hex_value == new_hash.hex_value:
            unchanged += 1
        else:
            updated_item = replace(
                existing,
                language=language,
                lines=int(entry.get("lines", 0)),
                size_bytes=int(entry.get("size_bytes", 0)),
                content_hash=new_hash,
                last_modified=int(entry.get("last_modified", 0)),
                needs_llm=True,
                updated_at=now,
            )
            upsert_result = repository.upsert(updated_item)
            if isinstance(upsert_result, Left):
                return upsert_result
            updated += 1

    paths_result = repository.find_all_paths()
    if isinstance(paths_result, Left):
        return paths_result
    existing_paths = paths_result.value
    soft_deleted = 0
    for gone_path in existing_paths - yaml_paths:
        find_result = repository.find_by_path(gone_path)
        if isinstance(find_result, Left):
            return find_result
        if find_result.value is not None:
            delete_result = repository.soft_delete(find_result.value.id, now)
            if isinstance(delete_result, Left):
                return delete_result
            soft_deleted += 1

    return right(
        SyncReport(
            inserted=inserted,
            updated=updated,
            soft_deleted=soft_deleted,
            unchanged=unchanged,
        )
    )
