"""
log.py — structured logger for Pi Python scripts.

Mirrors the contract of src/extensions/logger/index.ts:
    logger = create_logger("my-script")
    logger.info("started")
    logger.warn("something odd")
    logger.error("fatal")
    logger.debug("verbose — only with DEBUG=1")
    logger.clear()

Environment:
    NO_LOG_FILE=1   suppress all file I/O (use in tests / pre-commit)
    DEBUG=1         write DEBUG lines + echo every line to stderr
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


class Logger(Protocol):
    def info(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def clear(self) -> None: ...


@dataclass
class _NoopLogger:
    def info(self, message: str) -> None:
        pass

    def warn(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass

    def debug(self, message: str) -> None:
        pass

    def clear(self) -> None:
        pass


@dataclass
class _FileLogger:
    name: str
    log_path: Path
    debug_enabled: bool

    def _write(self, level: str, message: str) -> None:
        timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} [{level:<5}] [{self.name}] {message}\n"
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(line)
            if self.debug_enabled:
                import sys

                sys.stderr.write(line)
        except OSError:
            pass

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def debug(self, message: str) -> None:
        if self.debug_enabled:
            self._write("DEBUG", message)

    def clear(self) -> None:
        try:
            if self.log_path.exists():
                self.log_path.unlink()
        except OSError:
            pass


def _find_git_root() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return str(Path.cwd())


def create_logger(
    name: str,
    *,
    log_dir: str | None = None,
    environ: dict[str, str] | None = None,
) -> Logger:
    """
    Create a logger for a Python script.

    Args:
        name:    module/script name — used as filename (<name>.log) and log tag
        log_dir: override log directory (default: <git-root>/.logs/scripts/)
        environ: environment dict override (default: os.environ) — useful in tests
    """
    resolved_env = environ if environ is not None else dict(os.environ)

    if resolved_env.get("NO_LOG_FILE") == "1":
        return _NoopLogger()

    debug_enabled = resolved_env.get("DEBUG") == "1"

    if log_dir is not None:
        resolved_dir = Path(log_dir)
    else:
        resolved_dir = Path(_find_git_root()) / ".logs" / "scripts"

    log_path = resolved_dir / f"{name}.log"
    logger = _FileLogger(name=name, log_path=log_path, debug_enabled=debug_enabled)
    logger.info("=== start ===")
    return logger
