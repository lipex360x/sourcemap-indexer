from __future__ import annotations

import json
import shutil
import subprocess

from sourcemap_indexer.config import llm_cli_model
from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.llm_client import EnrichmentResult, _parse_enrichment
from sourcemap_indexer.lib.either import Either, left


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


def _build_cmd(prompt: str) -> list[str]:
    model = llm_cli_model()
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    return cmd


class ClaudeCliProvider:
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
                _build_cmd(prompt),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            return left(f"claude-cli-error: {exc.returncode}")
        try:
            wrapper = json.loads(proc.stdout)
            raw = wrapper["result"]
        except (json.JSONDecodeError, KeyError):
            return left("claude-cli-parse-error")
        return _parse_enrichment(raw)
