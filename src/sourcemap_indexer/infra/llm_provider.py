from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.llm_client import EnrichmentResult
from sourcemap_indexer.lib.either import Either, left, right


@runtime_checkable
class LLMProvider(Protocol):
    def enrich(
        self,
        path: str,
        language: Language,
        content: str,
        extra_instruction: str | None = None,
    ) -> Either[str, EnrichmentResult]: ...


def _make_http() -> LLMProvider:
    from sourcemap_indexer.infra.llm_client import HttpLLMProvider, from_environ  # noqa: PLC0415

    return HttpLLMProvider(from_environ())


def _make_claude_cli(
    llm_log: Any = None,
    system_prompt: Any = None,
    valid_layers: Any = None,
) -> LLMProvider:
    from sourcemap_indexer.infra.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    return ClaudeCliProvider(
        llm_log=llm_log, system_prompt=system_prompt, valid_layers=valid_layers
    )


_PROVIDERS: dict[str, Any] = {
    "http": _make_http,
    "claude-cli": _make_claude_cli,
}


def resolve_provider(name: str) -> Either[str, Any]:
    factory = _PROVIDERS.get(name)
    if factory is None:
        return left("unknown-provider")
    return right(factory)
