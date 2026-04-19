from __future__ import annotations

import re

from sourcemap_indexer.domain.value_objects import ItemId
from sourcemap_indexer.lib.either import Left, Right

UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_generate_returns_valid_uuid_v4() -> None:
    item_id = ItemId.generate()
    assert UUID_V4_PATTERN.match(item_id.uuid_str)


def test_generate_returns_unique_ids() -> None:
    first = ItemId.generate()
    second = ItemId.generate()
    assert first.uuid_str != second.uuid_str


def test_from_string_valid_uuid() -> None:
    valid_uuid = "123e4567-e89b-42d3-a456-426614174000"
    result = ItemId.from_string(valid_uuid)
    assert isinstance(result, Right)
    assert result.value.uuid_str == valid_uuid


def test_from_string_invalid_format() -> None:
    result = ItemId.from_string("not-a-uuid")
    assert isinstance(result, Left)
    assert result.error == "invalid-uuid-format"


def test_from_string_empty_string() -> None:
    result = ItemId.from_string("")
    assert isinstance(result, Left)
    assert result.error == "invalid-uuid-format"
