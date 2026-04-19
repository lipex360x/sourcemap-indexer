from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sourcemap_indexer.domain.repository import ItemRepository
from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.llama_client import EnrichmentResult
from sourcemap_indexer.lib.either import Either, Left, right


class _EnrichClient(Protocol):
    def enrich(
        self, path: str, language: Language, content: str
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
) -> Either[str, EnrichReport]:
    items_result = repository.find_needs_llm(limit=batch_limit)
    if isinstance(items_result, Left):
        return items_result

    enriched = 0
    failed = 0
    errors: list[str] = []
    now = int(time.time())

    for item in items_result.value:
        file_path = root / item.path
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            failed += 1
            errors.append(f"read-error: {item.path}")
            continue

        enrich_result = client.enrich(item.path, item.language, content)
        if isinstance(enrich_result, Left):
            failed += 1
            errors.append(f"{enrich_result.error}: {item.path}")
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
            errors.append(f"{upsert_result.error}: {item.path}")
            continue
        enriched += 1

    return right(EnrichReport(enriched=enriched, failed=failed, skipped=0, errors=tuple(errors)))
