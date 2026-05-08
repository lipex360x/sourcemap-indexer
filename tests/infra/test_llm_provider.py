from __future__ import annotations

import pytest

from sourcemap_indexer.infra.llm.llm_provider import LLMProvider, resolve_provider
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
    from sourcemap_indexer.infra.llm.llm_client import HttpLLMProvider  # noqa: PLC0415

    provider = HttpLLMProvider.__new__(HttpLLMProvider)
    assert isinstance(provider, LLMProvider)


def test_claude_cli_provider_satisfies_protocol() -> None:
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    provider = ClaudeCliProvider.__new__(ClaudeCliProvider)
    assert isinstance(provider, LLMProvider)


def test_claude_cli_not_on_path_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

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
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

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
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    provider = ClaudeCliProvider()
    result = provider.enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Right)
    assert result.value.purpose == "Entry point"


def test_claude_cli_passes_model_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.setenv("SOURCEMAP_LLM_CLI_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "--model" in captured[0]
    assert "claude-haiku-4-5-20251001" in captured[0]


def test_claude_cli_calls_llm_log_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    recorded: list[dict[str, object]] = []

    class _SpyLog:
        def record(self, **kwargs: object) -> None:
            recorded.append(kwargs)

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider(llm_log=_SpyLog()).enrich("app.py", Language.PY, "x = 1")
    assert len(recorded) == 1
    assert recorded[0]["result"] == "ok"
    assert recorded[0]["path"] == "app.py"
    messages = recorded[0]["messages"]
    assert isinstance(messages, list)
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles


def test_claude_cli_factory_forwards_llm_log() -> None:
    recorded: list[str] = []

    class _SpyLog:
        def record(self, **kwargs: object) -> None:
            recorded.append(str(kwargs.get("result")))

    result = resolve_provider("claude-cli")
    assert isinstance(result, Right)
    provider = result.value(llm_log=_SpyLog())
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    assert isinstance(provider, ClaudeCliProvider)
    assert provider._llm_log is _SpyLog or hasattr(provider, "_llm_log")


def test_claude_cli_passes_effort_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.setenv("SOURCEMAP_LLM_CLI_EFFORT", "high")
    monkeypatch.delenv("SOURCEMAP_LLM_CLI_MODEL", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "--effort" in captured[0]
    assert "high" in captured[0]


def test_claude_cli_omits_effort_flag_when_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.delenv("SOURCEMAP_LLM_CLI_EFFORT", raising=False)
    monkeypatch.delenv("SOURCEMAP_LLM_CLI_MODEL", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "--effort" not in captured[0]


def test_claude_cli_omits_model_flag_when_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.delenv("SOURCEMAP_LLM_CLI_MODEL", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "--model" not in captured[0]


def test_claude_cli_includes_system_prompt_in_cmd(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "--system-prompt" in captured[0]


def test_claude_cli_uses_custom_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider(system_prompt="CUSTOM").enrich("app.py", Language.PY, "x = 1")
    idx = captured[0].index("--system-prompt")
    assert captured[0][idx + 1] == "CUSTOM"


def test_claude_cli_builds_system_prompt_from_valid_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    wrapper = json.dumps({"result": json.dumps(payload)})

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=wrapper, stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: None,
    )
    ClaudeCliProvider(valid_layers=frozenset({"domain", "custom-layer"})).enrich(
        "app.py", Language.PY, "x = 1"
    )
    idx = captured[0].index("--system-prompt")
    assert "custom-layer" in captured[0][idx + 1]


def test_resolve_opencode_returns_right() -> None:
    result = resolve_provider("opencode")
    assert isinstance(result, Right)


def test_opencode_provider_satisfies_protocol() -> None:
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    provider = OpenCodeProvider.__new__(OpenCodeProvider)
    assert isinstance(provider, LLMProvider)


def test_opencode_not_on_path_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = OpenCodeProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error == "opencode-not-configured"


def test_opencode_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    payload = {
        "purpose": "Entry point",
        "tags": ["cli"],
        "layer": "application",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = OpenCodeProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Right)
    assert result.value.purpose == "Entry point"


def test_opencode_passes_model_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setenv("SOURCEMAP_LLM_CLI_MODEL", "openrouter/openai/gpt-oss-20b:free")
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider().enrich("app.py", Language.PY, "x = 1")
    assert "-m" in captured[0]
    assert "openrouter/openai/gpt-oss-20b:free" in captured[0]


def test_opencode_omits_model_flag_when_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.delenv("SOURCEMAP_LLM_CLI_MODEL", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider().enrich("app.py", Language.PY, "x = 1")
    assert "-m" not in captured[0]


def test_opencode_subprocess_error_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = OpenCodeProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error.startswith("opencode-error:")


def test_opencode_embeds_system_prompt_in_message(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider(system_prompt="CUSTOM_SYS").enrich("app.py", Language.PY, "x = 1")
    full_message = " ".join(captured[0])
    assert "CUSTOM_SYS" in full_message


def test_opencode_calls_llm_log_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    recorded: list[dict[str, object]] = []

    class _SpyLog:
        def record(self, **kwargs: object) -> None:
            recorded.append(kwargs)

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider(llm_log=_SpyLog()).enrich("app.py", Language.PY, "x = 1")
    assert len(recorded) == 1
    assert recorded[0]["result"] == "ok"
    assert recorded[0]["path"] == "app.py"
    messages = recorded[0]["messages"]
    assert isinstance(messages, list)
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles


def test_opencode_factory_forwards_llm_log() -> None:
    recorded: list[str] = []

    class _SpyLog:
        def record(self, **kwargs: object) -> None:
            recorded.append(str(kwargs.get("result")))

    result = resolve_provider("opencode")
    assert isinstance(result, Right)
    provider = result.value(llm_log=_SpyLog())
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    assert isinstance(provider, OpenCodeProvider)
    assert hasattr(provider, "_llm_log")
    assert provider._llm_log is not None


def test_claude_cli_auth_failure_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        "sourcemap_indexer.infra.llm.claude_cli_provider._check_auth",
        lambda: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "claude")),
    )
    result = ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error == "claude-cli-auth-error"


def test_claude_cli_subprocess_error_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "claude")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr("sourcemap_indexer.infra.llm.claude_cli_provider._check_auth", lambda: None)
    monkeypatch.setattr(subprocess, "run", _raise)
    result = ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert "claude-cli-error" in result.error


def test_claude_cli_invalid_json_output_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="not-json-at-all", stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr("sourcemap_indexer.infra.llm.claude_cli_provider._check_auth", lambda: None)
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert "claude-cli-parse-error" in result.error


def test_claude_cli_build_prompt_includes_extra_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps({"result": json.dumps(payload)}), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr("sourcemap_indexer.infra.llm.claude_cli_provider._check_auth", lambda: None)
    monkeypatch.setattr(subprocess, "run", _fake_run)
    ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1", extra_instruction="write in English")
    prompt_arg = captured[0][2]
    assert "Additional instruction: write in English" in prompt_arg


def test_claude_cli_build_prompt_includes_import_context(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.claude_cli_provider import ClaudeCliProvider  # noqa: PLC0415

    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps({"result": json.dumps(payload)}), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr("sourcemap_indexer.infra.llm.claude_cli_provider._check_auth", lambda: None)
    monkeypatch.setattr(subprocess, "run", _fake_run)
    import_ctx = "Context from direct imports:\n- mod/util.py: utility"
    ClaudeCliProvider().enrich("app.py", Language.PY, "x = 1", import_context=import_ctx)
    prompt_arg = captured[0][2]
    assert "Context from direct imports" in prompt_arg


def test_check_auth_calls_claude_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.infra.llm.claude_cli_provider import _check_auth  # noqa: PLC0415

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    _check_auth()
    assert "claude" in captured[0]
    assert "auth" in captured[0]


def test_make_http_returns_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://localhost/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "test-model")
    result = resolve_provider("http")
    assert isinstance(result, Right)
    provider = result.value()
    assert isinstance(provider, LLMProvider)


def test_make_opencode_returns_provider() -> None:
    result = resolve_provider("opencode")
    assert isinstance(result, Right)
    provider = result.value()
    assert isinstance(provider, LLMProvider)


def test_opencode_build_prompt_includes_extra_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider().enrich("app.py", Language.PY, "x = 1", extra_instruction="write in French")
    full_prompt = captured[0][2]
    assert "write in French" in full_prompt


def test_opencode_build_prompt_includes_import_context(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider().enrich(
        "app.py",
        Language.PY,
        "x = 1",
        import_context="Context from direct imports:\n- mod/util.py: utility",
    )
    full_prompt = captured[0][2]
    assert "Context from direct imports" in full_prompt


def test_opencode_uses_valid_layers_for_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "custom-layer",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }
    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider(valid_layers=frozenset({"domain", "custom-layer"})).enrich(
        "app.py", Language.PY, "x = 1"
    )
    full_prompt = captured[0][2]
    assert "custom-layer" in full_prompt


def test_opencode_strips_null_bytes_from_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.opencode_provider import OpenCodeProvider  # noqa: PLC0415

    captured: list[list[str]] = []
    payload = {
        "purpose": "p",
        "tags": ["t"],
        "layer": "infra",
        "stability": "stable",
        "side_effects": [],
        "invariants": [],
    }

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    OpenCodeProvider().enrich("app.py", Language.PY, "x = 1\x00\x00y = 2")
    full_prompt = " ".join(captured[0])
    assert "\x00" not in full_prompt
    assert "x = 1" in full_prompt
    assert "y = 2" in full_prompt


def _gemini_payload(response_body: str) -> str:
    import json  # noqa: PLC0415

    return json.dumps({"session_id": "abc", "response": response_body, "stats": {}})


def _gemini_enrichment_response() -> str:
    import json  # noqa: PLC0415

    return json.dumps(
        {
            "purpose": "Entry point",
            "tags": ["cli"],
            "layer": "application",
            "stability": "stable",
            "side_effects": [],
            "invariants": [],
        }
    )


def test_resolve_gemini_cli_returns_right() -> None:
    result = resolve_provider("gemini-cli")
    assert isinstance(result, Right)


def test_gemini_cli_provider_satisfies_protocol() -> None:
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    provider = GeminiCliProvider.__new__(GeminiCliProvider)
    assert isinstance(provider, LLMProvider)


def test_gemini_cli_not_on_path_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error == "gemini-cli-not-configured"


def test_gemini_cli_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Right)
    assert result.value.purpose == "Entry point"


def test_gemini_cli_command_includes_skip_trust_and_json_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "--skip-trust" in captured[0]
    assert "-o" in captured[0]
    json_idx = captured[0].index("-o")
    assert captured[0][json_idx + 1] == "json"
    assert "-p" in captured[0]


def test_gemini_cli_passes_model_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    monkeypatch.setenv("SOURCEMAP_LLM_CLI_MODEL", "gemini-2.5-pro")
    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "-m" in captured[0]
    idx = captured[0].index("-m")
    assert captured[0][idx + 1] == "gemini-2.5-pro"


def test_gemini_cli_omits_model_flag_when_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    monkeypatch.delenv("SOURCEMAP_LLM_CLI_MODEL", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert "-m" not in captured[0]


def test_gemini_cli_subprocess_error_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error.startswith("gemini-cli-error:")


def test_gemini_cli_quota_exhausted_returns_left(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="",
            stderr="Attempt 1 failed: You have exhausted your capacity on this model..",
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error == "gemini-cli-quota-exhausted"


def test_gemini_cli_outer_json_parse_error_returns_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, stdout="not json at all", stderr="")

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error == "gemini-cli-parse-error"


def test_gemini_cli_missing_response_field_returns_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps({"session_id": "x"}), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = GeminiCliProvider().enrich("app.py", Language.PY, "x = 1")
    assert isinstance(result, Left)
    assert result.error == "gemini-cli-parse-error"


def test_gemini_cli_embeds_system_prompt_in_message(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    GeminiCliProvider(system_prompt="CUSTOM_SYS").enrich("app.py", Language.PY, "x = 1")
    full_message = " ".join(captured[0])
    assert "CUSTOM_SYS" in full_message


def test_gemini_cli_calls_llm_log_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    recorded: list[dict[str, object]] = []

    class _SpyLog:
        def record(self, **kwargs: object) -> None:
            recorded.append(kwargs)

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    GeminiCliProvider(llm_log=_SpyLog()).enrich("app.py", Language.PY, "x = 1")
    assert len(recorded) == 1
    assert recorded[0]["result"] == "ok"
    assert recorded[0]["path"] == "app.py"
    messages = recorded[0]["messages"]
    assert isinstance(messages, list)
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles


def test_gemini_cli_factory_forwards_llm_log() -> None:
    class _SpyLog:
        def record(self, **_kwargs: object) -> None:
            return None

    result = resolve_provider("gemini-cli")
    assert isinstance(result, Right)
    provider = result.value(llm_log=_SpyLog())
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    assert isinstance(provider, GeminiCliProvider)
    assert provider._llm_log is not None


def test_gemini_cli_appends_extra_instruction_and_import_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    recorded: list[dict[str, object]] = []

    class _SpyLog:
        def record(self, **kwargs: object) -> None:
            recorded.append(kwargs)

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    GeminiCliProvider(llm_log=_SpyLog()).enrich(
        "app.py",
        Language.PY,
        "x = 1",
        extra_instruction="be terse",
        import_context="Imports: foo, bar",
    )
    full_prompt = " ".join(captured[0])
    assert "be terse" in full_prompt
    assert "Imports: foo, bar" in full_prompt
    user_prompt = recorded[0]["messages"][1]["content"]  # type: ignore[index]
    assert "be terse" in user_prompt
    assert "Imports: foo, bar" in user_prompt


def test_gemini_cli_strips_null_bytes_from_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415
    from sourcemap_indexer.infra.llm.gemini_cli_provider import (  # noqa: PLC0415
        GeminiCliProvider,
    )

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    GeminiCliProvider().enrich("app.py", Language.PY, "x = 1\x00\x00y = 2")
    full_prompt = " ".join(captured[0])
    assert "\x00" not in full_prompt
    assert "x = 1" in full_prompt
    assert "y = 2" in full_prompt


def test_gemini_cli_factory_forwards_valid_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from sourcemap_indexer.domain.value_objects import Language  # noqa: PLC0415

    captured: list[list[str]] = []

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout=_gemini_payload(_gemini_enrichment_response()), stderr=""
        )

    monkeypatch.setattr(shutil, "which", lambda _name: "/opt/homebrew/bin/gemini")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    factory = resolve_provider("gemini-cli")
    assert isinstance(factory, Right)
    provider = factory.value(valid_layers=frozenset({"domain", "custom-layer"}))
    provider.enrich("app.py", Language.PY, "x = 1")
    full_prompt = " ".join(captured[0])
    assert "custom-layer" in full_prompt
