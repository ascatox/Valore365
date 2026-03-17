"""Request / response models for the Copilot."""

from __future__ import annotations

from pydantic import BaseModel


class CopilotMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class CopilotChatRequest(BaseModel):
    portfolio_id: int
    portfolio_ids: list[int] | None = None
    messages: list[CopilotMessage]
