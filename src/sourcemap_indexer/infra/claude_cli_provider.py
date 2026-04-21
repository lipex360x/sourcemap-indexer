from __future__ import annotations

import json
import shutil
import subprocess

from sourcemap_indexer.config import llm_cli_effort, llm_cli_model
from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.llm_client import (
    SYSTEM_PROMPT,
    EnrichmentResult,
    _parse_enrichment,
    build_system_prompt,
)
from sourcemap_indexer.lib.either import Either, Left, left
from sourcemap_indexer.lib.llm_log import LlmLog


def _check_auth() -> None:
    subprocess.run(
        ["claude", "auth", "status"],
        capture_output=True,
        check=True,
    )


def _build_prompt(
    path: str, language: Language, content: str, extra_instruction: str | None
) -> str:
    lang_str = str(language)
    prompt = f"Path: {path}\nLanguage: {language}\n\n```{lang_str}\n{content}\n```"
    if extra_instruction:
        prompt += f"\n\nAdditional instruction: {extra_instruction}"
    return prompt


def _build_cmd(prompt: str, system_prompt: str) -> list[str]:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--system-prompt", system_prompt]
    model = llm_cli_model()
    if model:
        cmd += ["--model", model]
    effort = llm_cli_effort()
    if effort:
        cmd += ["--effort", effort]
    return cmd


class ClaudeCliProvider:
    def __init__(
        self,
        llm_log: LlmLog | None = None,
        system_prompt: str | None = None,
        valid_layers: frozenset[str] | None = None,
    ) -> None:
        self._llm_log = llm_log
        if system_prompt is not None:
            self._system_prompt = system_prompt
        elif valid_layers is not None:
            self._system_prompt = build_system_prompt(valid_layers)
        else:
            self._system_prompt = SYSTEM_PROMPT

    def _log(self, path: str, language: Language, prompt: str, result: str, raw: str = "") -> None:
        if self._llm_log is not None:
            self._llm_log.record(
                path=path,
                language=str(language),
                model=llm_cli_model() or "claude-cli",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_raw=raw,
                result=result,
                finish_reason="",
            )

    def enrich(
        self,
        path: str,
        language: Language,
        content: str,
        extra_instruction: str | None = None,
    ) -> Either[str, EnrichmentResult]:
        if not shutil.which("claude"):
            return left("claude-cli-not-configured")
        try:
            _check_auth()
        except subprocess.CalledProcessError:
            return left("claude-cli-auth-error")
        prompt = _build_prompt(path, language, content, extra_instruction)
        try:
            proc = subprocess.run(
                _build_cmd(prompt, self._system_prompt),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            error = f"claude-cli-error: {exc.returncode}"
            self._log(path, language, prompt, error)
            return left(error)
        try:
            wrapper = json.loads(proc.stdout)
            raw = wrapper["result"]
        except (json.JSONDecodeError, KeyError):
            self._log(path, language, prompt, "claude-cli-parse-error", proc.stdout)
            return left("claude-cli-parse-error")
        parsed = _parse_enrichment(raw)
        result_label = "ok" if not isinstance(parsed, Left) else parsed.error
        self._log(path, language, prompt, result_label, raw)
        return parsed
