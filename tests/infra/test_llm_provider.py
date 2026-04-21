from __future__ import annotations

import pytest

from sourcemap_indexer.infra.llm_provider import LLMProvider, resolve_provider
from sourcemap_indexer.lib.either import Left, Right


def test_resolve_http_returns_right() -> None:
    result = resolve_provider("http")
    assert isinstance(result, Right)


def test_resolve_unknown_returns_left() -> None:
    result = resolve_provider("unknown-xyz")
    assert isinstance(result, Left)
    assert result.error == "unknown-provider"


def test_resolve_claude_cli_returns_right() -> None:
    result = resolve_provider("claude-cli")
    assert isinstance(result, Right)


def test_http_provider_satisfies_llmprovider_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://localhost:1234/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    from sourcemap_indexer.infra.llm_client import HttpLLMProvider  # noqa: PLC0415

    provider = HttpLLMProvider.__new__(HttpLLMProvider)
    assert isinstance(provider, LLMProvider)


def test_claude_cli_provider_satisfies_protocol() -> None:
    from sourcemap_indexer.infra.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    provider = ClaudeCliProvider.__new__(ClaudeCliProvider)
    assert isinstance(provider, LLMProvider)


def test_claude_cli_not_on_path_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    provider = ClaudeCliProvider()
    result = provider.enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error == "claude-cli-not-configured"


def test_claude_cli_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    payload = {
        "purpose": "Entry point",
        "tags": ["cli"],
        "layer": "application",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.claude_cli_provider._check_auth",
        lambda: None,
    )
    provider = ClaudeCliProvider()
    result = provider.enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Right)
    assert result.value.purpose == "Entry point"
