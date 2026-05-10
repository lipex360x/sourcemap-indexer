from __future__ import annotations

from sourcemap_indexer.domain.value_objects import (
    _DEFAULT_LAYERS,
    Language,
    Layer,
    SideEffect,
    Stability,
)


def test_language_py_value() -> None:
    assert Language.PY == "py"


def test_language_has_all_expected_members() -> None:
    expected = {
        "py",
        "sh",
        "ts",
        "tsx",
        "js",
        "sql",
        "md",
        "yaml",
        "json",
        "toml",
        "php",
        "ruby",
        "go",
        "rust",
        "java",
        "kotlin",
        "swift",
        "scala",
        "c",
        "cpp",
        "csharp",
        "objc",
        "lua",
        "dart",
        "elixir",
        "erlang",
        "haskell",
        "ocaml",
        "clojure",
        "perl",
        "r",
        "julia",
        "vue",
        "svelte",
        "astro",
        "css",
        "scss",
        "less",
        "html",
        "xml",
        "graphql",
        "proto",
        "dockerfile",
        "makefile",
        "terraform",
        "nix",
        "other",
    }
    assert {member.value for member in Language} == expected


def test_layer_is_str_alias() -> None:
    assert Layer is str


def test_default_layers_contains_all_expected() -> None:
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
    assert expected == _DEFAULT_LAYERS


def test_layer_unknown_is_valid_default() -> None:
    assert "unknown" in _DEFAULT_LAYERS


def test_layer_value_is_plain_str() -> None:
    layer: Layer = "domain"
    assert isinstance(layer, str)


def test_stability_has_all_expected_members() -> None:
    expected = {"core", "stable", "experimental", "deprecated", "unknown"}
    assert {member.value for member in Stability} == expected


def test_side_effect_has_all_expected_members() -> None:
    expected = {"writes_fs", "spawns_process", "network", "git", "environ"}
    assert {member.value for member in SideEffect} == expected


def test_language_is_str_subclass() -> None:
    assert isinstance(Language.PY, str)
