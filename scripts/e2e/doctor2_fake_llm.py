"""Fake OpenAI-compatible LLM for the Doctor 2.0 E2E (no network, deterministic).

The backend runs with COPILOT_PROVIDER=openai and OPENAI_BASE_URL pointing here,
so the REAL agentic loop of the backend (tool allowlist, preview_policy, the
`policy_draft` SSE event with the server-issued confirmation token) is
exercised; only the model's decisions are scripted:

- a user message containing "60/40" or "bozza"  -> tool call `preview_policy`
  with a 60/40 draft (then a short text answer after the tool result);
- a user message containing "pensione"/"rendita" -> text routing to /fire;
- a user message containing "ERRORE LLM", or the switch `POST /__fail` (body
  "on"/"off") -> HTTP 500 (provider failure);
- anything else -> a short text answer.

Only the Python standard library is used. Usage:
    python scripts/e2e/doctor2_fake_llm.py --port 8765
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"fail": False, "requests": 0}

DRAFT_DOCUMENT = {
    "schema_version": 1,
    "rules": [
        {"rule_id": "azioni-60", "metric_code": "equity_weight_pct", "operator": "range",
         "min_value": 55, "max_value": 65, "severity": "high", "label": "Azioni 55–65%"},
        {"rule_id": "obbligazioni-40", "metric_code": "bond_weight_pct", "operator": "range",
         "min_value": 35, "max_value": 45, "severity": "medium", "label": "Obbligazioni 35–45%"},
        {"rule_id": "max-single", "metric_code": "max_single_position_pct", "operator": "max",
         "max_value": 35, "severity": "high", "label": "Max singolo ETF"},
    ],
}


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):
                return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            return str(content or "")
    return ""


def _completion(message: dict, finish_reason: str) -> dict:
    return {
        "id": f"chatcmpl-fake-{STATE['requests']}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "fake-e2e",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _decide(body: dict) -> dict:
    messages = body.get("messages") or []
    last = messages[-1] if messages else {}
    if last.get("role") == "tool":
        return _completion({
            "role": "assistant",
            "content": (
                "Ho preparato una bozza 60/40 (azioni 55–65%, obbligazioni 35–45%, max singolo ETF 35%). "
                "Trovi l'anteprima qui sotto: non è salvata finché non premi «Conferma e salva»."
            ),
        }, "stop")
    text = _last_user_text(messages).lower()
    if "60/40" in text or "bozza" in text:
        tools = {t.get("function", {}).get("name") for t in body.get("tools") or []}
        if "preview_policy" in tools:
            return _completion({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_preview_1",
                    "type": "function",
                    "function": {
                        "name": "preview_policy",
                        "arguments": json.dumps({"document": DRAFT_DOCUMENT, "name": "Policy 60/40"}),
                    },
                }],
            }, "tool_calls")
    if "pensione" in text or "rendita" in text or "capitale" in text:
        return _completion({
            "role": "assistant",
            "content": (
                "Per capitale, rendita e pensione usa la pagina FIRE: [Apri FIRE](/fire). "
                "Qui nel Doctor posso aiutarti con composizione e limiti personali."
            ),
        }, "stop")
    return _completion({"role": "assistant", "content": "Risposta di prova del Copilot (LLM finto E2E)."}, "stop")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quiet
        pass

    def _send(self, status: int, payload: dict | str, content_type: str = "application/json") -> None:
        data = payload if isinstance(payload, str) else json.dumps(payload)
        raw = data.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path.startswith("/__state"):
            self._send(200, STATE)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if self.path.startswith("/__fail"):
            STATE["fail"] = raw.decode().strip().lower() in {"on", "1", "true"}
            self._send(200, STATE)
            return
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send(404, {"error": {"message": "not found"}})
            return
        STATE["requests"] += 1
        body = json.loads(raw or b"{}")
        if STATE["fail"] or "errore llm" in _last_user_text(body.get("messages") or []).lower():
            self._send(500, {"error": {"message": "fake provider failure", "type": "server_error"}})
            return
        completion = _decide(body)
        if body.get("stream"):
            message = completion["choices"][0]["message"]
            chunk = {"id": completion["id"], "object": "chat.completion.chunk", "created": completion["created"],
                     "model": "fake-e2e",
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": message.get("content") or ""},
                                  "finish_reason": None}]}
            end = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            stream = f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(end)}\n\ndata: [DONE]\n\n"
            self._send(200, stream, "text/event-stream")
            return
        self._send(200, completion)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
