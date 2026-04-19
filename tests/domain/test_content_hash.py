from __future__ import annotations

from sourcemap_indexer.domain.value_objects import ContentHash
from sourcemap_indexer.lib.either import Left, Right

VALID_HASH = "a" * 64


def test_create_returns_right_for_valid_hex() -> None:
    result = ContentHash.create(VALID_HASH)
    assert isinstance(result, Right)
    assert result.value.hex_value == VALID_HASH


def test_create_returns_left_for_wrong_length() -> None:
    result = ContentHash.create("abc")
    assert isinstance(result, Left)
    assert result.error == "invalid-hash-format"


def test_create_returns_left_for_invalid_chars() -> None:
    result = ContentHash.create("g" * 64)
    assert isinstance(result, Left)
    assert result.error == "invalid-hash-format"


def test_create_returns_left_for_uppercase_hex() -> None:
    result = ContentHash.create("A" * 64)
    assert isinstance(result, Left)
    assert result.error == "invalid-hash-format"


def test_from_bytes_returns_sha256_hex() -> None:
    sha256_hello = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    result = ContentHash.from_bytes(b"hello")
    assert isinstance(result, Right)
    assert result.value.hex_value == sha256_hello


def test_from_bytes_is_deterministic() -> None:
    first = ContentHash.from_bytes(b"test-data")
    second = ContentHash.from_bytes(b"test-data")
    assert isinstance(first, Right)
    assert isinstance(second, Right)
    assert first.value.hex_value == second.value.hex_value


def test_from_bytes_different_data_produces_different_hash() -> None:
    first = ContentHash.from_bytes(b"data-a")
    second = ContentHash.from_bytes(b"data-b")
    assert isinstance(first, Right)
    assert isinstance(second, Right)
    assert first.value.hex_value != second.value.hex_value
