from __future__ import annotations

import hashlib
from pathlib import Path

from sourcemap_indexer.domain.value_objects import ContentHash
from sourcemap_indexer.infra.fs.hasher import hash_content, hash_file
from sourcemap_indexer.lib.either import Left, Right


def test_hash_content_deterministic() -> None:
    first = hash_content(b"hello world")
    second = hash_content(b"hello world")
    assert first.hex_value == second.hex_value


def test_hash_content_matches_sha256() -> None:
    data = b"test-data"
    expected = hashlib.sha256(data).hexdigest()
    result = hash_content(data)
    assert result.hex_value == expected


def test_hash_content_different_data_differs() -> None:
    assert hash_content(b"aaa").hex_value != hash_content(b"bbb").hex_value


def test_hash_file_returns_right_for_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_bytes(b"sample content")
    result = hash_file(target)
    assert isinstance(result, Right)
    assert isinstance(result.value, ContentHash)


def test_hash_file_matches_hash_content(tmp_path: Path) -> None:
    data = b"deterministic"
    target = tmp_path / "file.txt"
    target.write_bytes(data)
    result = hash_file(target)
    assert isinstance(result, Right)
    assert result.value.hex_value == hash_content(data).hex_value


def test_hash_file_returns_left_for_missing_file(tmp_path: Path) -> None:
    result = hash_file(tmp_path / "does_not_exist.txt")
    assert isinstance(result, Left)
    assert result.error == "file-not-found"


def test_hash_file_returns_left_for_unreadable_file(tmp_path: Path) -> None:
    target = tmp_path / "locked.txt"
    target.write_bytes(b"data")
    target.chmod(0o000)
    result = hash_file(target)
    assert isinstance(result, Left)
    assert result.error.startswith("read-error")
    target.chmod(0o644)
