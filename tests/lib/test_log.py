from __future__ import annotations

from pathlib import Path

import pytest

from sourcemap_indexer.lib.log import create_logger


def test_create_logger_without_flag_returns_noop_logger(tmp_path: Path) -> None:
    logger = create_logger("test", log_dir=str(tmp_path), environ={})
    logger.info("ignored")
    logger.warn("ignored")
    logger.error("ignored")
    logger.debug("ignored")
    logger.clear()
    assert not any(tmp_path.iterdir())


def test_create_logger_with_flag_returns_file_logger(tmp_path: Path) -> None:
    logger = create_logger(
        "mymodule",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1"},
    )
    logger.info("hello")
    log_file = tmp_path / "mymodule.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "hello" in content
    assert "INFO" in content


def test_create_logger_writes_start_marker(tmp_path: Path) -> None:
    create_logger(
        "start_test",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1"},
    )
    log_file = tmp_path / "start_test.log"
    content = log_file.read_text(encoding="utf-8")
    assert "=== start ===" in content


def test_create_logger_debug_disabled_by_default(tmp_path: Path) -> None:
    logger = create_logger(
        "debug_test",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1"},
    )
    logger.clear()
    logger.debug("should not appear")
    log_file = tmp_path / "debug_test.log"
    assert not log_file.exists()


def test_create_logger_debug_enabled_with_env(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = create_logger(
        "debug_enabled",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1", "SOURCEMAP_DEBUG": "1"},
    )
    logger.clear()
    logger.debug("debug message here")
    log_file = tmp_path / "debug_enabled.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "debug message here" in content
    assert "DEBUG" in content


def test_create_logger_clear_removes_log_file(tmp_path: Path) -> None:
    logger = create_logger(
        "clearable",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1"},
    )
    log_file = tmp_path / "clearable.log"
    assert log_file.exists()
    logger.clear()
    assert not log_file.exists()


def test_create_logger_warn_writes_warn_level(tmp_path: Path) -> None:
    logger = create_logger(
        "warn_test",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1"},
    )
    logger.clear()
    logger.warn("watch out")
    log_file = tmp_path / "warn_test.log"
    content = log_file.read_text(encoding="utf-8")
    assert "WARN" in content
    assert "watch out" in content


def test_create_logger_error_writes_error_level(tmp_path: Path) -> None:
    logger = create_logger(
        "error_test",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1"},
    )
    logger.clear()
    logger.error("fatal issue")
    log_file = tmp_path / "error_test.log"
    content = log_file.read_text(encoding="utf-8")
    assert "ERROR" in content
    assert "fatal issue" in content


def test_create_logger_uses_os_environ_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SOURCEMAP_LOG_FILE", "1")
    logger = create_logger("env_test", log_dir=str(tmp_path))
    logger.info("from os.environ")
    log_file = tmp_path / "env_test.log"
    assert log_file.exists()


def test_create_logger_debug_writes_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = create_logger(
        "stderr_test",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1", "SOURCEMAP_DEBUG": "1"},
    )
    logger.clear()
    logger.info("echoed to stderr")
    captured = capsys.readouterr()
    assert "echoed to stderr" in captured.err


def test_file_logger_clear_noop_when_file_absent(tmp_path: Path) -> None:
    logger = create_logger(
        "absent_clear",
        log_dir=str(tmp_path),
        environ={"SOURCEMAP_LOG_FILE": "1"},
    )
    log_file = tmp_path / "absent_clear.log"
    log_file.unlink()
    logger.clear()
