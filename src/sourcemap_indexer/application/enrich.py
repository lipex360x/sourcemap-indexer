from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.repository import ItemRepository
from sourcemap_indexer.domain.value_objects import Language, Layer, Stability
from sourcemap_indexer.infra.llm_client import EnrichmentResult
from sourcemap_indexer.lib.either import Either, Left, left, right


class _EnrichClient(Protocol):
    def enrich(
        self,
        path: str,
        language: Language,
        content: str,
        extra_instruction: str | None = None,
    ) -> Either[str, EnrichmentResult]: ...


@dataclass(frozen=True)
class EnrichReport:
    enriched: int
    failed: int
    skipped: int
    errors: tuple[str, ...]


def _progress_notify(
    on_progress: Callable[[str, bool, int, int], None] | None,
    path: str,
    success: bool,
    done: int,
    total: int,
) -> None:
    if on_progress:
        on_progress(path, success, done, total)


def _handle_empty_file(item: Item, repository: ItemRepository, now: int) -> Either[str, None]:
    stub = item.with_llm_enrichment(
        purpose="Empty file",
        layer="unknown",
        stability=Stability.UNKNOWN,
        tags=frozenset({"empty-file"}),
        side_effects=frozenset(),
        invariants=(),
        llm_at=now,
    )
    upsert_result = repository.upsert(stub)
    if isinstance(upsert_result, Left):
        return left(f"{upsert_result.error}: {item.path}")
    return right(None)


def _handle_normal_file(
    item: Item,
    content: str,
    client: _EnrichClient,
    repository: ItemRepository,
    valid_layers: frozenset[str] | None,
    extra_instruction: str | None,
    now: int,
) -> Either[str, None]:
    enrich_result = client.enrich(item.path, item.language, content, extra_instruction)
    if isinstance(enrich_result, Left):
        return left(f"{enrich_result.error}: {item.path}")
    result_data = enrich_result.value
    if valid_layers is not None and result_data.layer not in valid_layers:
        return left(f"invalid-layer: {item.path}")
    updated = item.with_llm_enrichment(
        purpose=result_data.purpose,
        layer=result_data.layer,
        stability=result_data.stability,
        tags=result_data.tags,
        side_effects=result_data.side_effects,
        invariants=result_data.invariants,
        llm_at=now,
    )
    upsert_result = repository.upsert(updated)
    if isinstance(upsert_result, Left):
        return left(f"{upsert_result.error}: {item.path}")
    return right(None)


def _enrich_item(
    item: Item,
    root: Path,
    client: _EnrichClient,
    repository: ItemRepository,
    valid_layers: frozenset[str] | None,
    extra_instruction: str | None,
    now: int,
) -> Either[str, None]:
    try:
        content = (root / item.path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return left(f"read-error: {item.path}")
    if item.size_bytes == 0:
        return _handle_empty_file(item, repository, now)
    return _handle_normal_file(
        item, content, client, repository, valid_layers, extra_instruction, now
    )


def run_enrich(
    root: Path,
    repository: ItemRepository,
    client: _EnrichClient,
    batch_limit: int | None = None,
    on_progress: Callable[[str, bool, int, int], None] | None = None,
    force: bool = False,
    layer_filter: Layer | None = None,
    language_filter: Language | None = None,
    extra_instruction: str | None = None,
    path_filter: str | None = None,
    valid_layers: frozenset[str] | None = None,
) -> Either[str, EnrichReport]:
    items_result = repository.find_needs_llm(
        limit=batch_limit,
        force=force,
        layer=layer_filter,
        language=language_filter,
        path=path_filter,
    )
    if isinstance(items_result, Left):
        return items_result
    pending = items_result.value
    total_items = len(pending)
    enriched = failed = 0
    errors: list[str] = []
    now = int(time.time())
    for done, item in enumerate(pending, start=1):
        result = _enrich_item(item, root, client, repository, valid_layers, extra_instruction, now)
        if isinstance(result, Left):
            failed += 1
            errors.append(result.error)
            _progress_notify(on_progress, item.path, False, done, total_items)
        else:
            enriched += 1
            _progress_notify(on_progress, item.path, True, done, total_items)
    return right(EnrichReport(enriched=enriched, failed=failed, skipped=0, errors=tuple(errors)))
