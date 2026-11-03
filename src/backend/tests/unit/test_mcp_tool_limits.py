"""TASK-33 / V365-013: MCP heavy-tool quota vs concurrency, structured limit errors."""

from __future__ import annotations

import anyio
import pytest

import app.mcp_server.tools as mcp_tools
from app.mcp_server.tools import McpToolLimitError, ToolCallLimits
from app.rate_limit import SlidingWindowRateLimiter


def _limits(*, heavy_max: int = 1, window: int = 60, concurrent: int = 1) -> ToolCallLimits:
    return ToolCallLimits(
        timeout_seconds=5,
        max_concurrent_per_user=concurrent,
        heavy_limiter=SlidingWindowRateLimiter(max_requests=heavy_max, window_seconds=window),
    )


def _run(limits: ToolCallLimits, name: str = "get_monte_carlo"):
    return anyio.run(mcp_tools._run_bounded, limits, object(), name, {"portfolio_id": 1}, "u")


def test_busy_rejection_does_not_consume_heavy_quota(monkeypatch):
    monkeypatch.setattr(mcp_tools, "run_tool_sync", lambda *a: {"ok": True})
    limits = _limits(heavy_max=1, concurrent=1)
    assert limits.try_acquire("u")  # another call is in flight
    with pytest.raises(McpToolLimitError) as exc_info:
        _run(limits)
    assert exc_info.value.code == "concurrency_busy"
    assert 0 < exc_info.value.retry_after_s <= 5
    limits.release("u")
    # The quota (1 call) is still available.
    assert _run(limits) == {"ok": True}
    assert limits.in_flight("u") == 0


def test_heavy_quota_error_is_structured_and_releases_slot(monkeypatch):
    monkeypatch.setattr(mcp_tools, "run_tool_sync", lambda *a: {"ok": True})
    limits = _limits(heavy_max=1, window=60, concurrent=1)
    assert _run(limits) == {"ok": True}
    with pytest.raises(McpToolLimitError) as exc_info:
        _run(limits)
    err = exc_info.value
    assert err.code == "heavy_quota"
    assert 1 <= err.retry_after_s <= 60
    assert "qualche minuto" not in str(err)
    assert "60 secondi" in str(err) or "1 minuto" in str(err)
    # The concurrency slot taken before the quota check is given back.
    assert limits.in_flight("u") == 0
    # Light tools are not affected by the heavy quota.
    assert _run(limits, "get_portfolio_summary") == {"ok": True}


def test_sliding_window_retry_after_uses_oldest_entry(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: clock["now"])
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    assert limiter.retry_after("k") == 0
    assert limiter.allow("k")
    clock["now"] = 1010.0
    assert limiter.allow("k")
    clock["now"] = 1020.0
    assert not limiter.allow("k")
    # Oldest entry (t=1000) leaves the window at t=1060 -> 40 s from now.
    assert limiter.retry_after("k") == 40


def test_limit_error_becomes_machine_readable_call_tool_result():
    err = McpToolLimitError("Troppe richieste in corso, riprova tra poco", code="concurrency_busy", retry_after_s=2)
    result = err.to_call_tool_result()
    assert result.isError is True
    assert result.structuredContent == {
        "error": {
            "code": "concurrency_busy",
            "message": "Troppe richieste in corso, riprova tra poco",
            "retry_after_s": 2,
        }
    }
    text = result.content[0].text
    assert "Troppe richieste in corso" in text
    assert "concurrency_busy" in text and "retry_after_s" in text
