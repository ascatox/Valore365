import json
import time

from app.copilot import streaming
from app.copilot.config import CopilotConfig
from app.copilot.models import CopilotMessage


def _events(chunks):
    return [
        json.loads(c[len("data: "):])
        for c in chunks
        if c.startswith("data: ")
    ]


def test_run_with_heartbeat_yields_keepalives_while_waiting():
    def slow(value):
        time.sleep(0.25)
        return value * 2

    gen = streaming._run_with_heartbeat(slow, 21, interval=0.05)
    chunks = []
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as stop:
        result = stop.value

    assert result == 42
    assert chunks
    assert all(c == streaming._HEARTBEAT for c in chunks)


def test_agentic_stream_sends_first_byte_and_keepalives(monkeypatch):
    def slow_llm(*_args):
        time.sleep(0.25)
        return [], "Risposta finale"

    monkeypatch.setattr(streaming, "_call_llm_with_tools", slow_llm)
    monkeypatch.setattr(streaming, "HEARTBEAT_INTERVAL_S", 0.05)
    monkeypatch.setattr(streaming, "format_tools_for_provider", lambda *a, **k: [])

    config = CopilotConfig(provider="openai", model="test-model", api_key="test-key")
    chunks = list(
        streaming.stream_copilot_response_agentic(
            config,
            {},
            [CopilotMessage(role="user", content="ciao")],
            repo=None,
            perf_service=None,
            portfolio_id=1,
            user_id="u",
        )
    )

    events = _events(chunks)
    assert events[0]["type"] == "thinking"
    assert streaming._HEARTBEAT in chunks
    assert {"type": "text_delta", "content": "Risposta finale"} in events
    assert events[-1]["type"] == "done"
