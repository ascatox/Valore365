"""Unit tests for app.copilot.structured (TASK-62).

No real network: the SDK client classes (openai.OpenAI, anthropic.Anthropic,
google.genai.Client) are replaced with fakes that replay a scripted list of answers.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import openai
import pytest
from google import genai
from google.genai import errors as genai_errors

from app.copilot import structured
from app.copilot.config import CopilotConfig
from app.copilot.structured import (
    STRUCTURED_OUTPUT_PROVIDERS,
    StructuredOutputError,
    StructuredOutputProviderError,
    StructuredOutputSchemaError,
    StructuredOutputTimeout,
    StructuredOutputUnavailable,
    call_structured,
    supports_structured_output,
)

PROVIDERS = ("openai", "anthropic", "gemini", "openrouter")

# api-contracts §6.4, schema_name = "tribunal_opening"
OPENING_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["arguments"],
    "properties": {
        "arguments": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["theme", "stance", "text", "fact_ids"],
                "properties": {
                    "theme": {"type": "string", "enum": [
                        "costi", "diversificazione", "concentrazione", "composizione",
                        "esposizione_geografica", "esposizione_settoriale", "rischio", "scenari",
                        "regole_personali", "qualita_dati"]},
                    "stance": {"type": "string", "enum": ["punto_di_forza", "criticita", "neutro"]},
                    "text": {"type": "string", "minLength": 1, "description": "con segnaposto {F1}"},
                    "fact_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

VALID = {"arguments": [{"theme": "costi", "stance": "punto_di_forza",
                        "text": "Il TER medio è {F3}.", "fact_ids": ["F3"]}]}
INVALID_ENUM = {"arguments": [{"theme": "astrologia", "stance": "neutro", "text": "x", "fact_ids": []}]}
INVALID_EXTRA = {"arguments": [], "verdict": "vince l'indicizzatore"}

SYSTEM = "Tribunale del portafoglio — fase: apertura; voce: indicizzatore\nIstruzioni."
MESSAGES = [{"role": "user", "content": "Fascicolo: ..."}]

_REQ = httpx.Request("POST", "https://example.invalid")


# ---------------------------------------------------------------------------
# Fake SDK clients
# ---------------------------------------------------------------------------

class Script:
    """Scripted answers shared by the fake clients. Each item is a payload (dict / raw str /
    None for "no tool call") or an exception instance to raise."""

    def __init__(self, provider: str, items: list[Any]) -> None:
        self.provider = provider
        self.items = list(items)
        self.inits: list[dict] = []
        self.calls: list[dict] = []

    def next(self) -> Any:
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _openai_response(item: Any, name: str) -> Any:
    tool_calls = None
    if item is not None:
        args = item if isinstance(item, str) else json.dumps(item)
        tool_calls = [SimpleNamespace(id="call_1", type="function",
                                      function=SimpleNamespace(name=name, arguments=args))]
    msg = SimpleNamespace(content=None, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="tool_calls")])


def _anthropic_response(item: Any, name: str) -> Any:
    if item is None:
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Non posso.")])
    payload = item
    if isinstance(item, str):
        try:
            payload = json.loads(item)
        except ValueError:
            payload = item  # malformed input passed through as raw text
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id="tu_1", name=name, input=payload)])


def _gemini_response(item: Any) -> Any:
    if item is None:
        return SimpleNamespace(text=None, parsed=None)
    return SimpleNamespace(text=item if isinstance(item, str) else json.dumps(item))


@pytest.fixture
def fake_sdks(monkeypatch):
    """Install fake SDK clients; returns a function that loads a script."""
    holder: dict[str, Script] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            holder["s"].inits.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            holder["s"].calls.append(kwargs)
            return _openai_response(holder["s"].next(), kwargs["tool_choice"]["function"]["name"])

    class FakeAnthropic:
        def __init__(self, **kwargs):
            holder["s"].inits.append(kwargs)
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            holder["s"].calls.append(kwargs)
            return _anthropic_response(holder["s"].next(), kwargs["tool_choice"]["name"])

    class FakeGenai:
        def __init__(self, **kwargs):
            holder["s"].inits.append(kwargs)
            self.models = SimpleNamespace(generate_content=self._generate)

        def _generate(self, **kwargs):
            holder["s"].calls.append(kwargs)
            return _gemini_response(holder["s"].next())

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    monkeypatch.setattr(genai, "Client", FakeGenai)

    def load(provider: str, items: list[Any]) -> Script:
        holder["s"] = Script(provider, items)
        return holder["s"]

    return load


def _cfg(provider: str) -> CopilotConfig:
    return CopilotConfig(provider=provider, model="m-test", api_key="sk-test")


def _call(provider: str, **kw) -> dict:
    return call_structured(_cfg(provider), SYSTEM, MESSAGES, OPENING_SCHEMA,
                           schema_name="tribunal_opening", **kw)


def _timeout_exc(provider: str) -> BaseException:
    if provider in ("openai", "openrouter"):
        return openai.APITimeoutError(request=_REQ)
    if provider == "anthropic":
        return anthropic.APITimeoutError(request=_REQ)
    return httpx.ReadTimeout("read timed out", request=_REQ)


def _provider_exc(provider: str) -> BaseException:
    resp = httpx.Response(500, request=_REQ)
    if provider in ("openai", "openrouter"):
        return openai.InternalServerError("boom", response=resp, body=None)
    if provider == "anthropic":
        return anthropic.InternalServerError("boom", response=resp, body=None)
    return genai_errors.ServerError(503, {"error": {"message": "down", "status": "UNAVAILABLE"}})


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------

def test_supported_providers_match_contract():
    assert STRUCTURED_OUTPUT_PROVIDERS == frozenset(PROVIDERS)
    for p in PROVIDERS:
        assert supports_structured_output(_cfg(p)) is True
    assert supports_structured_output(_cfg("local")) is False


def test_local_provider_is_unavailable_without_any_call(fake_sdks):
    script = fake_sdks("local", [VALID])
    with pytest.raises(StructuredOutputUnavailable) as ei:
        _call("local")
    assert ei.value.code == "unsupported_provider"
    assert ei.value.provider == "local"
    assert script.inits == [] and script.calls == []


def test_error_hierarchy_and_codes():
    codes = {
        StructuredOutputError: "structured_error",
        StructuredOutputUnavailable: "unsupported_provider",
        StructuredOutputTimeout: "timeout",
        StructuredOutputProviderError: "provider_error",
        StructuredOutputSchemaError: "schema_mismatch",
    }
    for cls, code in codes.items():
        assert issubclass(cls, StructuredOutputError)
        err = cls("msg", provider="openai")
        assert err.code == code and err.provider == "openai" and str(err) == "msg"


# ---------------------------------------------------------------------------
# Per provider: valid, non-conforming, timeout, provider error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider", PROVIDERS)
def test_valid_response_is_returned(fake_sdks, provider):
    script = fake_sdks(provider, [VALID])
    assert _call(provider) == VALID
    assert len(script.calls) == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_one_retry_then_valid(fake_sdks, provider):
    script = fake_sdks(provider, [INVALID_ENUM, VALID])
    assert _call(provider) == VALID
    assert len(script.calls) == 2


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("bad", [INVALID_ENUM, INVALID_EXTRA, "{not json", None, "[1, 2]"],
                         ids=["enum", "extra_key", "bad_json", "no_tool_call", "not_object"])
def test_non_conforming_twice_raises_schema_error(fake_sdks, provider, bad):
    script = fake_sdks(provider, [bad, bad, VALID])
    with pytest.raises(StructuredOutputSchemaError) as ei:
        _call(provider)
    assert ei.value.code == "schema_mismatch"
    assert ei.value.provider == provider
    assert len(script.calls) == 2  # exactly one retry, never a third call


@pytest.mark.parametrize("provider", PROVIDERS)
def test_timeout_is_distinct_and_not_retried(fake_sdks, provider):
    script = fake_sdks(provider, [_timeout_exc(provider), VALID])
    with pytest.raises(StructuredOutputTimeout) as ei:
        _call(provider, timeout_s=12.5)
    assert ei.value.code == "timeout"
    assert ei.value.provider == provider
    assert not isinstance(ei.value, StructuredOutputSchemaError)
    assert len(script.calls) == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_provider_error_is_distinct_and_not_retried(fake_sdks, provider):
    script = fake_sdks(provider, [_provider_exc(provider), VALID])
    with pytest.raises(StructuredOutputProviderError) as ei:
        _call(provider)
    assert ei.value.code == "provider_error"
    assert ei.value.provider == provider
    assert not isinstance(ei.value, (StructuredOutputTimeout, StructuredOutputSchemaError))
    assert len(script.calls) == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_timeout_on_retry_after_bad_answer(fake_sdks, provider):
    fake_sdks(provider, [INVALID_ENUM, _timeout_exc(provider)])
    with pytest.raises(StructuredOutputTimeout):
        _call(provider)


# ---------------------------------------------------------------------------
# Request shape per provider (api-contracts §8.4, architecture.md)
# ---------------------------------------------------------------------------

def test_openai_request_uses_forced_tool_and_no_base_url(fake_sdks):
    script = fake_sdks("openai", [VALID])
    _call("openai", timeout_s=12.5, max_tokens=999)
    init, call = script.inits[0], script.calls[0]
    assert "base_url" not in init  # OPENAI_BASE_URL of the E2E fake LLM keeps working
    assert init["api_key"] == "sk-test" and init["timeout"] == 12.5 and init["max_retries"] == 0
    assert call["model"] == "m-test" and call["max_tokens"] == 999
    assert call["tools"] == [{"type": "function",
                              "function": {"name": "tribunal_opening", "parameters": OPENING_SCHEMA}}]
    assert call["tool_choice"] == {"type": "function", "function": {"name": "tribunal_opening"}}
    assert call["messages"][0] == {"role": "system", "content": SYSTEM}
    assert call["messages"][1:] == MESSAGES


def test_openrouter_request_uses_openrouter_base_url(fake_sdks):
    script = fake_sdks("openrouter", [VALID])
    _call("openrouter")
    assert script.inits[0]["base_url"] == "https://openrouter.ai/api/v1"
    assert script.inits[0]["timeout"] == 45.0
    assert script.calls[0]["tool_choice"]["function"]["name"] == "tribunal_opening"


def test_anthropic_request_uses_forced_tool(fake_sdks):
    script = fake_sdks("anthropic", [VALID])
    _call("anthropic", timeout_s=20)
    init, call = script.inits[0], script.calls[0]
    assert init["timeout"] == 20 and init["max_retries"] == 0
    assert call["system"] == SYSTEM and call["messages"] == MESSAGES
    assert call["max_tokens"] == 2048
    assert call["tools"] == [{"name": "tribunal_opening", "input_schema": OPENING_SCHEMA}]
    assert call["tool_choice"] == {"type": "tool", "name": "tribunal_opening"}


def test_gemini_request_uses_native_json_schema_without_additional_properties(fake_sdks):
    script = fake_sdks("gemini", [VALID])
    _call("gemini", timeout_s=12.5, max_tokens=777)
    init, call = script.inits[0], script.calls[0]
    assert init["http_options"].timeout == 12500  # milliseconds
    cfg = call["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.system_instruction == SYSTEM
    assert cfg.max_output_tokens == 777
    sent = cfg.response_schema
    assert "additionalProperties" not in json.dumps(sent)
    item = sent["properties"]["arguments"]["items"]
    assert item["required"] == ["theme", "stance", "text", "fact_ids"]
    assert item["properties"]["text"] == {"type": "string", "minLength": 1, "description": "con segnaposto {F1}"}
    assert sent["properties"]["arguments"]["minItems"] == 1
    assert call["contents"] == [{"role": "user", "parts": [{"text": "Fascicolo: ..."}]}]


def test_gemini_still_validates_against_full_schema(fake_sdks):
    # The schema sent to Gemini has no additionalProperties, but local validation does.
    fake_sdks("gemini", [INVALID_EXTRA, INVALID_EXTRA])
    with pytest.raises(StructuredOutputSchemaError):
        _call("gemini")


def test_gemini_schema_keeps_property_named_like_a_keyword():
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"additionalProperties": {"type": "string"}, "type": {"type": "string"}}}
    out = structured._gemini_schema(schema)
    assert out == {"type": "object",
                   "properties": {"additionalProperties": {"type": "string"}, "type": {"type": "string"}}}
    assert "additionalProperties" in schema  # input not mutated


def test_assistant_messages_are_mapped_for_gemini(fake_sdks):
    script = fake_sdks("gemini", [VALID])
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"}]
    call_structured(_cfg("gemini"), SYSTEM, msgs, OPENING_SCHEMA, schema_name="tribunal_opening")
    assert [c["role"] for c in script.calls[0]["contents"]] == ["user", "model", "user"]


def test_invalid_schema_fails_before_any_call(fake_sdks):
    script = fake_sdks("openai", [VALID])
    with pytest.raises(Exception):
        call_structured(_cfg("openai"), SYSTEM, MESSAGES, {"type": 12}, schema_name="x")
    assert script.calls == []
