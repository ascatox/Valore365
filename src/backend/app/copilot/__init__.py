"""Copilot package -- re-exports all public symbols for backward compatibility."""

from .config import (
    CopilotConfig,
    _DEFAULT_MODELS,
    _decrypt_api_key,
    _get_model,
    _get_server_api_key,
    encrypt_api_key,
    is_copilot_available,
    resolve_copilot_config,
)
from .models import CopilotChatRequest, CopilotMessage
from .providers import (
    _build_assistant_tool_message,
    _build_tool_result_message,
    _call_llm_with_tools,
    _sse,
    _stream_final_response,
)
from .snapshot import (
    build_aggregate_snapshot_light,
    build_portfolio_snapshot,
    build_portfolio_snapshot_light,
)
from .streaming import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_AGENTIC,
    stream_copilot_response,
    stream_copilot_response_agentic,
)

__all__ = [
    "CopilotChatRequest",
    "CopilotConfig",
    "CopilotMessage",
    "_DEFAULT_MODELS",
    "_build_assistant_tool_message",
    "_build_tool_result_message",
    "_call_llm_with_tools",
    "_decrypt_api_key",
    "_get_model",
    "_get_server_api_key",
    "_sse",
    "_stream_final_response",
    "build_aggregate_snapshot_light",
    "build_portfolio_snapshot",
    "build_portfolio_snapshot_light",
    "encrypt_api_key",
    "is_copilot_available",
    "resolve_copilot_config",
    "stream_copilot_response",
    "stream_copilot_response_agentic",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_AGENTIC",
]
