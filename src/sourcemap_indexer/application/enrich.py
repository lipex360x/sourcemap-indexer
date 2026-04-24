from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sourcemap_indexer.application.import_context import resolve_import_context
from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.repository import ItemRepository
from sourcemap_indexer.domain.value_objects import _DEFAULT_LAYERS, Language, Layer, Stability
from sourcemap_indexer.infra.llm.llm_client import EnrichmentResult
from sourcemap_indexer.infra.parser.import_extractor import _EXTRACTORS
from sourcemap_indexer.lib.either import Either, Left, left, right

_CONTEXT_MAX_CHARS = 2000


def _item_deps(
    item: Item,
    extractors: dict[Language, Callable[[str, str], list[str]]],
    pending_paths: set[str],
    root: Path,
) -> list[str]:
    extractor = extractors.get(item.language)
    if extractor is None:
        return []
    try:
        content = (root / item.path).read_text(encoding="utf-8", errors="replace")
        paths = extractor(content, item.path)
    except (OSError, SyntaxError):
        return []
    return [dep for dep in paths if dep in pending_paths]


def _build_dep_graph(
    items: list[Item],
    extractors: dict[Language, Callable[[str, str], list[str]]],
    root: Path,
) -> tuple[dict[str, int], dict[str, list[str]]]:
    pending_paths = {item.path for item in items}
    in_degree: dict[str, int] = {item.path: 0 for item in items}
    dependents: dict[str, list[str]] = {item.path: [] for item in items}
    for item in items:
        for dep_path in _item_deps(item, extractors, pending_paths, root):
            in_degree[item.path] += 1
            dependents[dep_path].append(item.path)
    return in_degree, dependents


def _kahn_bfs(
    items: list[Item],
    path_to_item: dict[str, Item],
    in_degree: dict[str, int],
    dependents: dict[str, list[str]],
) -> tuple[list[Item], set[str]]:
    queue = deque(item.path for item in items if in_degree[item.path] == 0)
    result: list[Item] = []
    seen: set[str] = set()
    while queue:
        path = queue.popleft()
        result.append(path_to_item[path])
        seen.add(path)
        for dependent_path in dependents[path]:
            in_degree[dependent_path] -= 1
            if in_degree[dependent_path] == 0:
                queue.append(dependent_path)
    return result, seen


def _topologically_ordered(
    items: list[Item],
    extractors: dict[Language, Callable[[str, str], list[str]]],
    root: Path,
) -> list[Item]:
    if not items:
        return []
    path_to_item = {item.path: item for item in items}
    in_degree, dependents = _build_dep_graph(items, extractors, root)
    result, seen = _kahn_bfs(items, path_to_item, in_degree, dependents)
    for item in items:
        if item.path not in seen:
            result.append(item)
    return result


class _EnrichClient(Protocol):
    def enrich(
        self,
        path: str,
        language: Language,
        content: str,
        extra_instruction: str | None = None,
        import_context: str | None = None,
    ) -> Either[str, EnrichmentResult]: ...


@dataclass(frozen=True)
class EnrichReport:
    enriched: int
    failed: int
    skipped: int
    errors: tuple[str, ...]
    layer_mismatches: tuple[tuple[str, str, str], ...] = ()


def _top_directory(path: str) -> str:
    head, sep, _ = path.partition("/")
    return head if sep else ""


def _detect_layer_mismatch(
    path: str, chosen_layer: str, custom_layers: frozenset[str]
) -> tuple[str, str, str] | None:
    if not custom_layers:
        return None
    top = _top_directory(path)
    if top in custom_layers and chosen_layer != top and chosen_layer in _DEFAULT_LAYERS:
        return (path, chosen_layer, top)
    return None


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
    import_context: str | None,
    now: int,
) -> Either[str, tuple[str, str, str] | None]:
    enrich_result = client.enrich(
        item.path, item.language, content, extra_instruction, import_context
    )
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
    custom_layers = valid_layers - _DEFAULT_LAYERS if valid_layers is not None else frozenset()
    return right(_detect_layer_mismatch(item.path, result_data.layer, custom_layers))


def _enrich_item(
    item: Item,
    root: Path,
    client: _EnrichClient,
    repository: ItemRepository,
    valid_layers: frozenset[str] | None,
    extra_instruction: str | None,
    now: int,
    with_context: bool = False,
) -> Either[str, tuple[str, str, str] | None]:
    try:
        content = (root / item.path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return left(f"read-error: {item.path}")
    if item.size_bytes == 0:
        empty_result = _handle_empty_file(item, repository, now)
        if isinstance(empty_result, Left):
            return empty_result
        return right(None)
    import_context = (
        resolve_import_context(item, content, repository, _CONTEXT_MAX_CHARS)
        if with_context
        else None
    )
    return _handle_normal_file(
        item, content, client, repository, valid_layers, extra_instruction, import_context, now
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
    with_context: bool = False,
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
    pending = _topologically_ordered(items_result.value, _EXTRACTORS, root)
    total_items = len(pending)
    enriched = failed = 0
    errors: list[str] = []
    mismatches: list[tuple[str, str, str]] = []
    now = int(time.time())
    for done, item in enumerate(pending, start=1):
        result = _enrich_item(
            item, root, client, repository, valid_layers, extra_instruction, now, with_context
        )
        if isinstance(result, Left):
            failed += 1
            errors.append(result.error)
            _progress_notify(on_progress, item.path, False, done, total_items)
        else:
            enriched += 1
            if result.value is not None:
                mismatches.append(result.value)
            _progress_notify(on_progress, item.path, True, done, total_items)
    return right(
        EnrichReport(
            enriched=enriched,
            failed=failed,
            skipped=0,
            errors=tuple(errors),
            layer_mismatches=tuple(mismatches),
        )
    )
