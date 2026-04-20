from __future__ import annotations

from pathlib import Path

import yaml

from sourcemap_indexer.lib.llm_log import LlmLog, create_llm_log

_ENV = {}

_RECORD_KWARGS = {
    "path": "src/auth.py",
    "language": "py",
    "model": "my-model",
    "messages": [
        {"role": "system", "content": "You are a code analyser."},
        {"role": "user", "content": "Path: src/auth.py\n\ndef verify(): ..."},
    ],
    "response_raw": '{"purpose": "Validates JWT tokens"}',
    "result": "ok",
}


def test_create_llm_log_returns_noop_when_no_log_file(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ={"NO_LOG_FILE": "1"})
    log.record(**_RECORD_KWARGS)
    assert not (tmp_path / "llm.yaml").exists()


def test_record_creates_yaml_file(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    log.record(**_RECORD_KWARGS)
    assert (tmp_path / "llm.yaml").exists()


def test_record_yaml_contains_metadata(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    log.record(**_RECORD_KWARGS)
    content = (tmp_path / "llm.yaml").read_text()
    assert "src/auth.py" in content
    assert "my-model" in content
    assert "ok" in content


def test_record_yaml_contains_messages(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    log.record(**_RECORD_KWARGS)
    content = (tmp_path / "llm.yaml").read_text()
    assert "code analyser" in content
    assert "verify" in content


def test_record_yaml_contains_response(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    log.record(**_RECORD_KWARGS)
    content = (tmp_path / "llm.yaml").read_text()
    assert "Validates JWT tokens" in content


def test_multiple_records_all_present(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    log.record(**{**_RECORD_KWARGS, "path": "a.py"})
    log.record(**{**_RECORD_KWARGS, "path": "b.py"})
    content = (tmp_path / "llm.yaml").read_text()
    assert "a.py" in content
    assert "b.py" in content


def test_multiple_records_are_valid_yaml_documents(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    log.record(**{**_RECORD_KWARGS, "path": "a.py"})
    log.record(**{**_RECORD_KWARGS, "path": "b.py"})
    raw = (tmp_path / "llm.yaml").read_text()
    docs = list(yaml.safe_load_all(raw))
    assert len(docs) == 2
    assert docs[0]["path"] == "a.py"
    assert docs[1]["path"] == "b.py"


def test_record_error_result(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    log.record(**{**_RECORD_KWARGS, "response_raw": "", "result": "llm-timeout"})
    content = (tmp_path / "llm.yaml").read_text()
    assert "llm-timeout" in content


def test_record_creates_parent_dir_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "logs"
    log = create_llm_log(nested, environ=_ENV)
    log.record(**_RECORD_KWARGS)
    assert (nested / "llm.yaml").exists()


def test_noop_log_has_record_method() -> None:
    log = create_llm_log(Path("/unused"), environ={"NO_LOG_FILE": "1"})
    assert callable(getattr(log, "record", None))


def test_llm_log_is_runtime_checkable(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_ENV)
    assert isinstance(log, LlmLog)
