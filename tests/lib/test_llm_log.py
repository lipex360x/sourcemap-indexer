from __future__ import annotations

from pathlib import Path

import yaml

from sourcemap_indexer.lib.llm_log import LlmLog, create_llm_log

_LOG_ON = {"SOURCEMAP_LLM_LOG": "1"}

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
    "finish_reason": "stop",
}


def test_create_llm_log_returns_noop_by_default(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ={})
    log.record(**_RECORD_KWARGS)
    assert not list(tmp_path.glob("llm-*.yaml"))


def test_create_llm_log_returns_noop_when_env_absent(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ={"OTHER_VAR": "1"})
    log.record(**_RECORD_KWARGS)
    assert not list(tmp_path.glob("llm-*.yaml"))


def test_record_creates_timestamped_yaml_file(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    log.record(**_RECORD_KWARGS)
    files = list(tmp_path.glob("llm-*.yaml"))
    assert len(files) == 1


def test_each_session_produces_separate_file(tmp_path: Path) -> None:
    log1 = create_llm_log(tmp_path, environ=_LOG_ON)
    log2 = create_llm_log(tmp_path, environ=_LOG_ON)
    log1.record(**{**_RECORD_KWARGS, "path": "a.py"})
    log2.record(**{**_RECORD_KWARGS, "path": "b.py"})
    files = list(tmp_path.glob("llm-*.yaml"))
    assert len(files) == 2
    combined = "".join(f.read_text() for f in files)
    assert "a.py" in combined
    assert "b.py" in combined


def test_multiple_records_in_same_session_share_one_file(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    log.record(**{**_RECORD_KWARGS, "path": "a.py"})
    log.record(**{**_RECORD_KWARGS, "path": "b.py"})
    files = list(tmp_path.glob("llm-*.yaml"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "a.py" in content
    assert "b.py" in content


def test_record_yaml_contains_metadata(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    log.record(**_RECORD_KWARGS)
    content = next(tmp_path.glob("llm-*.yaml")).read_text()
    assert "src/auth.py" in content
    assert "my-model" in content
    assert "ok" in content


def test_record_yaml_contains_messages(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    log.record(**_RECORD_KWARGS)
    content = next(tmp_path.glob("llm-*.yaml")).read_text()
    assert "code analyser" in content
    assert "verify" in content


def test_record_yaml_contains_response(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    log.record(**_RECORD_KWARGS)
    content = next(tmp_path.glob("llm-*.yaml")).read_text()
    assert "Validates JWT tokens" in content


def test_records_are_valid_yaml_documents(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    log.record(**{**_RECORD_KWARGS, "path": "a.py"})
    log.record(**{**_RECORD_KWARGS, "path": "b.py"})
    raw = next(tmp_path.glob("llm-*.yaml")).read_text()
    docs = list(yaml.safe_load_all(raw))
    assert len(docs) == 2
    assert docs[0]["path"] == "a.py"
    assert docs[1]["path"] == "b.py"


def test_record_error_result(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    log.record(**{**_RECORD_KWARGS, "response_raw": "", "result": "llm-timeout"})
    content = next(tmp_path.glob("llm-*.yaml")).read_text()
    assert "llm-timeout" in content


def test_record_creates_parent_dir_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "logs"
    log = create_llm_log(nested, environ=_LOG_ON)
    log.record(**_RECORD_KWARGS)
    assert list(nested.glob("llm-*.yaml"))


def test_noop_log_has_record_method() -> None:
    log = create_llm_log(Path("/unused"), environ={})
    assert callable(getattr(log, "record", None))


def test_llm_log_is_runtime_checkable(tmp_path: Path) -> None:
    log = create_llm_log(tmp_path, environ=_LOG_ON)
    assert isinstance(log, LlmLog)
