"""Motore dell'Auditor (TASK-73): registro, contesto, esecutore, report e CLI.

Solo regole e tool finti: nessuna dipendenza dai moduli di regole di TASK-74…77 né dal database.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jsonschema
import pytest

from app.mcp_server.tools import McpToolError
from app.services.auditor import __main__ as cli
from app.services.auditor import context as context_module
from app.services.auditor import registry, report as report_module, runner
from app.services.auditor.context import (
    AGGREGATE_TOOL_OF,
    PERFORMANCE_AUDIT_TOOL,
    TRANSACTIONS_TOOL,
    AuditContext,
    AuditorOfflineError,
    AuditToolError,
    OfflineFinanceClient,
    ScopeSelectionError,
    canonical_key,
    discover_scopes,
    scope_key,
    scoped_tool_args,
)
from app.services.auditor.registry import Rule, RuleRegistrationError, load_rules, rule_from_declaration, select_rules
from app.services.auditor.report import (
    ReportValidationError,
    build_report,
    privacy_rows,
    report_to_json,
    report_to_markdown,
    validate_report,
)
from app.services.auditor.runner import RunOptions, evaluate_rule, exit_code_for, run_audit

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_SCHEMA = REPO_ROOT / "docs" / "auditor" / "schemas" / "report.schema.json"
DOCS_EXAMPLE = REPO_ROOT / "docs" / "auditor" / "fixtures" / "report-example.json"
ENGINE_SCHEMA = Path(report_module.__file__).with_name("report_schema.json")


# -- tool e dipendenze finti ---------------------------------------------------------------------

class FakeRepo:
    def __init__(self, transactions=None) -> None:
        self.transactions = transactions or {}
        self.calls: list[tuple[int, str]] = []

    def list_transactions(self, portfolio_id: int, user_id: str):
        self.calls.append((portfolio_id, user_id))
        if portfolio_id not in self.transactions:
            raise ValueError("Portfolio non trovato")
        return self.transactions[portfolio_id]


class FakeDeps:
    """Al posto di ToolDependencies: ``responses`` = {canonical_key: dict | Exception | callable}."""

    def __init__(self, responses=None, *, repo=None) -> None:
        self.responses = dict(responses or {})
        self.repo = repo or FakeRepo()
        self.performance_service = object()
        self.finance_client = OfflineFinanceClient()
        self.calls: list[tuple[str, dict, str]] = []
        self.lock = threading.Lock()

    def set(self, tool, args, value):
        self.responses[canonical_key(tool, args)] = value
        return self


def fake_run_tool_sync(deps: FakeDeps, name: str, args: dict, user_id: str):
    with deps.lock:
        deps.calls.append((name, dict(args), user_id))
    key = canonical_key(name, args)
    if key not in deps.responses:
        raise McpToolError(f"risposta finta mancante: {key}")
    value = deps.responses[key]
    if callable(value):
        value = value()
    if isinstance(value, BaseException):
        raise value
    return value


_REAL_RUN_TOOL_SYNC = context_module.mcp_tools.run_tool_sync


@pytest.fixture(autouse=True)
def _fake_tools(monkeypatch):
    monkeypatch.setattr(context_module.mcp_tools, "run_tool_sync", fake_run_tool_sync)


def portfolios_deps(portfolios, positions=None, **kwargs) -> FakeDeps:
    deps = FakeDeps(**kwargs)
    deps.set("list_portfolios", {}, {"portfolios": portfolios})
    for pid, rows in (positions or {}).items():
        deps.set("get_positions", {"portfolio_id": pid}, {"portfolio_id": pid, "positions": rows})
    return deps


def make_ctx(deps: FakeDeps, user_id: str = "user-1", mode: str = "local") -> AuditContext:
    return AuditContext(deps, user_id, run_id="a" * 32, mode=mode)


THREE_EUR = [
    {"id": 1, "name": "Uno", "base_currency": "EUR"},
    {"id": 2, "name": "Due", "base_currency": "EUR"},
    {"id": 3, "name": "Tre", "base_currency": "USD"},
]


# -- regole finte --------------------------------------------------------------------------------

def ok_outcome(**extra):
    return {"status": "pass", "reason_code": None, "reason": None, "evidence": [], **extra}


def evidence(tool="get_positions", observed=1.0, expected=1.0, **extra):
    return {"tool": tool, "args": {"portfolio_id": 1}, "path": "positions[0].weight", "observed": observed,
            "expected": expected, "tolerance": 0.01, "note": None, **extra}


def declaration(rule_id="A-TEST-ONE", **overrides):
    base = {
        "id": rule_id,
        "group": rule_id.split("-", 1)[0],
        "title": "Una regola di prova",
        "area": "stress",
        "severity": "P1",
        "findings": ["V365-002"],
        "scopes": ["portfolio"],
        "tools": ["get_positions"],
        "check": lambda ctx, scope: ok_outcome(),
    }
    base.update(overrides)
    return base


def make_rule(rule_id="A-TEST-ONE", check=None, **overrides) -> Rule:
    if check is not None:
        overrides["check"] = check
    return rule_from_declaration(declaration(rule_id, **overrides))


def install_module(monkeypatch, name: str, rules) -> str:
    module = types.ModuleType(name)
    if rules is not None:
        module.RULES = rules
    monkeypatch.setitem(sys.modules, name, module)
    return name


# ================================================================================================
# Registro
# ================================================================================================

def test_rule_modules_are_the_contract_ones():
    from app.services.auditor.rules import RULE_MODULES

    assert RULE_MODULES == ("stress_classification", "rebalance_simulation", "costs_income", "consistency")


def test_rule_from_declaration_builds_rule_with_defaults():
    rule = make_rule()
    assert rule.id == "A-TEST-ONE" and rule.group == "A"
    assert rule.findings == ("V365-002",) and rule.scopes == ("portfolio",) and rule.tools == ("get_positions",)
    assert rule.timeout_s == registry.DEFAULT_RULE_TIMEOUT_S and rule.known_defect is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "a-lower"},
        {"id": "A_UNDERSCORE"},
        {"id": "B-WRONG-PREFIX"},
        {"group": "E"},
        {"severity": "P3"},
        {"area": "unknown"},
        {"scopes": ["galaxy"]},
        {"scopes": []},
        {"title": "   "},
        {"check": "non chiamabile"},
        {"timeout_s": 0},
        {"timeout_s": -1},
        {"timeout_s": 301},
        {"timeout_s": True},
        {"known_defect": "BUG-1"},
        {"findings": "V365-002"},
        {"tools": []},
        {"extra_key": 1},
    ],
)
def test_rule_from_declaration_rejects_invalid(overrides):
    with pytest.raises(RuleRegistrationError):
        rule_from_declaration(declaration(**overrides))


def test_rule_from_declaration_rejects_missing_key():
    decl = declaration()
    del decl["check"]
    with pytest.raises(RuleRegistrationError, match="check"):
        rule_from_declaration(decl)


def test_rule_from_declaration_accepts_optionals():
    rule = make_rule(timeout_s=300, known_defect="TASK-41", findings=[])
    assert rule.timeout_s == 300.0 and rule.known_defect == "TASK-41" and rule.findings == ()


def test_load_rules_discovers_declarations_sorted(monkeypatch):
    m1 = install_module(monkeypatch, "fake_auditor.rules_one", [declaration("B-ZETA"), declaration("B-ALPHA")])
    m2 = install_module(monkeypatch, "fake_auditor.rules_two", [declaration("A-MIDDLE")])
    rules = load_rules([m1, m2])
    assert [r.id for r in rules] == ["A-MIDDLE", "B-ALPHA", "B-ZETA"]


def test_load_rules_ignores_missing_module_with_warning(monkeypatch, caplog):
    present = install_module(monkeypatch, "fake_auditor.rules_present", [declaration("C-PRESENT", area="costs")])
    with caplog.at_level("WARNING"):
        rules = load_rules(["not_yet_written_group", present])
    assert [r.id for r in rules] == ["C-PRESENT"]
    assert "not_yet_written_group" in caplog.text


def test_load_rules_propagates_other_import_errors(tmp_path, monkeypatch):
    pkg = tmp_path / "fake_auditor_broken_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "broken.py").write_text("import a_dependency_that_does_not_exist_xyz\nRULES = []\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError) as excinfo:
        load_rules(["fake_auditor_broken_pkg.broken"])
    assert excinfo.value.name == "a_dependency_that_does_not_exist_xyz"


def test_load_rules_rejects_duplicates_and_missing_rules(monkeypatch):
    m1 = install_module(monkeypatch, "fake_auditor.dup_one", [declaration("A-SAME")])
    m2 = install_module(monkeypatch, "fake_auditor.dup_two", [declaration("A-SAME")])
    with pytest.raises(RuleRegistrationError, match="duplicato"):
        load_rules([m1, m2])
    m3 = install_module(monkeypatch, "fake_auditor.no_rules", None)
    with pytest.raises(RuleRegistrationError, match="RULES"):
        load_rules([m3])
    m4 = install_module(monkeypatch, "fake_auditor.bad_decl", [declaration("A-BAD", severity="P9")])
    with pytest.raises(RuleRegistrationError, match="fake_auditor.bad_decl"):
        load_rules([m4])


def test_load_rules_default_tolerates_partial_rule_set():
    # I moduli dei gruppi possono mancare o essere presenti (TASK-74…77 in parallelo): mai un errore.
    rules = load_rules()
    assert all(isinstance(r, Rule) for r in rules)
    assert [r.id for r in rules] == sorted(r.id for r in rules)


def test_select_rules_filters_in_and_and_rejects_unknown():
    rules = [make_rule("A-ONE"), make_rule("A-TWO"), make_rule("B-ONE")]
    assert [r.id for r in select_rules(rules, groups=["A"])] == ["A-ONE", "A-TWO"]
    assert [r.id for r in select_rules(rules, rule_ids=["B-ONE", "A-TWO"])] == ["A-TWO", "B-ONE"]
    assert [r.id for r in select_rules(rules, groups=["A"], rule_ids=["B-ONE", "A-TWO"])] == ["A-TWO"]
    assert [r.id for r in select_rules(rules)] == ["A-ONE", "A-TWO", "B-ONE"]
    with pytest.raises(RuleRegistrationError):
        select_rules(rules, groups=["Z"])
    with pytest.raises(RuleRegistrationError):
        select_rules(rules, rule_ids=["A-MISSING"])


# ================================================================================================
# Contesto
# ================================================================================================

def test_canonical_key_and_scope_key():
    assert canonical_key("t", {"b": 1, "a": "è"}) == '{"args":{"a":"è","b":1},"tool":"t"}'
    assert scope_key({"kind": "portfolio", "portfolio_id": 9101}) == "portfolio:9101"
    assert scope_key({"kind": "aggregate", "portfolio_ids": [9101, 9102, 9103]}) == "aggregate:9101,9102,9103"
    assert scope_key({"kind": "instrument", "portfolio_id": 9103, "symbol": "XGLD.DE"}) == "instrument:9103:XGLD.DE"
    assert scope_key({"kind": "user", "portfolio_ids": [1]}) == "user"


def test_scoped_tool_args_table():
    pf = {"kind": "portfolio", "portfolio_id": 7}
    ins = {"kind": "instrument", "portfolio_id": 7, "symbol": "X"}
    agg = {"kind": "aggregate", "portfolio_ids": [7, 8]}
    assert scoped_tool_args("get_positions", pf) == ("get_positions", {"portfolio_id": 7})
    assert scoped_tool_args("search_asset_info", ins, {"symbol": "X"}) == (
        "search_asset_info", {"portfolio_id": 7, "symbol": "X"})
    assert scoped_tool_args("get_stress_test", agg) == ("get_aggregate_stress_test", {"portfolio_ids": [7, 8]})
    assert scoped_tool_args("read_doctor_metrics", agg) == (
        "read_doctor_metrics", {"portfolio_id": 7, "portfolio_ids": [7, 8]})
    for tool in AGGREGATE_TOOL_OF:
        assert scoped_tool_args(tool, agg)[0] == AGGREGATE_TOOL_OF[tool]
    with pytest.raises(ValueError):
        scoped_tool_args("get_positions", agg, {"x": 1})
    with pytest.raises(ValueError):
        scoped_tool_args("get_cash_balance", agg)
    with pytest.raises(ValueError):
        scoped_tool_args("get_positions", {"kind": "user", "portfolio_ids": [1]})
    with pytest.raises(ValueError):
        scoped_tool_args("get_aggregate_positions", pf)


def test_call_memoizes_and_returns_deep_copies():
    deps = FakeDeps().set("get_positions", {"portfolio_id": 1}, {"positions": [{"symbol": "A", "weight": 50.0}]})
    ctx = make_ctx(deps)
    first = ctx.call("get_positions", {"portfolio_id": 1})
    first["positions"][0]["weight"] = -1
    second = ctx.scoped("get_positions", {"kind": "portfolio", "portfolio_id": 1})
    assert second["positions"][0]["weight"] == 50.0
    assert len(deps.calls) == 1
    assert deps.calls[0] == ("get_positions", {"portfolio_id": 1}, "user-1")
    assert ctx.call_stats() == {"total": 1, "cache_hits": 1, "errors": 0, "by_tool": {"get_positions": 1}}


def test_call_applies_sanitize_output():
    deps = FakeDeps().set("get_cash_balance", {"portfolio_id": 1},
                          {"value": float("nan"), "when": datetime(2026, 1, 2, tzinfo=UTC), "text": "a‮b"})
    result = make_ctx(deps).call("get_cash_balance", {"portfolio_id": 1})
    assert result["value"] is None
    assert isinstance(result["when"], str)
    assert result["text"] == "ab"


def test_call_errors_become_memoized_audit_tool_errors():
    deps = FakeDeps()
    deps.set("get_stress_test", {"portfolio_id": 1}, McpToolError("Portafoglio non trovato"))
    deps.set("get_cost_breakdown", {"portfolio_id": 1}, RuntimeError("db down"))
    ctx = make_ctx(deps)
    for _ in range(2):
        with pytest.raises(AuditToolError) as excinfo:
            ctx.call("get_stress_test", {"portfolio_id": 1})
        assert excinfo.value.tool == "get_stress_test"
        assert excinfo.value.args == {"portfolio_id": 1}
        assert excinfo.value.message == "Portafoglio non trovato"
    with pytest.raises(AuditToolError, match="RuntimeError: db down"):
        ctx.call("get_cost_breakdown", {"portfolio_id": 1})
    assert ctx.try_call("get_stress_test", {"portfolio_id": 1}) == {
        "ok": False, "result": None, "error": "Portafoglio non trovato"}
    assert len(deps.calls) == 2
    stats = ctx.call_stats()
    assert stats["total"] == 2 and stats["errors"] == 2 and stats["cache_hits"] == 2


def test_try_call_success_shares_memo():
    deps = FakeDeps().set("calculate_what_if", {"portfolio_id": 1, "action": "buy"}, {"ok": 1})
    ctx = make_ctx(deps)
    assert ctx.try_call("calculate_what_if", {"action": "buy", "portfolio_id": 1}) == {
        "ok": True, "result": {"ok": 1}, "error": None}
    assert ctx.call("calculate_what_if", {"portfolio_id": 1, "action": "buy"}) == {"ok": 1}
    assert len(deps.calls) == 1


def test_context_goes_through_real_run_tool_sync(monkeypatch):
    import app.mcp_server.tools as real_tools

    monkeypatch.setattr(context_module.mcp_tools, "run_tool_sync", _REAL_RUN_TOOL_SYNC)
    assert context_module.mcp_tools is real_tools

    class Repo(FakeRepo):
        def list_portfolios(self, user_id):
            return [{"id": 4, "name": "Quattro\u200b", "base_currency": "EUR", "owner": user_id}]

    ctx = make_ctx(FakeDeps(repo=Repo()))
    assert ctx.portfolios() == [{"id": 4, "name": "Quattro", "base_currency": "EUR"}]
    with pytest.raises(AuditToolError, match="Tool sconosciuto"):
        ctx.call("drop_everything", {})
    with pytest.raises(AuditToolError):
        ctx.call("get_positions", {"portfolio_id": "uno"})


def test_memo_deduplicates_in_flight_calls():
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(5)
        return {"positions": []}

    deps = FakeDeps().set("get_positions", {"portfolio_id": 1}, slow)
    ctx = make_ctx(deps)
    results = []
    threads = [threading.Thread(target=lambda: results.append(ctx.call("get_positions", {"portfolio_id": 1})))
               for _ in range(4)]
    for t in threads:
        t.start()
    assert started.wait(5)
    time.sleep(0.05)
    release.set()
    for t in threads:
        t.join(5)
    assert results == [{"positions": []}] * 4
    assert len(deps.calls) == 1
    assert ctx.call_stats()["cache_hits"] == 3


def test_memo_is_per_context():
    deps = FakeDeps().set("list_portfolios", {}, {"portfolios": []})
    make_ctx(deps).portfolios()
    make_ctx(deps).portfolios()
    assert len(deps.calls) == 2


def test_transactions_direct_read_shape_order_and_memo():
    raw = [
        {"id": 5, "portfolio_id": 1, "asset_id": 10, "side": "buy", "trade_at": datetime(2026, 3, 1, 23, 30),
         "quantity": 2, "price": 10.5, "fees": None, "taxes": 0, "trade_currency": "EUR", "notes": "segreto",
         "symbol": "VWCE.DE", "asset_name": "Vanguard"},
        types.SimpleNamespace(id=9, portfolio_id=1, asset_id=None, side=types.SimpleNamespace(value="deposit"),
                              trade_at=datetime(2026, 3, 1, 23, 30, tzinfo=UTC), quantity=1.0, price=100.0,
                              fees=0.0, taxes=0.0, trade_currency="EUR", notes=None, symbol=None, asset_name=None),
        {"id": 7, "asset_id": 10, "side": "sell", "trade_at": "2026-04-01T10:00:00+02:00", "quantity": 1,
         "price": 11, "fees": 1, "taxes": 0.5, "trade_currency": "EUR", "symbol": "VWCE.DE"},
    ]
    repo = FakeRepo({1: raw})
    ctx = make_ctx(FakeDeps(repo=repo))
    rows = ctx.transactions(1)
    assert [r["id"] for r in rows] == [7, 9, 5]
    assert set(rows[0]) == {"id", "asset_id", "symbol", "side", "trade_at", "trade_date", "quantity", "price",
                            "fees", "taxes", "trade_currency"}
    assert rows[0]["trade_date"] == "2026-04-01" and rows[0]["trade_at"].startswith("2026-04-01T08:00:00")
    assert rows[1]["side"] == "deposit" and rows[1]["asset_id"] is None
    assert rows[2]["fees"] == 0.0 and rows[2]["quantity"] == 2.0 and isinstance(rows[2]["quantity"], float)
    rows[0]["price"] = 0
    assert ctx.transactions(1)[0]["price"] == 11.0
    assert repo.calls == [(1, "user-1")]
    assert ctx.call_stats()["by_tool"] == {TRANSACTIONS_TOOL: 1}
    with pytest.raises(AuditToolError) as excinfo:
        ctx.transactions(99)
    assert excinfo.value.tool == TRANSACTIONS_TOOL and excinfo.value.args == {"portfolio_id": 99}


def test_performance_audit_single_and_aggregate(monkeypatch):
    import app.services.performance_audit as perf_audit

    seen = []

    def fake_export(perf_service, portfolio_ids, user_id, **kwargs):
        seen.append((portfolio_ids, user_id, kwargs))
        return {"twr": float("inf"), "portfolio_ids": [portfolio_ids]}

    monkeypatch.setattr(perf_audit, "build_performance_audit_export", fake_export)
    deps = FakeDeps().set("get_aggregate_performance_audit", {"portfolio_ids": [1, 2]}, {"agg": True})
    ctx = make_ctx(deps)
    assert ctx.performance_audit([1]) == {"twr": None, "portfolio_ids": [1]}
    ctx.performance_audit([1])
    assert seen == [(1, "user-1", {"period": "1y", "max_flows": 200, "offset": 0})]
    assert ctx.performance_audit([2, 1]) == {"agg": True}
    assert deps.calls == [("get_aggregate_performance_audit", {"portfolio_ids": [1, 2]}, "user-1")]
    assert ctx.call_stats()["by_tool"] == {PERFORMANCE_AUDIT_TOOL: 1, "get_aggregate_performance_audit": 1}

    with pytest.raises(AuditToolError) as excinfo:
        ctx.performance_audit([3, 4])
    assert excinfo.value.tool == PERFORMANCE_AUDIT_TOOL and excinfo.value.args == {"portfolio_ids": [3, 4]}

    def broken_export(*args, **kwargs):
        raise ValueError("Portfolio non trovato")

    monkeypatch.setattr(perf_audit, "build_performance_audit_export", broken_export)
    with pytest.raises(AuditToolError) as excinfo:
        ctx.performance_audit([5])
    assert excinfo.value.tool == PERFORMANCE_AUDIT_TOOL and "Portfolio non trovato" in excinfo.value.message


def test_offline_finance_client_and_dependencies():
    client = OfflineFinanceClient()
    with pytest.raises(AuditorOfflineError):
        client.get_etf_top_holdings("VWCE.DE")
    with pytest.raises(AuditorOfflineError):
        client.get_quote("X")
    with pytest.raises(AttributeError):
        client._private  # noqa: B018
    deps = context_module.build_tool_dependencies(offline=True)
    assert isinstance(deps.finance_client, OfflineFinanceClient)
    assert deps.performance_service.repo is deps.repo


def test_discover_scopes_portfolio_aggregate_instrument_user():
    positions = {
        1: [{"symbol": "VWCE.DE"}, {"symbol": "XGLD.DE"}],
        2: [{"symbol": "AGGH.MI"}],
        3: [],
    }
    deps = portfolios_deps(THREE_EUR, positions)
    scopes = discover_scopes(make_ctx(deps))
    keys = [scope_key(s) for s in scopes]
    assert keys == sorted(keys)
    assert keys == [
        "aggregate:1,2",
        "instrument:1:VWCE.DE", "instrument:1:XGLD.DE", "instrument:2:AGGH.MI",
        "portfolio:1", "portfolio:2", "portfolio:3",
        "user",
    ]
    assert {"kind": "user", "portfolio_ids": [1, 2, 3]} in scopes

    only = discover_scopes(make_ctx(deps), portfolio_ids=[3, 1], include_instruments=False)
    assert [scope_key(s) for s in only] == ["portfolio:1", "portfolio:3", "user"]
    none = discover_scopes(make_ctx(deps), include_aggregate=False, include_instruments=False)
    assert [scope_key(s) for s in none] == ["portfolio:1", "portfolio:2", "portfolio:3", "user"]
    with pytest.raises(ScopeSelectionError):
        discover_scopes(make_ctx(deps), portfolio_ids=[1, 42])


def test_discover_scopes_caps_aggregate_and_survives_positions_error():
    many = [{"id": i, "name": f"P{i}", "base_currency": "EUR"} for i in range(1, 24)]
    deps = portfolios_deps(many)
    for i in range(1, 24):
        deps.set("get_positions", {"portfolio_id": i}, McpToolError("boom"))
    scopes = discover_scopes(make_ctx(deps))
    aggregates = [s for s in scopes if s["kind"] == "aggregate"]
    assert aggregates == [{"kind": "aggregate", "portfolio_ids": list(range(1, 21))}]
    assert not [s for s in scopes if s["kind"] == "instrument"]


# ================================================================================================
# Esecutore
# ================================================================================================

PF1 = {"kind": "portfolio", "portfolio_id": 1}


def test_evaluate_rule_pass_fail_skip():
    pass_rule = make_rule(check=lambda ctx, scope: ok_outcome(evidence=[evidence()]))
    result = evaluate_rule(pass_rule, None, PF1, timeout_s=5)
    assert result["status"] == "pass" and result["reason_code"] is None
    assert result["scope_key"] == "portfolio:1" and result["evidence"][0]["observed"] == 1.0
    assert result["evidence_truncated"] is False and result["duration_ms"] >= 0

    fail_rule = make_rule(check=lambda ctx, scope: {"status": "fail", "reason_code": "invariant_violated",
                                                     "reason": "Somma sbagliata.", "evidence": [evidence(observed=2)]})
    assert evaluate_rule(fail_rule, None, PF1, timeout_s=5)["status"] == "fail"

    skip_rule = make_rule(check=lambda ctx, scope: {"status": "skip", "reason_code": "empty_portfolio",
                                                     "reason": "Portafoglio vuoto.", "evidence": []})
    result = evaluate_rule(skip_rule, None, PF1, timeout_s=5)
    assert (result["status"], result["reason_code"]) == ("skip", "empty_portfolio")


def test_evaluate_rule_exception_gives_error_with_exception_name():
    def boom(ctx, scope):
        raise ZeroDivisionError("x" * 1000)

    result = evaluate_rule(make_rule(check=boom), None, PF1, timeout_s=5)
    assert (result["status"], result["reason_code"]) == ("error", "exception")
    assert result["reason"].startswith("ZeroDivisionError: ")
    assert len(result["reason"]) <= len("ZeroDivisionError: ") + 301


def test_evaluate_rule_timeout_gives_dedicated_code_and_does_not_block():
    release = threading.Event()

    def slow(ctx, scope):
        release.wait(10)
        return ok_outcome()

    started = time.monotonic()
    result = evaluate_rule(make_rule(check=slow), None, PF1, timeout_s=0.2)
    elapsed = time.monotonic() - started
    release.set()
    assert (result["status"], result["reason_code"]) == ("error", "timeout")
    assert result["reason"] == "Superato il limite di 0.2 s."
    assert elapsed < 2


def test_evaluate_rule_tool_error_from_real_context():
    deps = FakeDeps().set("get_stress_test", {"portfolio_id": 1}, McpToolError("Errore interno"))
    rule = make_rule(check=lambda ctx, scope: ctx.scoped("get_stress_test", scope) and ok_outcome())
    result = evaluate_rule(rule, make_ctx(deps), PF1, timeout_s=5)
    assert (result["status"], result["reason_code"]) == ("error", "tool_error")
    assert "get_stress_test" in result["reason"] and "Errore interno" in result["reason"]
    assert result["evidence"][0]["tool"] == "get_stress_test"
    assert result["evidence"][0]["args"] == {"portfolio_id": 1}


@pytest.mark.parametrize(
    "outcome",
    [
        None,
        {"status": "error", "reason_code": "exception", "reason": "x", "evidence": []},
        {"status": "pass", "reason_code": None, "reason": None},
        {"status": "pass", "reason_code": "invariant_violated", "reason": None, "evidence": []},
        {"status": "skip", "reason_code": "made_up", "reason": "x", "evidence": []},
        {"status": "skip", "reason_code": "empty_portfolio", "reason": None, "evidence": []},
        {"status": "fail", "reason_code": "invariant_violated", "reason": "x", "evidence": []},
        {"status": "fail", "reason_code": "Bad Code", "reason": "x", "evidence": [evidence()]},
        {"status": "pass", "reason_code": None, "reason": None, "evidence": [evidence(observed=object())]},
        {"status": "pass", "reason_code": None, "reason": None, "evidence": [evidence(observed=float("nan"))]},
        {"status": "pass", "reason_code": None, "reason": None, "evidence": [{"tool": "x"}]},
        {"status": "pass", "reason_code": None, "reason": None, "evidence": [], "extra": 1},
    ],
)
def test_evaluate_rule_invalid_outcome(outcome):
    result = evaluate_rule(make_rule(check=lambda ctx, scope: outcome), None, PF1, timeout_s=5)
    assert (result["status"], result["reason_code"]) == ("error", "invalid_outcome")
    assert result["reason"]


def test_evaluate_rule_accepts_rule_specific_fail_code_and_truncates_evidence():
    many = [evidence(observed=i) for i in range(75)]
    rule = make_rule(check=lambda ctx, scope: {"status": "fail", "reason_code": "weights_off",
                                                "reason": "Pesi errati.", "evidence": many})
    result = evaluate_rule(rule, None, PF1, timeout_s=5)
    assert result["reason_code"] == "weights_off"
    assert len(result["evidence"]) == registry.MAX_EVIDENCE_ITEMS and result["evidence_truncated"] is True


def _run_deps() -> FakeDeps:
    return portfolios_deps(THREE_EUR, {1: [{"symbol": "VWCE.DE"}], 2: [], 3: [{"symbol": "SPY"}]})


def test_run_audit_scope_compatibility_order_and_filters():
    seen = []
    lock = threading.Lock()

    def recording(rule_id):
        def check(ctx, scope):
            with lock:
                seen.append((rule_id, scope_key(scope)))
            if scope["kind"] in ("portfolio", "aggregate"):
                ctx.scoped("get_positions", scope)
            return ok_outcome()
        return check

    rules = [
        make_rule("D-INSTR", recording("D-INSTR"), scopes=["instrument"], area="data"),
        make_rule("A-PF", recording("A-PF"), scopes=["portfolio"], severity="P0"),
        make_rule("C-USER", recording("C-USER"), scopes=["user"], area="costs", severity="P2"),
        make_rule("B-AGG", recording("B-AGG"), scopes=["portfolio", "aggregate"], area="rebalance"),
    ]
    ctx = make_ctx(_run_deps())
    report = run_audit(ctx, rules, RunOptions())
    assert seen == [
        ("A-PF", "portfolio:1"), ("A-PF", "portfolio:2"), ("A-PF", "portfolio:3"),
        ("B-AGG", "aggregate:1,2"), ("B-AGG", "portfolio:1"), ("B-AGG", "portfolio:2"), ("B-AGG", "portfolio:3"),
        ("C-USER", "user"),
        ("D-INSTR", "instrument:1:VWCE.DE"), ("D-INSTR", "instrument:3:SPY"),
    ]
    assert report["counts"]["total"] == 10
    # Ordinamento del report: severità, id, scope.
    assert [r["rule_id"] for r in report["results"]][:3] == ["A-PF"] * 3
    assert report["results"][-1]["rule_id"] == "C-USER"
    # get_positions eseguito una volta per portafoglio, poi sempre dalla memo.
    assert report["tool_calls"]["by_tool"]["get_positions"] == 3
    assert report["tool_calls"]["cache_hits"] > 0
    validate_report(report)

    seen.clear()
    filtered = run_audit(make_ctx(_run_deps()), rules,
                         RunOptions(groups=["A", "B"], rule_ids=["B-AGG"], portfolio_ids=[1],
                                    include_aggregate=False))
    assert seen == [("B-AGG", "portfolio:1")]
    assert filtered["options"]["groups"] == ["A", "B"] and filtered["options"]["portfolio_ids"] == [1]
    with pytest.raises(RuleRegistrationError):
        run_audit(make_ctx(_run_deps()), rules, RunOptions(rule_ids=["A-NOPE"]))


def test_run_audit_isolates_failures_between_rules():
    deps = _run_deps().set("get_stress_test", {"portfolio_id": 1}, McpToolError("guasto"))

    def raises(ctx, scope):
        raise KeyError("manca")

    def tool(ctx, scope):
        ctx.scoped("get_stress_test", scope)
        return ok_outcome()

    rules = [
        make_rule("A-RAISES", raises),
        make_rule("A-TOOL", tool),
        make_rule("A-GOOD"),
    ]
    report = run_audit(make_ctx(deps), rules, RunOptions(portfolio_ids=[1], include_aggregate=False,
                                                         include_instruments=False))
    by_rule = {r["rule_id"]: r for r in report["results"]}
    assert (by_rule["A-RAISES"]["status"], by_rule["A-RAISES"]["reason_code"]) == ("error", "exception")
    assert by_rule["A-RAISES"]["reason"].startswith("KeyError: ")
    assert (by_rule["A-TOOL"]["status"], by_rule["A-TOOL"]["reason_code"]) == ("error", "tool_error")
    assert by_rule["A-GOOD"]["status"] == "pass"
    assert report["exit_code"] == 1
    validate_report(report)


def test_run_audit_rule_timeout_cap_and_parallel_workers():
    release = threading.Event()

    def slow(ctx, scope):
        release.wait(10)
        return ok_outcome()

    rules = [make_rule("A-SLOW", slow), make_rule("A-FAST")]
    started = time.monotonic()
    report = run_audit(make_ctx(_run_deps()), rules,
                       RunOptions(rule_timeout_s=0.2, max_workers=4, include_instruments=False,
                                  include_aggregate=False))
    release.set()
    assert time.monotonic() - started < 3
    slow_results = [r for r in report["results"] if r["rule_id"] == "A-SLOW"]
    assert len(slow_results) == 3 and all(r["reason_code"] == "timeout" for r in slow_results)
    assert all(r["status"] == "pass" for r in report["results"] if r["rule_id"] == "A-FAST")
    validate_report(report)


def test_run_audit_deadline_exceeded():
    release = threading.Event()

    def slow(ctx, scope):
        release.wait(10)
        return ok_outcome()

    report = run_audit(make_ctx(_run_deps()), [make_rule("A-SLOW", slow), make_rule("B-LATER", area="rebalance")],
                       RunOptions(max_duration_s=0.3, include_instruments=False, include_aggregate=False))
    release.set()
    assert report["deadline_exceeded"] is True
    codes = [r["reason_code"] for r in report["results"]]
    assert codes.count("deadline_exceeded") == len(codes)
    assert report["counts"]["by_status"]["error"] == 6
    validate_report(report)


def test_run_audit_without_portfolios_has_no_user_scope():
    deps = portfolios_deps([])
    report = run_audit(make_ctx(deps), [make_rule("A-USER", scopes=["user"])], RunOptions())
    assert report["results"] == [] and report["scopes"] == [] and report["exit_code"] == 0


def _result(rule_id="A-X", status="fail", severity="P1", known_defect=None):
    return {"rule_id": rule_id, "status": status, "severity": severity, "known_defect": known_defect}


@pytest.mark.parametrize(
    ("results", "fail_on", "strict", "expected"),
    [
        ([], "P1", False, 0),
        ([_result(status="pass"), _result(status="skip")], "P2", False, 0),
        ([_result(status="fail", severity="P1")], "P1", False, 1),
        ([_result(status="fail", severity="P2")], "P1", False, 0),
        ([_result(status="fail", severity="P2")], "P2", False, 1),
        ([_result(status="error", severity="P0")], "P0", False, 1),
        ([_result(status="error", severity="P1")], "P0", False, 0),
        ([_result(status="fail", severity="P0", known_defect="TASK-41")], "P1", False, 0),
        ([_result(status="fail", severity="P0", known_defect="TASK-41")], "P1", True, 1),
        ([_result(status="error", severity="P0", known_defect="TASK-41")], "P1", False, 1),
    ],
)
def test_exit_code_for(results, fail_on, strict, expected):
    assert exit_code_for({"results": results}, fail_on=fail_on, strict_known=strict) == expected


# ================================================================================================
# Report
# ================================================================================================

def test_engine_schema_is_identical_copy_of_contract():
    assert ENGINE_SCHEMA.read_bytes() == DOCS_SCHEMA.read_bytes()


def test_contract_example_is_valid():
    validate_report(json.loads(DOCS_EXAMPLE.read_text(encoding="utf-8")))


def _mixed_report(**option_overrides):
    deps = _run_deps()

    def failing(ctx, scope):
        return {"status": "fail", "reason_code": "invariant_violated", "reason": "Il totale non torna.",
                "evidence": [evidence(observed=99.5, expected=100.0, note="somma")]}

    def skipping(ctx, scope):
        return {"status": "skip", "reason_code": "no_targets", "reason": "Nessun peso obiettivo | target.",
                "evidence": []}

    def raising(ctx, scope):
        raise RuntimeError("rotta")

    rules = [
        make_rule("A-FAIL", failing, severity="P0", scopes=["portfolio", "aggregate"]),
        make_rule("A-KNOWN", failing, severity="P1", known_defect="TASK-41", scopes=["instrument"], area="data",
                  findings=["V365-008"]),
        make_rule("B-SKIP", skipping, area="rebalance", severity="P2"),
        make_rule("C-PASS", lambda ctx, scope: ok_outcome(evidence=[evidence()]), area="costs", scopes=["user"]),
        make_rule("D-ERR", raising, area="data", severity="P2"),
    ]
    options = RunOptions(mode="ci", **option_overrides)
    return run_audit(make_ctx(deps, user_id="auditor-seed-user", mode="ci"), rules, options)


def test_engine_report_is_valid_against_contract_schema():
    report = _mixed_report()
    validate_report(report)
    # Anche contro la copia autorevole in docs/, direttamente con jsonschema.
    schema = json.loads(DOCS_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(json.loads(report_to_json(report)))
    assert report["schema_version"] == 1 and len(report["run_id"]) == 32
    assert report["user_id"] == "auditor-seed-user" and report["mode"] == "ci"
    from app.version import APP_VERSION

    assert report["app_version"] == APP_VERSION
    assert report["started_at"].endswith("Z") and report["duration_ms"] >= 0


def test_report_counts_by_status_severity_scope_rule():
    report = _mixed_report()
    counts = report["counts"]
    assert counts["total"] == len(report["results"]) == sum(counts["by_status"].values())
    assert counts["by_status"] == {"pass": 1, "fail": 6, "skip": 3, "error": 3}
    assert counts["by_severity"]["P0"] == {"pass": 0, "fail": 4, "skip": 0, "error": 0}
    assert counts["by_severity"]["P1"] == {"pass": 1, "fail": 2, "skip": 0, "error": 0}
    assert counts["by_severity"]["P2"] == {"pass": 0, "fail": 0, "skip": 3, "error": 3}
    assert counts["known_defect_failures"] == 2
    assert report["by_rule"]["A-KNOWN"] == {"pass": 0, "fail": 2, "skip": 0, "error": 0}
    assert report["by_scope"]["portfolio:1"] == {"pass": 0, "fail": 1, "skip": 1, "error": 1}
    assert report["by_scope"]["user"] == {"pass": 1, "fail": 0, "skip": 0, "error": 0}
    assert [e["scope_key"] for e in report["scopes"]] == sorted(e["scope_key"] for e in report["scopes"])
    sev_order = [r["severity"] for r in report["results"]]
    assert sev_order == sorted(sev_order)
    assert report["exit_code"] == 1


def test_report_exit_code_follows_options():
    def failing(ctx, scope):
        return {"status": "fail", "reason_code": "invariant_violated", "reason": "No.", "evidence": [evidence()]}

    rule = make_rule("A-KNOWN", failing, known_defect="TASK-41")
    deps = _run_deps()
    lenient = run_audit(make_ctx(deps), [rule], RunOptions(include_instruments=False))
    strict = run_audit(make_ctx(deps), [rule], RunOptions(include_instruments=False, strict_known=True))
    assert lenient["exit_code"] == 0 and strict["exit_code"] == 1


def test_validate_report_rejects_invalid():
    report = _mixed_report()
    report["results"][0]["status"] = "maybe"
    with pytest.raises(ReportValidationError):
        validate_report(report)
    with pytest.raises(ReportValidationError):
        validate_report({"schema_version": 1})


def test_report_to_json_round_trip():
    report = _mixed_report()
    text = report_to_json(report)
    assert json.loads(text) == report
    assert "\n  " in text


def test_report_to_markdown_sections():
    report = _mixed_report()
    md = report_to_markdown(report)
    assert md.startswith("# Auditor dei calcoli — non superato\n")
    order = ["## Fallimenti ed errori", "## Regole saltate", "## Esiti per scope", "## Chiamate ai tool"]
    positions = [md.index(section) for section in order]
    assert positions == sorted(positions)
    assert "auditor-seed-user" in md and "modalità ci" in md
    assert "| P0 | 0 | 4 | 0 | 0 |" in md
    assert "`A-FAIL`" in md and "V365-008" in md and "TASK-41" in md
    assert "`positions[0].weight` (get_positions): 99.5 → 100.0, tolleranza ±0,01 — somma" in md
    assert "RuntimeError: rotta" in md
    assert "Nessun peso obiettivo \\| target." in md   # pipe protetta in tabella
    assert "| portfolio:1 | 0 | 1 | 1 | 1 |" in md
    assert "Difetti noti" in md


def test_report_to_markdown_passed_and_nightly_without_user():
    report = build_report(
        run_id="b" * 32, mode="nightly", user_id=None,
        started_at=datetime(2026, 11, 10, 23, 35, tzinfo=UTC),
        finished_at=datetime(2026, 11, 10, 23, 36, tzinfo=UTC),
        options=RunOptions(mode="nightly"), rules=[], scopes=[], results=[],
        tool_calls={"total": 0, "cache_hits": 0, "errors": 0, "by_tool": {}}, deadline_exceeded=False,
    )
    validate_report(report)
    md = report_to_markdown(report)
    assert md.startswith("# Auditor dei calcoli — superato")
    assert "utente" not in md.split("\n")[2]
    assert report["duration_ms"] == 60000 and report["started_at"] == "2026-11-10T23:35:00.000Z"


def test_report_to_markdown_stays_under_one_megabyte(monkeypatch):
    monkeypatch.setattr(report_module, "MARKDOWN_MAX_BYTES", 20_000)
    report = _mixed_report()
    skip = next(r for r in report["results"] if r["status"] == "skip")
    report["results"].extend(dict(skip, scope_key=f"portfolio:{i}", reason="x" * 200) for i in range(500))
    md = report_to_markdown(report)
    assert len(md.encode("utf-8")) <= 20_000
    assert "tabella omessa" in md
    assert "Il totale non torna." in md   # fail sempre presenti


def test_privacy_rows_collapse_and_worst_status():
    results = [
        {"rule_id": "D-X", "severity": "P1", "status": "pass",
         "scope": {"kind": "instrument", "portfolio_id": 1, "symbol": "A"}},
        {"rule_id": "D-X", "severity": "P1", "status": "fail",
         "scope": {"kind": "instrument", "portfolio_id": 1, "symbol": "B"}},
        {"rule_id": "D-X", "severity": "P1", "status": "skip",
         "scope": {"kind": "instrument", "portfolio_id": 1, "symbol": "C"}},
        {"rule_id": "D-X", "severity": "P1", "status": "error", "scope": {"kind": "portfolio", "portfolio_id": 1}},
        {"rule_id": "D-X", "severity": "P1", "status": "pass", "scope": {"kind": "portfolio", "portfolio_id": 1}},
        {"rule_id": "A-Y", "severity": "P0", "status": "skip", "scope": {"kind": "aggregate", "portfolio_ids": [1, 2]}},
        {"rule_id": "A-Y", "severity": "P0", "status": "pass", "scope": {"kind": "user", "portfolio_ids": [2]}},
    ]
    rows = privacy_rows({"results": results})
    assert rows == [
        {"portfolio_id": 1, "rule_id": "A-Y", "scope_kind": "aggregate", "status": "skip", "severity": "P0"},
        {"portfolio_id": 1, "rule_id": "D-X", "scope_kind": "instrument", "status": "fail", "severity": "P1"},
        {"portfolio_id": 1, "rule_id": "D-X", "scope_kind": "portfolio", "status": "error", "severity": "P1"},
        {"portfolio_id": 2, "rule_id": "A-Y", "scope_kind": "aggregate", "status": "skip", "severity": "P0"},
        {"portfolio_id": 2, "rule_id": "A-Y", "scope_kind": "user", "status": "pass", "severity": "P0"},
    ]
    for row in rows:
        assert set(row) == {"portfolio_id", "rule_id", "scope_kind", "status", "severity"}


# ================================================================================================
# CLI
# ================================================================================================

def _cli_rules():
    def failing_p2(ctx, scope):
        return {"status": "fail", "reason_code": "invariant_violated", "reason": "Minore.", "evidence": [evidence()]}

    def positions_pass(ctx, scope):
        ctx.scoped("get_positions", scope)
        return ok_outcome()

    return [
        make_rule("A-PASS", positions_pass, severity="P0"),
        make_rule("C-MINOR", failing_p2, severity="P2", area="costs"),
    ]


@pytest.fixture
def cli_env(monkeypatch):
    state = {"deps": _run_deps(), "rules": _cli_rules()}
    monkeypatch.setattr(cli, "load_rules", lambda: state["rules"])
    monkeypatch.setattr(cli, "build_tool_dependencies", lambda offline=True: state["deps"])
    return state


def test_cli_exit_zero_and_writes_reports(cli_env, tmp_path, capsys):
    json_out, md_out = tmp_path / "out" / "r.json", tmp_path / "r.md"
    code = cli.main(["--user", "auditor-seed-user", "--mode", "ci", "--json-out", str(json_out),
                     "--md-out", str(md_out), "--format", "json"])
    assert code == 0
    report = json.loads(json_out.read_text(encoding="utf-8"))
    validate_report(report)
    assert report["exit_code"] == 0 and report["mode"] == "ci"
    assert md_out.read_text(encoding="utf-8").startswith("# Auditor dei calcoli — superato")
    assert json.loads(capsys.readouterr().out) == report


def test_cli_fail_on_threshold_gives_exit_one(cli_env, capsys):
    assert cli.main(["--user", "u", "--fail-on", "P2"]) == 1
    assert capsys.readouterr().out.startswith("# Auditor dei calcoli — non superato")


def test_cli_filters_rules_and_portfolios(cli_env, tmp_path):
    out = tmp_path / "r.json"
    code = cli.main(["--user", "u", "--rule", "A-PASS", "--portfolio", "1", "--no-aggregate", "--no-instruments",
                     "--json-out", str(out), "--format", "json", "--max-workers", "2", "--rule-timeout-s", "5"])
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [r["scope_key"] for r in report["results"]] == ["portfolio:1"]
    assert report["options"]["rule_ids"] == ["A-PASS"] and report["options"]["portfolio_ids"] == [1]
    assert cli.main(["--user", "u", "--group", "C", "--fail-on", "P2"]) == 1
    assert cli.main(["--user", "u", "--group", "A", "--fail-on", "P2"]) == 0


def test_cli_known_defect_and_strict(cli_env):
    def failing(ctx, scope):
        return {"status": "fail", "reason_code": "invariant_violated", "reason": "No.", "evidence": [evidence()]}

    cli_env["rules"] = [make_rule("A-KNOWN", failing, severity="P0", known_defect="TASK-41")]
    assert cli.main(["--user", "u"]) == 0
    assert cli.main(["--user", "u", "--strict-known"]) == 1


@pytest.mark.parametrize(
    "argv",
    [
        [],                                              # --user mancante
        ["--user", "u", "--rule", "A-UNKNOWN"],
        ["--user", "u", "--group", "Z"],
        ["--user", "u", "--fail-on", "P5"],
        ["--user", "u", "--mode", "nightly"],
        ["--user", "u", "--portfolio", "abc"],
        ["--user", "u", "--portfolio", "42"],            # non dell'utente
        ["--user", "u", "--max-workers", "0"],
        ["--user", "u", "--rule-timeout-s", "-1"],
        ["--user", "u", "--unknown-flag"],
    ],
)
def test_cli_usage_errors_exit_two(cli_env, argv, capsys):
    assert cli.main(argv) == 2
    assert "auditor:" in capsys.readouterr().err


def test_cli_configuration_errors_exit_two(cli_env, monkeypatch):
    cli_env["rules"] = []
    assert cli.main(["--user", "u"]) == 2
    cli_env["rules"] = _cli_rules()

    cli_env["deps"] = portfolios_deps([])
    assert cli.main(["--user", "u"]) == 2                         # utente senza portafogli

    cli_env["deps"] = FakeDeps().set("list_portfolios", {}, RuntimeError("connection refused"))
    assert cli.main(["--user", "u"]) == 2                         # database non raggiungibile

    def broken_deps(offline=True):
        raise RuntimeError("DATABASE_URL mancante")

    monkeypatch.setattr(cli, "build_tool_dependencies", broken_deps)
    assert cli.main(["--user", "u"]) == 2

    def broken_rules():
        raise RuleRegistrationError("dichiarazione non valida")

    monkeypatch.setattr(cli, "load_rules", broken_rules)
    assert cli.main(["--user", "u"]) == 2


def test_cli_invalid_report_exit_two(cli_env, monkeypatch):
    def bad_validate(report):
        raise ReportValidationError("report non valido")

    monkeypatch.setattr(cli, "validate_report", bad_validate)
    assert cli.main(["--user", "u"]) == 2


def test_cli_list_rules(cli_env, capsys):
    cli_env["rules"] = _cli_rules() + [make_rule("D-KNOWN", area="data", known_defect="TASK-41")]
    assert cli.main(["--list-rules"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].split("\t") == ["A-PASS", "A", "P0", "Una regola di prova", "-"]
    assert lines[2].split("\t")[-1] == "TASK-41"


def test_cli_uses_offline_dependencies(monkeypatch):
    captured = {}

    def fake_build(*, offline=True):
        captured["offline"] = offline
        return portfolios_deps([])

    monkeypatch.setattr(cli, "load_rules", _cli_rules)
    monkeypatch.setattr(cli, "build_tool_dependencies", fake_build)
    cli.main(["--user", "u"])
    assert captured == {"offline": True}
