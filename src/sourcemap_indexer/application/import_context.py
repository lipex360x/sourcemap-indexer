from __future__ import annotations

from sourcemap_indexer.domain.entities import Item
from sourcemap_indexer.domain.repository import ItemRepository
from sourcemap_indexer.infra.import_extractor import _EXTRACTORS
from sourcemap_indexer.lib.either import Left


def _collect_lines(paths: list[str], repo: ItemRepository) -> list[str]:
    lines: list[str] = []
    for path in paths:
        found = repo.find_by_path(path)
        if isinstance(found, Left):
            continue
        candidate = found.value
        if candidate is None or candidate.purpose is None:
            continue
        lines.append(f"- {path}: {candidate.purpose}")
    return lines


def _apply_budget(lines: list[str], header: str, max_chars: int) -> list[str]:
    budget = max_chars - len(header) - 1
    kept: list[str] = []
    used = 0
    for line in lines:
        cost = len(line) + 1
        if used + cost > budget:
            break
        kept.append(line)
        used += cost
    return kept


def resolve_import_context(item: Item, content: str, repo: ItemRepository, max_chars: int) -> str:
    extract_fn = _EXTRACTORS.get(item.language)
    if extract_fn is None:
        return ""
    paths = extract_fn(content, item.path)
    if not paths:
        return ""
    lines = _collect_lines(paths, repo)
    if not lines:
        return ""
    header = "Context from direct imports:"
    kept = _apply_budget(lines, header, max_chars)
    if not kept:
        return ""
    return header + "\n" + "\n".join(kept)
