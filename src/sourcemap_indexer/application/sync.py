from __future__ import annotations

import time
from collections.abc import Callable
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


def _apply_entry(
    entry: dict[str, Any],
    existing: Item | None,
    language: Language,
    new_hash: ContentHash,
    repository: ItemRepository,
    now: int,
) -> Either[str, str]:
    if existing is None:
        item = Item(
            id=ItemId.generate(),
            path=entry["path"],
            name=entry["path"].split("/")[-1],
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
        return right("inserted")
    if existing.content_hash.hex_value == new_hash.hex_value:
        return right("unchanged")
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
    return right("updated")


def _process_entry(entry: dict[str, Any], repository: ItemRepository, now: int) -> Either[str, str]:
    find_result = repository.find_by_path(entry["path"])
    if isinstance(find_result, Left):
        return find_result
    return _apply_entry(
        entry,
        find_result.value,
        Language(str(entry["language"])),
        ContentHash(str(entry["content_hash"])),
        repository,
        now,
    )


def _sync_entries(
    files: list[dict[str, Any]],
    repository: ItemRepository,
    now: int,
    on_progress: Callable[[int, int], None] | None,
) -> Either[str, tuple[dict[str, int], set[str]]]:
    total = len(files)
    counters: dict[str, int] = {"inserted": 0, "updated": 0, "unchanged": 0}
    yaml_paths: set[str] = set()
    for idx, entry in enumerate(files, start=1):
        yaml_paths.add(entry["path"])
        if on_progress is not None:
            on_progress(idx, total)
        result = _process_entry(entry, repository, now)
        if isinstance(result, Left):
            return result
        counters[result.value] += 1
    return right((counters, yaml_paths))


def _soft_delete_gone(gone_path: str, repository: ItemRepository, now: int) -> Either[str, int]:
    find_result = repository.find_by_path(gone_path)
    if isinstance(find_result, Left):
        return find_result
    if find_result.value is None:
        return right(0)
    delete_result = repository.soft_delete(find_result.value.id, now)
    if isinstance(delete_result, Left):
        return delete_result
    return right(1)


def _sync_deletions(yaml_paths: set[str], repository: ItemRepository, now: int) -> Either[str, int]:
    paths_result = repository.find_all_paths()
    if isinstance(paths_result, Left):
        return paths_result
    soft_deleted = 0
    for gone_path in paths_result.value - yaml_paths:
        result = _soft_delete_gone(gone_path, repository, now)
        if isinstance(result, Left):
            return result
        soft_deleted += result.value
    return right(soft_deleted)


def run_sync(
    index_path: Path,
    repository: ItemRepository,
    on_progress: Callable[[int, int], None] | None = None,
) -> Either[str, SyncReport]:
    load_result = _load_index(index_path)
    if isinstance(load_result, Left):
        return load_result
    files: list[dict[str, Any]] = load_result.value.get("files", [])
    now = int(time.time())

    entries_result = _sync_entries(files, repository, now, on_progress)
    if isinstance(entries_result, Left):
        return entries_result
    counters, yaml_paths = entries_result.value

    deletions_result = _sync_deletions(yaml_paths, repository, now)
    if isinstance(deletions_result, Left):
        return deletions_result

    return right(
        SyncReport(
            inserted=counters["inserted"],
            updated=counters["updated"],
            soft_deleted=deletions_result.value,
            unchanged=counters["unchanged"],
        )
    )
