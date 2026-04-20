from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

from sourcemap_indexer.domain.value_objects import (
    _DEFAULT_LAYERS,
    Language,
    Layer,
    SideEffect,
    Stability,
)
from sourcemap_indexer.lib.either import Either, Right, left, right
from sourcemap_indexer.lib.llm_log import LlmLog


def build_system_prompt(valid_layers: frozenset[str]) -> str:
    layers_str = " | ".join(sorted(valid_layers))
    return (
        "You are a code analyser. You receive a source file and return ONLY valid JSON, "
        "no markdown fence, no extra text, no comments. The JSON follows THIS exact schema:\n\n"
        '{"purpose": "string — 1 to 2 sentences in English describing WHAT the file does '
        'and WHY it exists. No implementation details.", '
        '"tags": ["array of 3 to 7 kebab-case strings — semantic concepts, '
        'not obvious technologies"], '
        f'"layer": "one of: {layers_str}", '
        '"stability": "one of: core | stable | experimental | deprecated | unknown", '
        '"side_effects": '
        '["zero or more of: writes_fs | spawns_process | network | git | environ"], '
        '"invariants": ["zero to three short strings — critical constraints"]}\n\n'
        "Hard rules:\n"
        "- Reply with ONLY the JSON object. Zero text before or after.\n"
        '- If unsure about a field, use "unknown" (enums) or empty array.\n'
        "- Never include credentials or absolute paths in purpose/tags."
    )


SYSTEM_PROMPT = build_system_prompt(_DEFAULT_LAYERS)

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
    json_mode: bool = True


@dataclass(frozen=True)
class EnrichmentResult:
    purpose: str
    tags: frozenset[str]
    layer: Layer
    stability: Stability
    side_effects: frozenset[SideEffect]
    invariants: tuple[str, ...]


def is_llm_configured() -> bool:
    return "SOURCEMAP_LLM_URL" in os.environ and "SOURCEMAP_LLM_MODEL" in os.environ


def from_environ() -> LlmConfig:
    json_mode_val = os.environ.get("SOURCEMAP_LLM_JSON_MODE", "1")
    return LlmConfig(
        url=os.environ["SOURCEMAP_LLM_URL"],
        model=os.environ["SOURCEMAP_LLM_MODEL"],
        api_key=os.environ.get("SOURCEMAP_LLM_API_KEY", LlmConfig.api_key),
        json_mode=json_mode_val != "0",
    )


def _truncate(content: str, max_chars: int) -> str:
    if len(content) <= max_chars:
        return content
    head = round(max_chars * 2 / 3)
    tail = max_chars - head
    skipped = len(content) - head - tail
    return content[:head] + f"\n... [truncated {skipped} chars] ...\n" + content[-tail:]


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

    layer: Layer = str(data.get("layer", "unknown"))

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


class LlmClient:
    def __init__(
        self,
        config: LlmConfig,
        http_client: httpx.Client | None = None,
        llm_log: LlmLog | None = None,
        system_prompt: str | None = None,
        valid_layers: frozenset[str] | None = None,
    ) -> None:
        self._config = config
        self._http = http_client or httpx.Client(timeout=config.timeout_seconds)
        self._llm_log = llm_log
        if system_prompt is not None:
            self._system_prompt = system_prompt
        elif valid_layers is not None:
            self._system_prompt = build_system_prompt(valid_layers)
        else:
            self._system_prompt = SYSTEM_PROMPT

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
        content = _truncate(content, self._config.max_chars)
        system = self._system_prompt
        if extra_instruction:
            system = system + f"\n\nAdditional instruction: {extra_instruction}"
        lang_str = str(language)
        user_prompt = f"Path: {path}\nLanguage: {language}\n\n```{lang_str}\n{content}\n```"
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        body: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        if self._config.json_mode:
            body["response_format"] = {"type": "json_object"}

        def _log(result: str, response_raw: str = "", finish_reason: str = "") -> None:
            if self._llm_log is not None:
                self._llm_log.record(
                    path=path,
                    language=str(language),
                    model=self._config.model,
                    messages=messages,
                    response_raw=response_raw,
                    result=result,
                    finish_reason=finish_reason,
                )

        for attempt in range(2):
            try:
                response = self._http.post(
                    self._config.url, json=body, headers=self._auth_headers()
                )
            except httpx.TimeoutException:
                _log("llm-timeout")
                return left("llm-timeout")
            except httpx.RequestError as error:
                result_code = f"llm-request-error: {error}"
                _log(result_code)
                return left(result_code)

            if response.status_code != 200:
                result_code = f"llm-http-error: {response.status_code}"
                _log(result_code)
                return left(result_code)

            try:
                choice = response.json()["choices"][0]
                raw = choice["message"]["content"]
                finish_reason = str(choice.get("finish_reason", ""))
            except (KeyError, IndexError, json.JSONDecodeError):
                _log("llm-parse-error")
                return left("llm-parse-error")

            parsed = _parse_enrichment(raw)
            if isinstance(parsed, Right):
                _log("ok", raw, finish_reason)
                return parsed
            if attempt == 0:
                continue
            _log(parsed.error, raw, finish_reason)
            return parsed

        _log("llm-parse-error")
        return left("llm-parse-error")
