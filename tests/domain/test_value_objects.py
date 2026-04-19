from __future__ import annotations

from sourcemap_indexer.domain.value_objects import Language, Layer, SideEffect, Stability


def test_language_py_value() -> None:
    assert Language.PY == "py"


def test_language_has_all_expected_members() -> None:
    expected = {"py", "sh", "ts", "tsx", "js", "sql", "md", "yaml", "json", "toml", "other"}
    assert {member.value for member in Language} == expected


def test_layer_unknown_value() -> None:
    assert Layer.UNKNOWN == "unknown"


def test_layer_has_all_expected_members() -> None:
    expected = {
        "domain",
        "infra",
        "application",
        "cli",
        "hook",
        "lib",
        "config",
        "doc",
        "test",
        "unknown",
    }
    assert {member.value for member in Layer} == expected


def test_stability_has_all_expected_members() -> None:
    expected = {"core", "stable", "experimental", "deprecated", "unknown"}
    assert {member.value for member in Stability} == expected


def test_side_effect_has_all_expected_members() -> None:
    expected = {"writes_fs", "spawns_process", "network", "git", "environ"}
    assert {member.value for member in SideEffect} == expected


def test_language_is_str_subclass() -> None:
    assert isinstance(Language.PY, str)


def test_layer_is_str_subclass() -> None:
    assert isinstance(Layer.DOMAIN, str)
