"""Structured LLM call: ask the model for a JSON object that matches a schema.

Same entry point for OpenAI, Anthropic, Gemini and OpenRouter:

- OpenAI / OpenRouter: forced function tool (``tool_choice`` on ``schema_name``).
- Anthropic: forced tool (``tool_choice={"type": "tool", ...}``).
- Gemini: native structured output (``response_mime_type="application/json"`` + schema),
  with the keywords Gemini rejects stripped from the schema sent to the model.

The answer is always validated locally against the *complete* schema (jsonschema,
Draft 2020-12). A non-conforming answer is retried once, then
``StructuredOutputSchemaError`` is raised. Timeouts and provider errors have their own
exception types so callers can tell them apart from schema problems.

Contract: ``docs/tribunale/architecture.md`` (``copilot/structured.py``) and
``docs/tribunale/api-contracts.md`` §6.4, §8.4. ``providers.py`` is left untouched.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from jsonschema import Draft202012Validator

from .config import CopilotConfig

logger = logging.getLogger(__name__)

STRUCTURED_OUTPUT_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "gemini", "openrouter"})

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Keywords kept in the schema sent to Gemini (its OpenAPI-subset ``Schema``). Everything
# else, ``additionalProperties`` included, is stripped; validation still uses the full schema.
_GEMINI_SCHEMA_KEYWORDS: frozenset[str] = frozenset({
    "type", "properties", "required", "items", "enum", "description",
    "minItems", "maxItems", "minLength", "maxLength", "nullable", "format",
    "minimum", "maximum", "anyOf", "propertyOrdering", "title",
})


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------

class StructuredOutputError(Exception):
    """Base error of a structured call. ``code`` maps to ``voice_error.code``."""

    code: str = "structured_error"

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message)
        self.provider = provider


class StructuredOutputUnavailable(StructuredOutputError):
    code = "unsupported_provider"


class StructuredOutputTimeout(StructuredOutputError):
    code = "timeout"


class StructuredOutputProviderError(StructuredOutputError):
    code = "provider_error"


class StructuredOutputSchemaError(StructuredOutputError):
    code = "schema_mismatch"


class _SchemaMismatch(Exception):
    """Internal: the answer of one attempt does not match the schema."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def supports_structured_output(config: CopilotConfig) -> bool:
    """True if the configured provider can return structured output."""
    return config.provider in STRUCTURED_OUTPUT_PROVIDERS


def call_structured(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    schema_name: str,
    timeout_s: float = 45.0,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """dict conforme a `schema` (validato con jsonschema Draft 2020-12 sullo schema completo).
    Una risposta non conforme → un solo nuovo tentativo, poi StructuredOutputSchemaError.
    Provider senza supporto (local) → StructuredOutputUnavailable senza chiamare la rete."""
    provider = config.provider
    if not supports_structured_output(config):
        raise StructuredOutputUnavailable(
            f"Il provider '{provider}' non supporta l'output strutturato",
            provider=provider,
        )

    # An invalid schema is a programming error, not a model failure: fail before any call.
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    last_problem = ""
    for attempt in (1, 2):
        try:
            payload = _call_provider_once(
                config, system_prompt, messages, schema,
                schema_name=schema_name, timeout_s=timeout_s, max_tokens=max_tokens,
            )
            _validate(validator, payload)
            return payload
        except _SchemaMismatch as exc:
            last_problem = str(exc)
            logger.warning(
                "Structured output non conforme (provider=%s, schema=%s, tentativo %d): %s",
                provider, schema_name, attempt, last_problem,
            )

    raise StructuredOutputSchemaError(
        f"Risposta non conforme allo schema '{schema_name}' dopo 2 tentativi: {last_problem}",
        provider=provider,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(validator: Draft202012Validator, payload: Any) -> None:
    if not isinstance(payload, dict):
        raise _SchemaMismatch(f"attesa un oggetto JSON, ricevuto {type(payload).__name__}")
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.absolute_path) or "<radice>"
        # Solo percorso e regola violata: ``first.message`` riporta il valore del modello, che
        # finirebbe nei log e nel messaggio dell'eccezione (TASK-71: nessun testo non verificato
        # del modello nei log).
        raise _SchemaMismatch(f"{where}: regola '{first.validator}' non rispettata")


def _parse_json_object(raw: Any) -> Any:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise _SchemaMismatch("risposta vuota")
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise _SchemaMismatch(f"JSON non valido: {exc}") from exc


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    try:
        import httpx
        if isinstance(exc, httpx.TimeoutException):
            return True
    except ImportError:  # pragma: no cover - httpx ships with every SDK used here
        pass
    for mod_name in ("openai", "anthropic"):
        try:
            mod = __import__(mod_name)
        except ImportError:  # pragma: no cover
            continue
        timeout_cls = getattr(mod, "APITimeoutError", None)
        if timeout_cls is not None and isinstance(exc, timeout_cls):
            return True
    return False


def _call_provider_once(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    schema_name: str,
    timeout_s: float,
    max_tokens: int,
) -> Any:
    """One attempt. Returns the parsed payload (not yet validated).

    Raises ``_SchemaMismatch`` for unusable answers, ``StructuredOutputTimeout`` /
    ``StructuredOutputProviderError`` for transport and provider failures.
    """
    provider = config.provider
    if provider == "anthropic":
        request, extract = _anthropic_request, _anthropic_extract
    elif provider == "gemini":
        request, extract = _gemini_request, _gemini_extract
    else:  # openai / openrouter
        request, extract = _openai_request, _openai_extract

    try:
        response = request(
            config, system_prompt, messages, schema,
            schema_name=schema_name, timeout_s=timeout_s, max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - every SDK failure is classified here
        if _is_timeout(exc):
            raise StructuredOutputTimeout(
                f"Timeout della chiamata al modello ({provider}, {timeout_s:g} s)",
                provider=provider,
            ) from exc
        raise StructuredOutputProviderError(
            f"Errore del provider {provider}: {type(exc).__name__}: {exc}",
            provider=provider,
        ) from exc

    try:
        return extract(response, schema_name)
    except _SchemaMismatch:
        raise
    except Exception as exc:  # noqa: BLE001 - unexpected response shape
        raise _SchemaMismatch(f"risposta inattesa: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# OpenAI / OpenRouter: forced function tool
# ---------------------------------------------------------------------------

def _openai_request(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    schema_name: str,
    timeout_s: float,
    max_tokens: int,
) -> Any:
    import openai

    # OpenAI without an explicit base_url, so OPENAI_BASE_URL (fake LLM of the E2E) works.
    kwargs: dict[str, Any] = {"api_key": config.api_key, "timeout": timeout_s, "max_retries": 0}
    if config.provider == "openrouter":
        kwargs["base_url"] = _OPENROUTER_BASE_URL
    client = openai.OpenAI(**kwargs)

    oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    oai_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)

    return client.chat.completions.create(
        model=config.model,
        max_tokens=max_tokens,
        messages=oai_messages,
        tools=[{"type": "function", "function": {"name": schema_name, "parameters": schema}}],
        tool_choice={"type": "function", "function": {"name": schema_name}},
    )


def _openai_extract(response: Any, schema_name: str) -> Any:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise _SchemaMismatch("nessuna scelta nella risposta")
    message = choices[0].message
    for tc in getattr(message, "tool_calls", None) or []:
        fn = getattr(tc, "function", None)
        if fn is not None and fn.name == schema_name:
            return _parse_json_object(fn.arguments)
    raise _SchemaMismatch(f"nessuna chiamata allo strumento '{schema_name}'")


# ---------------------------------------------------------------------------
# Anthropic: forced tool
# ---------------------------------------------------------------------------

def _anthropic_request(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    schema_name: str,
    timeout_s: float,
    max_tokens: int,
) -> Any:
    import anthropic

    client = anthropic.Anthropic(api_key=config.api_key, timeout=timeout_s, max_retries=0)
    return client.messages.create(
        model=config.model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        tools=[{"name": schema_name, "input_schema": schema}],
        tool_choice={"type": "tool", "name": schema_name},
    )


def _anthropic_extract(response: Any, schema_name: str) -> Any:
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == schema_name:
            return _parse_json_object(block.input)
    raise _SchemaMismatch(f"nessun blocco tool_use '{schema_name}'")


# ---------------------------------------------------------------------------
# Gemini: native structured output
# ---------------------------------------------------------------------------

def _gemini_schema(schema: Any) -> Any:
    """Copy of ``schema`` with only the keywords Gemini's response schema accepts.

    ``additionalProperties`` (rejected by the Gemini API in ``response_schema``) and any
    other unsupported keyword are removed recursively. Names inside ``properties`` are
    property names, not keywords, and are all kept.
    """
    if isinstance(schema, list):
        return [_gemini_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _GEMINI_SCHEMA_KEYWORDS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: _gemini_schema(sub) for name, sub in value.items()}
        elif key in ("items", "anyOf"):
            out[key] = _gemini_schema(value)
        else:
            out[key] = value
    return out


def _gemini_request(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    schema_name: str,
    timeout_s: float,
    max_tokens: int,
) -> Any:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=config.api_key,
        http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),  # milliseconds
    )
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    return client.models.generate_content(
        model=config.model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=_gemini_schema(schema),
        ),
    )


def _gemini_extract(response: Any, schema_name: str) -> Any:
    text = getattr(response, "text", None)
    if text:
        return _parse_json_object(text)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    raise _SchemaMismatch("risposta vuota")
