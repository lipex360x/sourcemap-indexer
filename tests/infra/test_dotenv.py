from __future__ import annotations

import os
from pathlib import Path

import pytest

from sourcemap_indexer.infra.dotenv import load_dotenv


def test_loads_simple_key_value(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MY_VAR=hello\n")
    os.environ.pop("MY_VAR", None)
    load_dotenv(tmp_path / ".env")
    assert os.environ["MY_VAR"] == "hello"
    del os.environ["MY_VAR"]


def test_loads_quoted_values(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("KEY_DQ=\"double\"\nKEY_SQ='single'\n")
    os.environ.pop("KEY_DQ", None)
    os.environ.pop("KEY_SQ", None)
    load_dotenv(tmp_path / ".env")
    assert os.environ["KEY_DQ"] == "double"
    assert os.environ["KEY_SQ"] == "single"
    del os.environ["KEY_DQ"]
    del os.environ["KEY_SQ"]


def test_skips_comments_and_blank_lines(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("# comment\n\nVALID=yes\n")
    os.environ.pop("VALID", None)
    load_dotenv(tmp_path / ".env")
    assert os.environ["VALID"] == "yes"
    del os.environ["VALID"]


def test_does_not_override_existing_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXISTING_VAR", "original")
    (tmp_path / ".env").write_text("EXISTING_VAR=overridden\n")
    load_dotenv(tmp_path / ".env")
    assert os.environ["EXISTING_VAR"] == "original"


def test_missing_file_is_noop(tmp_path: Path) -> None:
    load_dotenv(tmp_path / ".env")


def test_skips_lines_without_equals(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NOEQUALS\nGOOD=val\n")
    os.environ.pop("NOEQUALS", None)
    os.environ.pop("GOOD", None)
    load_dotenv(tmp_path / ".env")
    assert "NOEQUALS" not in os.environ
    assert os.environ["GOOD"] == "val"
    del os.environ["GOOD"]
