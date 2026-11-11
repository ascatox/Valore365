"""TASK-82: scripts/auditor/mcp_call.py (chiamata in processo dei tool MCP per l'agente settimanale).

Senza database: guardia sul DATABASE_URL, elenco dei tool, esito ed errori di ``call_tool`` con un
repository finto, registro delle chiamate. L'esecuzione reale sul seed è nella prova a secco
(docs/auditor/reports/2026-11-11-prova-a-secco.md).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.mcp_server.tools import EXPOSED_TOOL_NAMES

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "auditor" / "mcp_call.py"
ENV_KEYS = ("DATABASE_URL", "APP_ENV", "CLERK_AUTH_ENABLED", "JUSTETF_ENABLED",
            "JUSTETF_XRAY_AUTO_ENRICH_ENABLED", "FINANCE_MAX_RETRIES", "FINANCE_REQUEST_TIMEOUT_SECONDS")


@pytest.fixture()
def mcp_call(monkeypatch, tmp_path):
    # main() scrive in os.environ (setdefault delle impostazioni): ambiente ripristinato a fine test.
    import os

    saved = {key: os.environ.get(key) for key in ENV_KEYS}
    monkeypatch.setenv("MCP_CALL_LOG", str(tmp_path / "calls.jsonl"))
    spec = importlib.util.spec_from_file_location("auditor_mcp_call", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://postgres@/valore365_auditor?host=/tmp/valore365-auditor-agent&port=55450",
    "postgresql+psycopg://postgres:postgres@localhost:5432/valore365",
    "postgresql+psycopg://postgres@127.0.0.1/valore365",
])
def test_local_database_urls_are_accepted(mcp_call, url):
    assert mcp_call._resolve_database_url(url) == url


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://u:p@db.example.com:5432/prod",
    "postgresql+psycopg://u@/prod?host=db.internal&port=5432",
])
def test_remote_database_urls_are_refused(mcp_call, url):
    with pytest.raises(mcp_call.UsageError, match="non locale"):
        mcp_call._resolve_database_url(url)


def test_main_refuses_remote_database_with_exit_2(mcp_call, capsys):
    code = mcp_call.main(["list_portfolios", "{}", "--database-url", "postgresql://u@prod.example.com/x"])
    assert code == mcp_call.EXIT_USAGE
    assert "non locale" in capsys.readouterr().err


def test_arguments_must_be_a_json_object(mcp_call):
    with pytest.raises(mcp_call.UsageError):
        mcp_call._parse_args_json("[1, 2]")
    with pytest.raises(mcp_call.UsageError):
        mcp_call._parse_args_json("{portfolio_id: 1}")
    assert mcp_call._parse_args_json('{"portfolio_id": 9101}') == {"portfolio_id": 9101}


def test_list_shows_every_exposed_tool(mcp_call, capsys):
    assert mcp_call.main(["--list"]) == mcp_call.EXIT_OK
    out = capsys.readouterr().out
    listed = {line.split("(", 1)[0] for line in out.splitlines() if line and not line.startswith(" ")}
    assert listed == set(EXPOSED_TOOL_NAMES)
    assert "calculate_what_if(portfolio_id: integer" in out


def test_schema_of_unknown_tool_is_a_usage_error(mcp_call, capsys):
    assert mcp_call.main(["--schema", "get_everything"]) == mcp_call.EXIT_USAGE
    assert mcp_call.main(["--schema", "get_positions"]) == mcp_call.EXIT_OK
    assert '"portfolio_id"' in capsys.readouterr().out


class _FakeRepo:
    def list_portfolios(self, user_id):
        assert user_id == "auditor-seed-user"
        return [{"id": 9101, "name": "AUD Bilanciato‮ storico", "base_currency": "EUR"}]


class _FakeDeps:
    repo = _FakeRepo()
    performance_service = None
    finance_client = None


def test_call_tool_returns_sanitized_result_and_logs(mcp_call, tmp_path):
    ok, payload = mcp_call.call_tool(_FakeDeps(), "list_portfolios", {}, "auditor-seed-user")
    assert ok is True
    # sanitize_output toglie i caratteri bidi, come il server prima di rispondere al client
    assert payload == {"portfolios": [{"id": 9101, "name": "AUD Bilanciato storico", "base_currency": "EUR"}]}
    [entry] = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert entry["tool"] == "list_portfolios" and entry["ok"] is True and "result" not in entry


def test_call_tool_reports_tool_errors_like_the_server(mcp_call, tmp_path):
    ok, payload = mcp_call.call_tool(_FakeDeps(), "drop_everything", {}, "auditor-seed-user")
    assert ok is False and payload["error"].startswith("Tool sconosciuto")
    ok, payload = mcp_call.call_tool(_FakeDeps(), "get_positions", {"portfolio_id": "x"}, "auditor-seed-user")
    assert ok is False and payload == {"error": "Argomenti non validi: portfolio_id"}
    entries = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [e["ok"] for e in entries] == [False, False]


def test_batch_prints_one_line_per_call(mcp_call, tmp_path, capsys):
    calls = tmp_path / "calls_in.jsonl"
    calls.write_text('{"tool": "list_portfolios", "args": {}, "label": "a"}\n# commento\n\n'
                     '{"tool": "nope"}\n', encoding="utf-8")
    code = mcp_call.run_batch(_FakeDeps(), str(calls), "auditor-seed-user")
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert code == mcp_call.EXIT_TOOL_ERROR
    assert [(line["tool"], line["ok"]) for line in lines] == [("list_portfolios", True), ("nope", False)]
    assert lines[0]["label"] == "a"
