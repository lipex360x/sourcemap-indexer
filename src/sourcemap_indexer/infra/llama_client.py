from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from sourcemap_indexer.domain.value_objects import Language, Layer, SideEffect, Stability
from sourcemap_indexer.lib.either import Either, left, right

_SYSTEM_PROMPT = (
    "Você é um analisador de código. Recebe um arquivo e devolve APENAS JSON válido, "
    "sem markdown fence, sem texto extra, sem comentários. O JSON segue ESTE schema exato:\n\n"
    '{"purpose": "string — 1 a 2 frases em português BR descrevendo O QUE o arquivo faz e '
    'POR QUÊ existe. Sem detalhe de implementação.", '
    '"tags": ["array de 3 a 7 strings kebab-case — conceitos semânticos, não tecnologias óbvias"], '
    '"layer": "domain | infra | application | cli | hook | lib | config | doc | test | unknown", '
    '"stability": "um de: core | stable | experimental | deprecated | unknown", '
    '"side_effects": ["zero ou mais de: writes_fs | spawns_process | network | git | environ"], '
    '"invariants": ["zero a três strings curtas — constraints críticas"]}\n\n'
    "Regras duras:\n"
    "- Responda APENAS o objeto JSON. Zero texto antes ou depois.\n"
    '- Se não souber um campo, use "unknown" (enums) ou array vazio.\n'
    "- Nunca inclua credentials ou paths absolutos em purpose/tags."
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class LlmConfig:
    url: str = "http://localhost:1234/v1/chat/completions"
    model: str = "qwen/qwen3-coder-30b"
    temperature: float = 0.1
    max_tokens: int = 800
    timeout_seconds: float = 60.0
    max_chars: int = 8000


@dataclass(frozen=True)
class EnrichmentResult:
    purpose: str
    tags: frozenset[str]
    layer: Layer
    stability: Stability
    side_effects: frozenset[SideEffect]
    invariants: tuple[str, ...]


def from_environ() -> LlmConfig:
    return LlmConfig(
        url=os.environ.get("SOURCEMAP_LLM_URL", LlmConfig.url),
        model=os.environ.get("SOURCEMAP_LLM_MODEL", LlmConfig.model),
    )


def _parse_enrichment(raw: str) -> Either[str, EnrichmentResult]:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.startswith("```")).strip()
    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            return left("llm-parse-error")
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return left("llm-parse-error")

    try:
        layer = Layer(data.get("layer", "unknown"))
    except ValueError:
        layer = Layer.UNKNOWN

    try:
        stability = Stability(data.get("stability", "unknown"))
    except ValueError:
        stability = Stability.UNKNOWN

    side_effects: frozenset[SideEffect] = frozenset()
    for effect in data.get("side_effects", []):
        with contextlib.suppress(ValueError):
            side_effects = side_effects | {SideEffect(effect)}

    return right(
        EnrichmentResult(
            purpose=str(data.get("purpose", "")),
            tags=frozenset(str(t) for t in data.get("tags", [])),
            layer=layer,
            stability=stability,
            side_effects=side_effects,
            invariants=tuple(str(i) for i in data.get("invariants", [])),
        )
    )


class LlamaClient:
    def __init__(self, config: LlmConfig, http_client: httpx.Client | None = None) -> None:
        self._config = config
        self._http = http_client or httpx.Client(timeout=config.timeout_seconds)

    def enrich(self, path: str, language: Language, content: str) -> Either[str, EnrichmentResult]:
        if len(content) > self._config.max_chars:
            content = content[: self._config.max_chars]
        user_prompt = f"Path: {path}\nLanguage: {language}\n\n---\n{content}"
        body = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        try:
            response = self._http.post(self._config.url, json=body)
        except httpx.TimeoutException:
            return left("llm-timeout")
        except httpx.RequestError as error:
            return left(f"llm-request-error: {error}")

        if response.status_code != 200:
            return left(f"llm-http-error: {response.status_code}")

        try:
            raw = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError):
            return left("llm-parse-error")

        return _parse_enrichment(raw)
