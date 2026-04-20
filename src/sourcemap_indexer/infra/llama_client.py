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
    "You are a code analyser. You receive a source file and return ONLY valid JSON, "
    "no markdown fence, no extra text, no comments. The JSON follows THIS exact schema:\n\n"
    '{"purpose": "string — 1 to 2 sentences in English describing WHAT the file does and '
    'WHY it exists. No implementation details.", '
    '"tags": ["array of 3 to 7 kebab-case strings — semantic concepts, not obvious technologies"], '
    '"layer": "domain | infra | application | cli | hook | lib | config | doc | test | unknown", '
    '"stability": "one of: core | stable | experimental | deprecated | unknown", '
    '"side_effects": ["zero or more of: writes_fs | spawns_process | network | git | environ"], '
    '"invariants": ["zero to three short strings — critical constraints"]}\n\n'
    "Hard rules:\n"
    "- Reply with ONLY the JSON object. Zero text before or after.\n"
    '- If unsure about a field, use "unknown" (enums) or empty array.\n'
    "- Never include credentials or absolute paths in purpose/tags."
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
    api_key: str = ""


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
        api_key=os.environ.get("SOURCEMAP_LLM_API_KEY", LlmConfig.api_key),
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

    def _auth_headers(self) -> dict[str, str]:
        if self._config.api_key:
            return {"Authorization": f"Bearer {self._config.api_key}"}
        return {}

    def ping(self) -> Either[str, None]:
        base = self._config.url.split("/v1/")[0]
        try:
            self._http.get(f"{base}/v1/models", timeout=5.0, headers=self._auth_headers())
        except httpx.RequestError as error:
            return left(f"llm-unreachable: {error}")
        return right(None)

    def enrich(
        self,
        path: str,
        language: Language,
        content: str,
        extra_instruction: str | None = None,
    ) -> Either[str, EnrichmentResult]:
        if len(content) > self._config.max_chars:
            content = content[: self._config.max_chars]
        system = _SYSTEM_PROMPT
        if extra_instruction:
            system = system + f"\n\nAdditional instruction: {extra_instruction}"
        user_prompt = f"Path: {path}\nLanguage: {language}\n\n---\n{content}"
        body = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        try:
            response = self._http.post(self._config.url, json=body, headers=self._auth_headers())
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
