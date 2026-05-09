from __future__ import annotations

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
from sourcemap_indexer.lib.either import Either, Left, left
from sourcemap_indexer.lib.llm_log import LlmLog


def _build_prompt(
    system_prompt: str,
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
    return f"{system_prompt}\n\n---\n\n{user}"


def _build_cmd(prompt: str) -> list[str]:
    cmd = ["opencode", "run", prompt]
    model = llm_cli_model()
    if model:
        cmd += ["-m", model]
    return cmd


class OpenCodeProvider:
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
                model=llm_cli_model() or "opencode",
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
        import_context: str | None = None,
    ) -> Either[str, EnrichmentResult]:
        if not shutil.which("opencode"):
            return left("opencode-not-configured")
        prompt = _build_prompt(
            self._system_prompt, path, language, content, extra_instruction, import_context
        )
        try:
            proc = subprocess.run(
                _build_cmd(prompt),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            error = f"opencode-error: {exc.returncode}"
            self._log(path, language, error)
            return left(error)
        parsed = _parse_enrichment(proc.stdout.strip())
        result_label = "ok" if not isinstance(parsed, Left) else parsed.error
        self._log(path, language, result_label, proc.stdout.strip())
        return parsed
