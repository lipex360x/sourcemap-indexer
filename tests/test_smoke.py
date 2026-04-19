from __future__ import annotations

from sourcemap_indexer import __version__


def test_version_is_string() -> None:
    assert isinstance(__version__, str)


def test_version_value() -> None:
    assert __version__ == "0.1.0"
