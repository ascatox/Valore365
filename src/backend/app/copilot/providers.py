"""LLM provider helpers: tool-calling and raw streaming per provider."""

from __future__ import annotations

import json
import logging
from typing import Generator

from .config import CopilotConfig
from .models import CopilotMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

def _sse(event_type: str, content: str) -> str:
    """Format an SSE event."""
    return f"data: {json.dumps({'type': event_type, 'content': content}, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Non-streaming tool-calling dispatch
# ---------------------------------------------------------------------------

def _call_llm_with_tools(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
) -> tuple[list[dict], str]:
    """Call LLM with tools (non-streaming). Returns (tool_calls, text_content).

    Each tool_call dict: {"id": str, "name": str, "args": dict}
    """
    provider = config.provider

    if provider == "openai":
        return _call_openai_with_tools(config.api_key, config.model, system_prompt, messages, tools)
    elif provider == "anthropic":
        return _call_anthropic_with_tools(config.api_key, config.model, system_prompt, messages, tools)
    elif provider == "gemini":
        return _call_gemini_with_tools(config.api_key, config.model, system_prompt, messages, tools)
    elif provider == "openrouter":
        return _call_openai_with_tools(
            config.api_key, config.model, system_prompt, messages, tools,
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        raise ValueError(f"Provider '{provider}' non supporta tool calling")


def _call_openai_with_tools(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], tools: list[dict],
    base_url: str | None = None,
) -> tuple[list[dict], str]:
    """OpenAI / OpenRouter tool calling."""
    import openai

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)

    oai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        oai_messages.append(msg)

    response = client.chat.completions.create(
        model=model, max_tokens=2048, messages=oai_messages, tools=tools,
    )
    choice = response.choices[0]
    text_content = choice.message.content or ""

    tool_calls = []
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "args": json.loads(tc.function.arguments) if tc.function.arguments else {},
            })

    return tool_calls, text_content


def _call_anthropic_with_tools(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], tools: list[dict],
) -> tuple[list[dict], str]:
    """Anthropic tool calling."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model, max_tokens=2048, system=system_prompt,
        messages=messages, tools=tools,
    )

    tool_calls = []
    text_content = ""

    for block in response.content:
        if block.type == "text":
            text_content += block.text
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "args": block.input if isinstance(block.input, dict) else {},
            })

    return tool_calls, text_content


def _call_gemini_with_tools(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], tools: list[dict],
) -> tuple[list[dict], str]:
    """Gemini tool calling."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Build Gemini tool declarations
    function_declarations = []
    for t in tools:
        func = t.get("function", t)
        fd = types.FunctionDeclaration(
            name=func["name"],
            description=func["description"],
            parameters=func.get("parameters", {}),
        )
        function_declarations.append(fd)

    gemini_tools = [types.Tool(function_declarations=function_declarations)]

    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Capito, sono pronto ad aiutarti."}]},
    ]
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        parts = msg.get("parts", [{"text": msg.get("content", "")}])
        contents.append({"role": role, "parts": parts})

    response = client.models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(
            max_output_tokens=2048,
            tools=gemini_tools,
        ),
    )

    tool_calls = []
    text_content = ""

    if response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append({
                    "id": fc.name,  # Gemini uses name as id
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                })
            elif hasattr(part, "text") and part.text:
                text_content += part.text

    return tool_calls, text_content


# ---------------------------------------------------------------------------
# Message builders for tool-call conversation history
# ---------------------------------------------------------------------------

def _build_assistant_tool_message(provider: str, tool_calls: list[dict], text_content: str) -> dict:
    """Build the assistant message that contains tool calls, for conversation history."""
    if provider == "anthropic":
        content = []
        if text_content:
            content.append({"type": "text", "text": text_content})
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["args"],
            })
        return {"role": "assistant", "content": content}

    elif provider == "gemini":
        parts = []
        if text_content:
            parts.append({"text": text_content})
        for tc in tool_calls:
            parts.append({
                "function_call": {"name": tc["name"], "args": tc["args"]},
            })
        return {"role": "model", "parts": parts}

    else:  # openai / openrouter
        msg: dict = {
            "role": "assistant",
            "content": text_content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in tool_calls
            ],
        }
        return msg


def _build_tool_result_message(provider: str, tool_id: str, tool_name: str, result: dict) -> dict:
    """Build the tool result message for conversation history."""
    result_str = json.dumps(result, ensure_ascii=False)

    if provider == "anthropic":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_str,
                }
            ],
        }

    elif provider == "gemini":
        return {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": tool_name,
                        "response": result,
                    },
                }
            ],
        }

    else:  # openai / openrouter
        return {
            "role": "tool",
            "tool_call_id": tool_id,
            "content": result_str,
        }


# ---------------------------------------------------------------------------
# Raw streaming helpers (final response, full message history)
# ---------------------------------------------------------------------------

def _stream_final_response(
    config: CopilotConfig,
    system_prompt: str,
    messages: list[dict],
) -> Generator[str, None, None]:
    """Stream the final text response (no tools) from the LLM."""
    provider = config.provider
    api_key = config.api_key
    model = config.model

    if provider == "openai":
        yield from _stream_openai_raw(api_key, model, system_prompt, messages)
    elif provider == "anthropic":
        yield from _stream_anthropic_raw(api_key, model, system_prompt, messages)
    elif provider == "gemini":
        yield from _stream_gemini_raw(api_key, model, system_prompt, messages)
    elif provider == "openrouter":
        yield from _stream_openai_raw(
            api_key, model, system_prompt, messages,
            base_url="https://openrouter.ai/api/v1",
        )


def _stream_openai_raw(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict], base_url: str | None = None,
) -> Generator[str, None, None]:
    """Stream final response from OpenAI/OpenRouter with full message history."""
    import openai

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = openai.OpenAI(**kwargs)

    oai_messages = [{"role": "system", "content": system_prompt}]
    oai_messages.extend(messages)

    stream = client.chat.completions.create(
        model=model, max_tokens=2048, stream=True, messages=oai_messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield _sse("text_delta", delta.content)


def _stream_anthropic_raw(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict],
) -> Generator[str, None, None]:
    """Stream final response from Anthropic with full message history."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    with client.messages.stream(
        model=model, max_tokens=2048, system=system_prompt, messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield _sse("text_delta", text)


def _stream_gemini_raw(
    api_key: str, model: str, system_prompt: str,
    messages: list[dict],
) -> Generator[str, None, None]:
    """Stream final response from Gemini with full message history."""
    from google import genai

    client = genai.Client(api_key=api_key)

    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Capito, sono pronto ad aiutarti."}]},
    ]
    contents.extend(messages)

    response = client.models.generate_content(
        model=model, contents=contents, config={"max_output_tokens": 2048},
    )
    if response.text:
        yield _sse("text_delta", response.text)


# ---------------------------------------------------------------------------
# Legacy streaming (non-agentic -- Fase 1, used as fallback)
# ---------------------------------------------------------------------------

def _stream_openai(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    import openai

    client = openai.OpenAI(api_key=api_key)
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    stream = client.chat.completions.create(
        model=model, max_tokens=2048, stream=True, messages=openai_messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield f"data: {json.dumps({'type': 'text_delta', 'content': delta.content}, ensure_ascii=False)}\n\n"


def _stream_anthropic(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    anthro_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

    with client.messages.stream(
        model=model, max_tokens=2048, system=system_prompt, messages=anthro_messages,
    ) as stream:
        for text in stream.text_stream:
            yield f"data: {json.dumps({'type': 'text_delta', 'content': text}, ensure_ascii=False)}\n\n"


def _stream_gemini(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    from google import genai

    client = genai.Client(api_key=api_key)
    contents = [{"role": "user", "parts": [{"text": system_prompt}]}, {"role": "model", "parts": [{"text": "Capito, sono pronto ad aiutarti."}]}]
    for msg in messages:
        role = "user" if msg.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.content}]})

    response = client.models.generate_content(
        model=model, contents=contents, config={"max_output_tokens": 2048},
    )
    # Gemini returns full response, emit as single chunk
    if response.text:
        yield f"data: {json.dumps({'type': 'text_delta', 'content': response.text}, ensure_ascii=False)}\n\n"


def _stream_openrouter(
    api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    """Stream from OpenRouter (OpenAI-compatible API)."""
    import openai

    client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    stream = client.chat.completions.create(
        model=model, max_tokens=2048, stream=True, messages=openai_messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield f"data: {json.dumps({'type': 'text_delta', 'content': delta.content}, ensure_ascii=False)}\n\n"


def _stream_local(
    local_url: str, api_key: str, model: str, system_prompt: str, messages: list[CopilotMessage],
) -> Generator[str, None, None]:
    """Stream from a local LLM server exposing an OpenAI-compatible API (Ollama, LM Studio, etc.)."""
    import openai

    client = openai.OpenAI(
        base_url=local_url or "http://localhost:11434/v1",
        api_key=api_key or "not-needed",
    )
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    stream = client.chat.completions.create(
        model=model, max_tokens=2048, stream=True, messages=openai_messages,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield f"data: {json.dumps({'type': 'text_delta', 'content': delta.content}, ensure_ascii=False)}\n\n"
