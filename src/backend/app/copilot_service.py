"""Backward-compatible facade -- imports from copilot package."""
from .copilot import *  # noqa: F401,F403
from .copilot import (
    CopilotChatRequest,
    CopilotMessage,
    build_aggregate_snapshot_light,
    build_portfolio_snapshot,
    build_portfolio_snapshot_light,
    encrypt_api_key,
    is_copilot_available,
    resolve_copilot_config,
    stream_copilot_response,
    stream_copilot_response_agentic,
    _get_model,
)
