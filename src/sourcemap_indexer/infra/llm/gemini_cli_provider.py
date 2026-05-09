from __future__ import annotations

import json
import shutil
import subprocess

from sourcemap_indexer.config import llm_cli_model
from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.llm.llm_client import (
    SYSTEM_PROMPT,
    EnrichmentResult,
    _parse_enrichment,
    build_system_prompt,
)
from sourcemap_indexer.lib.either import Either, Left, Right, left, right
from sourcemap_indexer.lib.llm_log import LlmLog

_QUOTA_MARKER = "exhausted your capacity"


def _build_user_prompt(
    path: str,
    language: Language,
    content: str,
    extra_instruction: str | None,
    import_context: str | None,
) -> str:
    lang_str = str(language)
    content = content.replace("\x00", "")
    user = f"Path: {path}\nLanguage: {language}\n\n```{lang_str}\n{content}\n```"
    if extra_instruction:
        user += f"\n\nAdditional instruction: {extra_instruction}"
    if import_context:
        user += f"\n\n{import_context}"
    return user


def _build_cmd(prompt: str) -> list[str]:
    cmd = ["gemini", "--skip-trust", "-o", "json", "-p", prompt]
    model = llm_cli_model()
    if model:
        cmd += ["-m", model]
    return cmd


def _extract_response(stdout: str) -> Either[str, str]:
    try:
        wrapper = json.loads(stdout)
        return right(wrapper["response"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return left("gemini-cli-parse-error")


class GeminiCliProvider:
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

    def _log(self, path: str, language: Language, result: str, raw: str = "") -> None:
        if self._llm_log is not None:
            self._llm_log.record(
                path=path,
                language=str(language),
                model=llm_cli_model() or "gemini-cli",
                response_raw=raw,
                result=result,
                finish_reason="",
            )

    def _check_proc_failure(
        self, path: str, language: Language, proc: subprocess.CompletedProcess[str]
    ) -> Either[str, None]:
        stderr = proc.stderr or ""
        if _QUOTA_MARKER in stderr:
            self._log(path, language, "gemini-cli-quota-exhausted", stderr)
            return left("gemini-cli-quota-exhausted")
        if proc.returncode != 0:
            error = f"gemini-cli-error: {proc.returncode}"
            self._log(path, language, error, stderr or proc.stdout)
            return left(error)
        return right(None)

    def enrich(
        self,
        path: str,
        language: Language,
        content: str,
        extra_instruction: str | None = None,
        import_context: str | None = None,
    ) -> Either[str, EnrichmentResult]:
        if not shutil.which("gemini"):
            return left("gemini-cli-not-configured")
        full_prompt = (
            f"{self._system_prompt}\n\n---\n\n"
            f"{_build_user_prompt(path, language, content, extra_instruction, import_context)}"
        )
        proc = subprocess.run(
            _build_cmd(full_prompt),
            capture_output=True,
            text=True,
            check=False,
        )
        failure = self._check_proc_failure(path, language, proc)
        if isinstance(failure, Left):
            return left(failure.error)
        extracted = _extract_response(proc.stdout)
        if not isinstance(extracted, Right):
            self._log(path, language, extracted.error, proc.stdout)
            return left(extracted.error)
        raw = extracted.value
        parsed = _parse_enrichment(raw)
        result_label = "ok" if not isinstance(parsed, Left) else parsed.error
        self._log(path, language, result_label, raw)
        return parsed
