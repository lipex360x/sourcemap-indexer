from __future__ import annotations

import json

import httpx
import pytest

from sourcemap_indexer.domain.value_objects import Language, Layer, SideEffect, Stability
from sourcemap_indexer.infra.llama_client import (
    EnrichmentResult,
    LlamaClient,
    LlmConfig,
    from_environ,
)
from sourcemap_indexer.lib.either import Left, Right
from sourcemap_indexer.lib.llm_log import LlmLog

_VALID_PAYLOAD = {
    "purpose": "Validates JWT tokens",
    "tags": ["auth", "jwt", "middleware"],
    "layer": "infra",
    "stability": "stable",
    "side_effects": ["network"],
    "invariants": ["token must expire within 24h"],
}


def _mock_response(body: dict[str, object], status: int = 200) -> httpx.Response:
    content = json.dumps({"choices": [{"message": {"content": json.dumps(body)}}]})
    return httpx.Response(status, text=content)


def _client_with(response: httpx.Response) -> LlamaClient:
    transport = httpx.MockTransport(lambda request: response)
    http_client = httpx.Client(transport=transport)
    return LlamaClient(LlmConfig(), http_client=http_client)


def test_llm_config_defaults() -> None:
    config = LlmConfig()
    assert "1234" in config.url or "8080" in config.url
    assert config.temperature == 0.1
    assert config.max_tokens == 800
    assert config.timeout_seconds == 60.0
    assert config.max_chars == 8000
    assert config.api_key == ""


def test_from_environ_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://host/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-model")
    monkeypatch.setenv("SOURCEMAP_LLM_API_KEY", "test-secret-key")
    config = from_environ()
    assert config.api_key == "test-secret-key"


def test_client_sends_auth_header_when_api_key_set() -> None:
    captured: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("authorization", ""))
        return _mock_response(_VALID_PAYLOAD)

    transport = httpx.MockTransport(capture)
    http_client = httpx.Client(transport=transport)
    config = LlmConfig(api_key="my-key")
    client = LlamaClient(config, http_client=http_client)
    client.enrich("src/f.py", Language.PY, "code")
    assert captured[0] == "Bearer my-key"


def test_client_sends_no_auth_header_when_api_key_empty() -> None:
    captured: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("authorization", ""))
        return _mock_response(_VALID_PAYLOAD)

    transport = httpx.MockTransport(capture)
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    client.enrich("src/f.py", Language.PY, "code")
    assert captured[0] == ""


def test_content_is_truncated_when_exceeds_max_chars() -> None:
    captured: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        captured.append(body["messages"][1]["content"])
        return _mock_response(_VALID_PAYLOAD)

    transport = httpx.MockTransport(capture)
    http_client = httpx.Client(transport=transport)
    config = LlmConfig(max_chars=10)
    client = LlamaClient(config, http_client=http_client)
    client.enrich("src/f.py", Language.PY, "A" * 100)
    assert len(captured) == 1
    assert "A" * 100 not in captured[0]
    assert "A" * 10 in captured[0]


def test_from_environ_reads_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://myhost:9999/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-model")
    config = from_environ()
    assert config.url == "http://myhost:9999/v1/chat/completions"


def test_from_environ_reads_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://host/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-custom-model")
    config = from_environ()
    assert config.model == "my-custom-model"


def test_from_environ_raises_when_url_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-model")
    with pytest.raises(KeyError):
        from_environ()


def test_from_environ_raises_when_model_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://host/v1/chat/completions")
    monkeypatch.delenv("SOURCEMAP_LLM_MODEL", raising=False)
    with pytest.raises(KeyError):
        from_environ()


def test_is_llm_configured_returns_true_when_url_and_model_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://myhost/v1/chat/completions")
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-model")
    from sourcemap_indexer.infra.llama_client import is_llm_configured

    assert is_llm_configured() is True


def test_is_llm_configured_returns_false_when_url_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCEMAP_LLM_URL", raising=False)
    monkeypatch.setenv("SOURCEMAP_LLM_MODEL", "my-model")
    from sourcemap_indexer.infra.llama_client import is_llm_configured

    assert is_llm_configured() is False


def test_is_llm_configured_returns_false_when_model_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCEMAP_LLM_URL", "http://myhost/v1/chat/completions")
    monkeypatch.delenv("SOURCEMAP_LLM_MODEL", raising=False)
    from sourcemap_indexer.infra.llama_client import is_llm_configured

    assert is_llm_configured() is False


def test_enrich_returns_right_for_valid_response() -> None:
    client = _client_with(_mock_response(_VALID_PAYLOAD))
    result = client.enrich("src/auth.py", Language.PY, "def verify(token): ...")
    assert isinstance(result, Right)
    assert result.value.purpose == "Validates JWT tokens"
    assert result.value.layer == Layer.INFRA
    assert result.value.stability == Stability.STABLE
    assert SideEffect.NETWORK in result.value.side_effects
    assert "auth" in result.value.tags
    assert "token must expire within 24h" in result.value.invariants


def test_enrich_parses_json_inside_markdown_fence() -> None:
    fenced = f"```json\n{json.dumps(_VALID_PAYLOAD)}\n```"
    content = json.dumps({"choices": [{"message": {"content": fenced}}]})
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=content))
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.enrich("src/auth.py", Language.PY, "code")
    assert isinstance(result, Right)
    assert result.value.purpose == "Validates JWT tokens"


def test_enrich_returns_left_for_invalid_json() -> None:
    content = json.dumps({"choices": [{"message": {"content": "not json at all"}}]})
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=content))
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Left)
    assert result.error == "llm-parse-error"


def test_enrich_returns_left_for_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="error"))
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Left)
    assert result.error == "llm-http-error: 500"


def test_enrich_returns_left_on_timeout() -> None:
    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    transport = httpx.MockTransport(raise_timeout)
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Left)
    assert result.error == "llm-timeout"


def test_enrich_maps_unknown_layer_to_unknown() -> None:
    payload = {**_VALID_PAYLOAD, "layer": "nonexistent_layer"}
    client = _client_with(_mock_response(payload))
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Right)
    assert result.value.layer == Layer.UNKNOWN


def test_enrich_maps_unknown_stability_to_unknown() -> None:
    payload = {**_VALID_PAYLOAD, "stability": "???"}
    client = _client_with(_mock_response(payload))
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Right)
    assert result.value.stability == Stability.UNKNOWN


def test_enrich_ignores_unknown_side_effects() -> None:
    payload = {**_VALID_PAYLOAD, "side_effects": ["network", "unknown_effect"]}
    client = _client_with(_mock_response(payload))
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Right)
    assert SideEffect.NETWORK in result.value.side_effects
    assert len(result.value.side_effects) == 1


def test_enrich_returns_left_on_request_error() -> None:
    def raise_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(raise_error)
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Left)
    assert result.error.startswith("llm-request-error")


def test_enrich_returns_left_when_response_missing_choices() -> None:
    content = json.dumps({"result": "no choices key"})
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=content))
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Left)
    assert result.error == "llm-parse-error"


def test_parse_json_block_found_but_still_invalid_returns_left() -> None:
    bad = "here is some text {key: not valid json value} end"
    content = json.dumps({"choices": [{"message": {"content": bad}}]})
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=content))
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Left)
    assert result.error == "llm-parse-error"


def test_enrichment_result_has_expected_fields() -> None:
    client = _client_with(_mock_response(_VALID_PAYLOAD))
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Right)
    enrichment = result.value
    assert isinstance(enrichment, EnrichmentResult)
    assert isinstance(enrichment.tags, frozenset)
    assert isinstance(enrichment.side_effects, frozenset)
    assert isinstance(enrichment.invariants, tuple)


def test_ping_returns_right_when_server_responds() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="[]"))
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.ping()
    assert isinstance(result, Right)


def test_ping_returns_left_on_connect_error() -> None:
    def raise_connect(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(raise_connect)
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.ping()
    assert isinstance(result, Left)
    assert "llm-unreachable" in result.error


def test_ping_returns_right_on_any_http_status() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404, text="not found"))
    http_client = httpx.Client(transport=transport)
    client = LlamaClient(LlmConfig(), http_client=http_client)
    result = client.ping()
    assert isinstance(result, Right)


class _CaptureLlmLog:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def record(
        self,
        *,
        path: str,
        language: str,
        model: str,
        messages: list[dict[str, str]],
        response_raw: str,
        result: str,
    ) -> None:
        self.calls.append(
            {
                "path": path,
                "language": language,
                "model": model,
                "messages": messages,
                "response_raw": response_raw,
                "result": result,
            }
        )


def _assert_is_llm_log(log: object) -> None:
    assert isinstance(log, LlmLog)


def test_enrich_calls_llm_log_on_success() -> None:
    spy = _CaptureLlmLog()
    _assert_is_llm_log(spy)
    transport = httpx.MockTransport(lambda _r: _mock_response(_VALID_PAYLOAD))
    client = LlamaClient(LlmConfig(), http_client=httpx.Client(transport=transport), llm_log=spy)
    client.enrich("src/auth.py", Language.PY, "code")
    assert len(spy.calls) == 1
    assert spy.calls[0]["path"] == "src/auth.py"
    assert spy.calls[0]["result"] == "ok"
    assert "Validates JWT tokens" in spy.calls[0]["response_raw"]


def test_enrich_calls_llm_log_on_http_error() -> None:
    spy = _CaptureLlmLog()
    transport = httpx.MockTransport(lambda _r: httpx.Response(500, text="err"))
    client = LlamaClient(LlmConfig(), http_client=httpx.Client(transport=transport), llm_log=spy)
    client.enrich("src/f.py", Language.PY, "code")
    assert len(spy.calls) == 1
    assert spy.calls[0]["result"] == "llm-http-error: 500"


def test_enrich_calls_llm_log_on_timeout() -> None:
    spy = _CaptureLlmLog()

    def raise_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    transport = httpx.MockTransport(raise_timeout)
    client = LlamaClient(LlmConfig(), http_client=httpx.Client(transport=transport), llm_log=spy)
    client.enrich("src/f.py", Language.PY, "code")
    assert len(spy.calls) == 1
    assert spy.calls[0]["result"] == "llm-timeout"
    assert spy.calls[0]["response_raw"] == ""


def test_enrich_without_llm_log_still_works() -> None:
    transport = httpx.MockTransport(lambda _r: _mock_response(_VALID_PAYLOAD))
    client = LlamaClient(LlmConfig(), http_client=httpx.Client(transport=transport))
    result = client.enrich("src/f.py", Language.PY, "code")
    assert isinstance(result, Right)


def test_custom_system_prompt_is_sent_to_llm() -> None:
    captured: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append(body["messages"][0]["content"])
        return _mock_response(_VALID_PAYLOAD)

    transport = httpx.MockTransport(capture)
    client = LlamaClient(
        LlmConfig(),
        http_client=httpx.Client(transport=transport),
        system_prompt="my custom instructions",
    )
    client.enrich("src/f.py", Language.PY, "code")
    assert len(captured) == 1
    assert captured[0] == "my custom instructions"


def test_default_system_prompt_used_when_none_passed() -> None:
    from sourcemap_indexer.infra.llama_client import SYSTEM_PROMPT

    captured: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append(body["messages"][0]["content"])
        return _mock_response(_VALID_PAYLOAD)

    transport = httpx.MockTransport(capture)
    client = LlamaClient(LlmConfig(), http_client=httpx.Client(transport=transport))
    client.enrich("src/f.py", Language.PY, "code")
    assert captured[0] == SYSTEM_PROMPT
