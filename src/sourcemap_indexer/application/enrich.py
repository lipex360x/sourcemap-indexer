from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sourcemap_indexer.domain.repository import ItemRepository
from sourcemap_indexer.domain.value_objects import Language, Layer, Stability
from sourcemap_indexer.infra.llm_client import EnrichmentResult
from sourcemap_indexer.lib.either import Either, Left, right


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
    enriched = 0
    failed = 0
    errors: list[str] = []
    now = int(time.time())
    done = 0

    for item in pending:
        file_path = root / item.path
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            failed += 1
            done += 1
            errors.append(f"read-error: {item.path}")
            if on_progress:
                on_progress(item.path, False, done, total_items)
            continue

        if item.size_bytes == 0:
            stub = item.with_llm_enrichment(
                purpose="Empty file",
                layer=Layer.UNKNOWN,
                stability=Stability.UNKNOWN,
                tags=frozenset({"empty-file"}),
                side_effects=frozenset(),
                invariants=(),
                llm_at=now,
            )
            upsert_result = repository.upsert(stub)
            if isinstance(upsert_result, Left):
                failed += 1
                done += 1
                errors.append(f"{upsert_result.error}: {item.path}")
                if on_progress:
                    on_progress(item.path, False, done, total_items)
                continue
            enriched += 1
            done += 1
            if on_progress:
                on_progress(item.path, True, done, total_items)
            continue

        enrich_result = client.enrich(item.path, item.language, content, extra_instruction)
        if isinstance(enrich_result, Left):
            failed += 1
            done += 1
            errors.append(f"{enrich_result.error}: {item.path}")
            if on_progress:
                on_progress(item.path, False, done, total_items)
            continue

        result_data = enrich_result.value
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
            failed += 1
            done += 1
            errors.append(f"{upsert_result.error}: {item.path}")
            if on_progress:
                on_progress(item.path, False, done, total_items)
            continue
        enriched += 1
        done += 1
        if on_progress:
            on_progress(item.path, True, done, total_items)

    return right(EnrichReport(enriched=enriched, failed=failed, skipped=0, errors=tuple(errors)))
