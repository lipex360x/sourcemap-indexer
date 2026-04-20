from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml


@runtime_checkable
class LlmLog(Protocol):
    def record(
        self,
        *,
        path: str,
        language: str,
        model: str,
        messages: list[dict[str, str]],
        response_raw: str,
        result: str,
    ) -> None: ...


@dataclass
class _NoopLlmLog:
    def record(
        self,
        *,
        path: str,
        language: str,
        model: str,
        messages: list[dict[str, str]],
        response_raw: str,
        result: str,
    ) -> None:
        pass


@dataclass
class _FileLlmLog:
    _log_path: Path

    def record(
        self,
        *,
        path: str,
        language: str,
        model: str,
        messages: list[dict[str, str]],
        response_raw: str,
        result: str,
    ) -> None:
        entry = {
            "timestamp": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "path": path,
            "language": language,
            "model": model,
            "result": result,
            "request": {"messages": messages},
            "response": response_raw or None,
        }
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as log_file:
                yaml.dump(
                    entry,
                    log_file,
                    allow_unicode=True,
                    default_flow_style=False,
                    explicit_start=True,
                    sort_keys=False,
                )
        except OSError:
            pass


def create_llm_log(
    log_dir: Path,
    *,
    environ: dict[str, str] | None = None,
) -> LlmLog:
    resolved_env = environ if environ is not None else dict(os.environ)
    if resolved_env.get("NO_LOG_FILE") == "1":
        return _NoopLlmLog()
    return _FileLlmLog(log_dir / "llm.yaml")
