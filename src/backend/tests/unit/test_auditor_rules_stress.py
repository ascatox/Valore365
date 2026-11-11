"""TASK-74 — Auditor, gruppo A: stress test e classificazione.

Per ogni regola: ``pass`` sull'output corretto, ``fail`` quando si
reintroduce il difetto del finding d'origine (V365-001, V365-002, V365-012,
V365-007, V-BOND-QUOTETYPE), ``skip`` con il codice giusto quando i dati non
bastano. Gli output finti hanno la forma reale dei tool: sono prodotti dalle
funzioni vere (``_get_stress_test``, ``_search_asset_info``,
``_get_cost_breakdown``, ``position_row``, classificatore condiviso, calcolo
degli scenari) su repository finti in memoria. Niente rete, niente DB.
"""

from __future__ import annotations

import ast
import copy
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from unittest import mock

import pytest

from app import copilot_tools
from app.constants.stress_scenarios import HISTORICAL_SCENARIOS, SHOCK_SCENARIOS
from app.mcp_server.tools import sanitize_output
from app.schemas.portfolio_doctor import StressTestResponse
from app.services.auditor.rules import stress_classification as sc
from app.services.portfolio_doctor import _health, _stress
from app.services.portfolio_doctor._holdings import AnalyzedHolding

# ---------------------------------------------------------------------------
# Contesto finto di riferimento (docs/auditor/architecture.md §10, copiato)
# ---------------------------------------------------------------------------

AGGREGATE_TOOL_OF = {
    "get_portfolio_summary": "get_aggregate_summary", "get_positions": "get_aggregate_positions",
    "get_performance": "get_aggregate_performance", "get_recent_transactions": "get_aggregate_recent_transactions",
    "get_portfolio_health": "get_aggregate_health", "get_monte_carlo": "get_aggregate_monte_carlo",
    "get_stress_test": "get_aggregate_stress_test", "get_xray_summary": "get_aggregate_xray",
}
DOCTOR_SCOPE_TOOLS = frozenset({
    "read_doctor_policy", "read_doctor_metrics", "read_doctor_violations",
    "validate_policy_draft", "build_doctor_scenario", "compare_doctor_scenarios",
})


def canonical_key(tool: str, args: Mapping[str, Any]) -> str:
    return json.dumps({"tool": tool, "args": dict(args)}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scoped_tool_args(tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None):
    extra = dict(extra_args or {})
    if tool.startswith("get_aggregate_"):
        raise ValueError("passare il tool del portafoglio singolo")
    kind = scope["kind"]
    if kind in ("portfolio", "instrument"):
        return tool, {"portfolio_id": scope["portfolio_id"], **extra}
    if kind == "aggregate":
        ids = list(scope["portfolio_ids"])
        if tool in DOCTOR_SCOPE_TOOLS:
            return tool, {"portfolio_id": ids[0], "portfolio_ids": ids, **extra}
        if extra or tool not in AGGREGATE_TOOL_OF:
            raise ValueError(f"{tool} non ha una variante aggregata")
        return AGGREGATE_TOOL_OF[tool], {"portfolio_ids": ids}
    raise ValueError(f"scope {kind} non ammesso per {tool}")


class FakeToolError(RuntimeError):
    def __init__(self, tool: str, args: Mapping[str, Any], message: str) -> None:
        super().__init__(f"{tool}: {message}")
        self.tool, self.args, self.message = tool, dict(args), message


class FakeAuditContext:
    """responses: [(tool, args, result_dict | Exception)]; transactions: {pid: [tx]};
    performance_audit: {tuple(sorted(ids)): export}; portfolios: [{"id", "name", "base_currency"}]."""

    def __init__(self, responses=(), *, transactions=None, performance_audit=None, portfolios=None,
                 user_id: str = "test-user") -> None:
        self.user_id, self.run_id, self.mode = user_id, "0" * 32, "local"
        self._responses = {canonical_key(t, a): r for t, a, r in responses}
        self._transactions = dict(transactions or {})
        self._performance_audit = dict(performance_audit or {})
        if portfolios is not None:
            self._responses[canonical_key("list_portfolios", {})] = {"portfolios": list(portfolios)}
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append((tool, dict(args)))
        key = canonical_key(tool, args)
        if key not in self._responses:
            raise KeyError(f"risposta finta mancante: {key}")
        value = self._responses[key]
        if isinstance(value, Exception):
            raise FakeToolError(tool, args, str(value))
        return copy.deepcopy(value)

    def try_call(self, tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return {"ok": True, "result": self.call(tool, args), "error": None}
        except FakeToolError as exc:
            return {"ok": False, "result": None, "error": exc.message}

    def scoped(self, tool: str, scope: Mapping[str, Any], extra_args: Mapping[str, Any] | None = None):
        return self.call(*scoped_tool_args(tool, scope, extra_args))

    def portfolios(self) -> list[dict[str, Any]]:
        return self.call("list_portfolios", {})["portfolios"]

    def transactions(self, portfolio_id: int) -> list[dict[str, Any]]:
        return copy.deepcopy(self._transactions[portfolio_id])

    def performance_audit(self, portfolio_ids: Sequence[int]) -> dict[str, Any]:
        return copy.deepcopy(self._performance_audit[tuple(sorted(portfolio_ids))])

    def call_stats(self) -> dict[str, Any]:
        return {"total": len(self.calls), "cache_hits": 0, "errors": 0, "by_tool": {}}


# ---------------------------------------------------------------------------
# Strumenti e portafogli di prova (rules.md §1, sottoinsieme)
# ---------------------------------------------------------------------------

ASSETS: dict[str, dict[str, Any]] = {
    "AUDEQ.MI": {"id": 9201, "type": "etf", "name": "AUD Global Equity UCITS ETF (Acc)",
                 "focus": "Equity, World", "ter": 0.22},
    "AUDBD.MI": {"id": 9202, "type": "etf", "name": "AUD Global Aggregate Bond UCITS ETF EUR Hedged (Acc)",
                 "focus": "Bonds, World, Aggregate", "ter": 0.10},
    "AUDTECH.DE": {"id": 9203, "type": "etf", "name": "AUD Nasdaq-100 Technology UCITS ETF (Dist)",
                   "focus": "Equity, United States, Technology", "ter": 0.30},
    "AUDGOV.MI": {"id": 9204, "type": "etf", "name": "AUD Euro Government Bond UCITS ETF (Dist)",
                  "focus": "Bonds, Euro, Government", "ter": 0.15},
    "AUDHY.DE": {"id": 9205, "type": "stock", "name": "AUD Euro High Yield Corporate Bond UCITS ETF (Dist)",
                 "category": "High Yield Bond"},
    "AUDBTP": {"id": 9206, "type": "bond", "name": "BTP Italia 2030 1,6%"},
    "AUDGLD.DE": {"id": 9207, "type": "stock", "name": "AUD Physical Gold ETC",
                  "focus": "Precious Metals, Gold"},
    "AUDCMD.MI": {"id": 9208, "type": "etf", "name": "AUD Broad Commodity Swap UCITS ETF",
                  "focus": "Commodities, Broad market", "ter": 0.19},
    "AUDTHM.DE": {"id": 9209, "type": "etf", "name": "AUD Thematic Frontier Opportunities UCITS ETF"},
    # V-BOND-QUOTETYPE: un ETF obbligazionario che il refresh ha registrato come bond.
    "AUDCORP.MI": {"id": 9210, "type": "bond", "name": "AUD Euro Corporate Bond UCITS ETF (Dist)"},
}

PORTFOLIOS: dict[int, list[tuple[str, float]]] = {
    9101: [("AUDEQ.MI", 70.0), ("AUDBD.MI", 20.0), ("AUDTECH.DE", 10.0)],
    9102: [("AUDGOV.MI", 40.0), ("AUDHY.DE", 35.0), ("AUDBTP", 25.0)],
    9103: [("AUDGLD.DE", 40.0), ("AUDCMD.MI", 20.0), ("AUDTHM.DE", 15.0), ("AUDEQ.MI", 25.0)],
    9106: [],
    9108: [("AUDCORP.MI", 60.0), ("AUDEQ.MI", 40.0)],
}

USER = "test-user"


def holdings_of(pid: int) -> list[AnalyzedHolding]:
    out = []
    for symbol, weight in PORTFOLIOS[pid]:
        a = ASSETS[symbol]
        out.append(AnalyzedHolding(
            asset_id=a["id"], symbol=symbol, name=a["name"], asset_type=a["type"], quote_currency="EUR",
            market_value=weight * 100.0, weight_pct=weight,
            investment_focus=a.get("focus"), category=a.get("category"),
        ))
    return out


def merged_holdings(pids: Sequence[int]) -> list[AnalyzedHolding]:
    """Holdings dell'aggregato: pesi sul totale combinato (valori uguali per portafoglio)."""
    by_id: dict[int, AnalyzedHolding] = {}
    for pid in pids:
        for h in holdings_of(pid):
            if h.asset_id in by_id:
                by_id[h.asset_id].market_value += h.market_value
            else:
                by_id[h.asset_id] = copy.copy(h)
    total = sum(h.market_value for h in by_id.values())
    for h in by_id.values():
        h.weight_pct = h.market_value / total * 100.0
    return list(by_id.values())


def price_rows_all_windows(pid: int) -> list[dict]:
    """Due barre per strumento in ogni finestra storica: metodo historical."""
    rows = []
    for k, scenario in enumerate(HISTORICAL_SCENARIOS):
        start, end = date.fromisoformat(scenario["start"]), date.fromisoformat(scenario["end"])
        for j, h in enumerate(holdings_of(pid)):
            first = 100.0 + 10 * j
            last = first * (1 - 0.1 * (j + 1) - 0.05 * k)
            rows.append({"asset_id": h.asset_id, "price_date": start, "close": first})
            rows.append({"asset_id": h.asset_id, "price_date": end, "close": last})
    return rows


class _PriceRepo:
    """Repository finto che risponde alla query di price_bars_1d (come test_stress_historical_proxy.py)."""

    def __init__(self, rows: list[dict] | None = None):
        rows = rows or []

        class _Result:
            def __init__(self, data):
                self._data = data

            def mappings(self):
                return self

            def all(self):
                return self._data

        class _Conn:
            def execute(self, _sql, params):
                ids = set(params["asset_ids"])
                data = [r for r in rows if r["asset_id"] in ids
                        and params["start_date"] <= r["price_date"] <= params["end_date"]]
                return _Result(sorted(data, key=lambda r: (r["asset_id"], r["price_date"])))

        class _Begin:
            def __enter__(self):
                return _Conn()

            def __exit__(self, *exc):
                return False

        class _Engine:
            @staticmethod
            def begin():
                return _Begin()

        self.engine = _Engine()


def stress_output(holdings: list[AnalyzedHolding], rows: list[dict] | None = None, *,
                  shock_scenarios: list[dict] = SHOCK_SCENARIOS) -> dict:
    """Output di get_stress_test prodotto dal codice vero (calcolo degli scenari + formattazione del tool)."""
    repo = _PriceRepo(rows)

    def fake_run_stress_test(_repo, portfolio_ref, _user_id):
        scenarios = []
        if holdings:
            scenarios = [_stress._compute_historical_scenario(repo, holdings, s) for s in HISTORICAL_SCENARIOS]
            scenarios += [_stress._compute_shock_scenario(holdings, s) for s in shock_scenarios]
        return StressTestResponse(portfolio_id=portfolio_ref if isinstance(portfolio_ref, int) else 0,
                                  scenarios=scenarios, analysis_date="2026-11-11")

    ref = 9999
    with mock.patch.object(copilot_tools, "run_stress_test", fake_run_stress_test):
        return sanitize_output(copilot_tools._get_stress_test({}, repo, None, ref, USER))


def legacy_shock_table() -> list[dict]:
    """Tabella shock precedente a TASK-35: niente gold/commodity, il resto prende lo shock equity."""
    out = copy.deepcopy(SHOCK_SCENARIOS)
    for s in out:
        s["shocks"].pop("gold")
        s["shocks"].pop("commodity")
    return out


def legacy_shock_asset_class(holding: AnalyzedHolding) -> str:
    """Il vecchio _shock_asset_class: solo bond riconosciuto, tutto il resto equity."""
    return "bond" if holding.asset_type == "bond" else "equity"


class _InfoRepo:
    """Repository finto per _search_asset_info e _get_cost_breakdown."""

    def __init__(self, pid: int):
        self.pid = pid

    def get_positions(self, _pid, _uid):
        total = sum(w for _, w in PORTFOLIOS[self.pid]) or 1.0
        return [SimpleNamespace(symbol=s, asset_id=ASSETS[s]["id"], name=ASSETS[s]["name"],
                                market_value=w * 100.0, weight=w / total * 100.0, asset_type=ASSETS[s]["type"])
                for s, w in PORTFOLIOS[self.pid]]

    def get_summary(self, _pid, _uid):
        return SimpleNamespace(market_value=sum(w * 100.0 for _, w in PORTFOLIOS[self.pid]))

    def list_transactions(self, _pid, _uid):
        return []

    def _by_id(self, asset_id):
        return next((s, a) for s, a in ASSETS.items() if a["id"] == asset_id)

    def get_asset(self, asset_id):
        symbol, a = self._by_id(asset_id)
        return SimpleNamespace(symbol=symbol, name=a["name"], asset_type=a["type"], quote_currency="EUR", isin=None)

    def get_asset_metadata(self, asset_id):
        _, a = self._by_id(asset_id)
        if "category" not in a:
            return None
        return SimpleNamespace(category=a["category"], description=None)

    def get_etf_enrichment(self, asset_id):
        _, a = self._by_id(asset_id)
        return {"investment_focus": a["focus"]} if a.get("focus") else None


def asset_info(pid: int, symbol: str) -> dict:
    return sanitize_output(copilot_tools._search_asset_info({"symbol": symbol}, _InfoRepo(pid), None, pid, USER))


def positions_output(pid: int) -> dict:
    rows = [
        copilot_tools.position_row(SimpleNamespace(
            symbol=p.symbol, name=p.name, weight=p.weight, market_value=p.market_value, avg_cost=1.0,
            quantity=p.market_value, unrealized_pl_pct=0.0, day_change_pct=0.0, market_price=1.0,
        ))
        for p in sorted(_InfoRepo(pid).get_positions(pid, USER), key=lambda p: p.weight, reverse=True)
    ]
    return sanitize_output({"positions": rows, **copilot_tools.positions_data_note(rows)})


def cost_output(pid: int, infer=_health.infer_ter) -> dict:
    """get_cost_breakdown vero; TER solo dedotto (nessun dato justETF/yFinance), come per AUDGLD.DE."""
    holdings = holdings_of(pid)

    def resolve(hs, _repo):
        out = {}
        for h in hs:
            ter = infer(h)
            out[h.asset_id] = (ter, "inferred" if ter is not None else "none")
        return out

    with mock.patch.object(copilot_tools, "_load_holdings", lambda *_a: holdings), \
            mock.patch.object(copilot_tools, "resolve_holding_ters", resolve):
        return sanitize_output(copilot_tools._get_cost_breakdown({}, _InfoRepo(pid), None, pid, USER))


def legacy_infer_ter(holding: AnalyzedHolding) -> float | None:
    """infer_ter precedente a f7d882c: ogni stock (anche un ETC) a costo zero."""
    if holding.asset_type.lower() in {"stock", "bond", "cash"}:
        return 0.0
    return _health.infer_ter(holding)


def P(pid: int) -> dict:
    return {"kind": "portfolio", "portfolio_id": pid}


def I(pid: int, symbol: str) -> dict:
    return {"kind": "instrument", "portfolio_id": pid, "symbol": symbol}


def ctx_with_stress(outputs: dict[int, dict], aggregate: tuple[list[int], dict] | None = None) -> FakeAuditContext:
    responses = [("get_stress_test", {"portfolio_id": pid}, out) for pid, out in outputs.items()]
    if aggregate:
        responses.append(("get_aggregate_stress_test", {"portfolio_ids": aggregate[0]}, aggregate[1]))
    return FakeAuditContext(responses)


def ctx_instrument(pid: int, symbol: str, *, info: dict | None = None, stress: dict | None = None,
                   costs: dict | None = None) -> FakeAuditContext:
    responses = [("search_asset_info", {"portfolio_id": pid, "symbol": symbol},
                  info if info is not None else asset_info(pid, symbol))]
    if stress is not None:
        responses.append(("get_stress_test", {"portfolio_id": pid}, stress))
    if costs is not None:
        responses.append(("get_cost_breakdown", {"portfolio_id": pid}, costs))
    return FakeAuditContext(responses)


EVIDENCE_KEYS = {"tool", "args", "path", "observed", "expected", "tolerance", "note"}


def assert_outcome(outcome: dict, status: str, reason_code: str | None = None) -> dict:
    assert set(outcome) == {"status", "reason_code", "reason", "evidence"}
    assert outcome["status"] == status, outcome
    if status == "pass":
        assert outcome["reason_code"] is None
    else:
        assert outcome["reason_code"] == (reason_code or "invariant_violated"), outcome
        assert isinstance(outcome["reason"], str) and outcome["reason"]
    if status == "fail":
        assert outcome["evidence"]
    assert len(outcome["evidence"]) <= 50
    for ev in outcome["evidence"]:
        assert set(ev) == EVIDENCE_KEYS
        assert isinstance(ev["tool"], str) and isinstance(ev["args"], dict) and isinstance(ev["path"], str)
    json.dumps(outcome)
    return outcome


def set_impact(output: dict, name: str, value: float) -> None:
    next(s for s in output["scenarios"] if s["scenario_name"] == name)["estimated_portfolio_impact_pct"] = value


def scenario(output: dict, name: str) -> dict:
    return next(s for s in output["scenarios"] if s["scenario_name"] == name)


@pytest.fixture(scope="module")
def outputs() -> dict[int, dict]:
    return {
        9101: stress_output(holdings_of(9101), price_rows_all_windows(9101)),
        9102: stress_output(holdings_of(9102)),
        9103: stress_output(holdings_of(9103)),
        9106: stress_output([]),
    }


# ---------------------------------------------------------------------------
# Dichiarazioni
# ---------------------------------------------------------------------------

CATALOG = {
    "A-STRESS-HIST-DISTINCT": ("P0", "stress", ["V365-001"], ["user"]),
    "A-STRESS-PROXY-TABLE": ("P0", "stress", ["V365-001"], ["portfolio", "aggregate"]),
    "A-STRESS-METHOD-COVERAGE": ("P1", "stress", ["V365-001"], ["portfolio", "aggregate"]),
    "A-STRESS-CONTRIB-SUM": ("P1", "stress", ["V365-001", "V365-002"], ["portfolio", "aggregate"]),
    "A-STRESS-SHOCK-TABLE": ("P0", "stress", ["V365-002"], ["portfolio", "aggregate"]),
    "A-STRESS-NONEQUITY-POSITION-SHOCK": ("P0", "stress", ["V365-002"], ["portfolio", "aggregate"]),
    "A-CLASS-STRESS-CONSISTENT": ("P0", "classification", ["V365-002", "V365-012"], ["portfolio"]),
    "A-CLASS-ETC-NOT-EQUITY": ("P1", "classification", ["V365-012"], ["instrument"]),
    "A-CLASS-ETP-TER-NONZERO": ("P2", "classification", ["V365-012", "V365-007"], ["instrument"]),
    "A-CLASS-BOND-TYPE": ("P2", "classification", ["V-BOND-QUOTETYPE"], ["instrument"]),
    "A-CLASS-UNKNOWN-DECLARED": ("P2", "classification", ["V365-002"], ["instrument"]),
}


def test_declarations_match_catalog():
    import re

    by_id = {r["id"]: r for r in sc.RULES}
    assert set(by_id) == set(CATALOG)
    assert len(sc.RULES) == 11
    for rule_id, (severity, area, findings, scopes) in CATALOG.items():
        rule = by_id[rule_id]
        assert re.match(r"^[ABCD]-[A-Z0-9]+(?:-[A-Z0-9]+)*$", rule_id)
        assert rule["group"] == "A"
        assert rule["severity"] == severity
        assert rule["area"] == area
        assert rule["findings"] == findings
        assert rule["scopes"] == scopes
        assert callable(rule["check"]) and rule["title"] and rule["tools"]
    assert by_id["A-STRESS-HIST-DISTINCT"]["timeout_s"] == 60.0


def test_module_imports_only_allowed_modules():
    tree = ast.parse(Path(sc.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    app_modules = {m for m in imported if m and m.startswith("app")}
    assert app_modules == {"app.constants.stress_scenarios"}


def test_real_outputs_have_expected_methods(outputs):
    assert {s["method"] for s in outputs[9101]["scenarios"] if s["scenario_type"] == "historical"} == {"historical"}
    assert {s["method"] for s in outputs[9102]["scenarios"] if s["scenario_type"] == "historical"} == {"proxy"}
    assert outputs[9106]["scenarios"] == []


# ---------------------------------------------------------------------------
# A-STRESS-HIST-DISTINCT (V365-001)
# ---------------------------------------------------------------------------

USER_SCOPE = {"kind": "user", "portfolio_ids": [9101, 9102, 9103, 9106]}
OLD_IMPACTS = {"Global Financial Crisis": -45.44, "Dot-Com Crash": -39.28,
               "Covid Crash": -27.12, "Bear Market 2022": -20.32}


def test_hist_distinct_pass(outputs):
    out = assert_outcome(sc.check_stress_hist_distinct(ctx_with_stress(outputs), USER_SCOPE), "pass")
    assert {ev["args"]["portfolio_id"] for ev in out["evidence"]} == {9101, 9102, 9103}


def test_hist_distinct_fails_on_benchmark_times_08(outputs):
    broken = copy.deepcopy(outputs)
    for pid in (9101, 9102, 9103):
        for name, value in OLD_IMPACTS.items():
            set_impact(broken[pid], name, value)
    out = assert_outcome(sc.check_stress_hist_distinct(ctx_with_stress(broken), USER_SCOPE), "fail")
    ev = out["evidence"][0]
    assert ev["tool"] == "get_stress_test" and ev["path"].endswith(".estimated_portfolio_impact_pct")
    assert ev["observed"] in OLD_IMPACTS.values()


def test_hist_distinct_skip_with_fewer_than_two_eligible(outputs):
    ctx = ctx_with_stress({9101: outputs[9101], 9106: outputs[9106]})
    assert_outcome(sc.check_stress_hist_distinct(ctx, {"kind": "user", "portfolio_ids": [9101, 9106]}),
                   "skip", "not_applicable")


def test_hist_distinct_same_composition_is_not_judged(outputs):
    # Stessa miscela di classi (distanza L1 0): impatti uguali legittimi, nessuna coppia giudicabile.
    ctx = ctx_with_stress({9102: outputs[9102], 9109: copy.deepcopy(outputs[9102])})
    assert_outcome(sc.check_stress_hist_distinct(ctx, {"kind": "user", "portfolio_ids": [9102, 9109]}),
                   "skip", "not_applicable")


# ---------------------------------------------------------------------------
# A-STRESS-PROXY-TABLE (V365-001)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_proxy_table_pass(outputs, pid):
    assert_outcome(sc.check_stress_proxy_table(ctx_with_stress(outputs), P(pid)), "pass")


def test_proxy_table_pass_on_aggregate():
    ids = [9102, 9103]
    agg = stress_output(merged_holdings(ids))
    ctx = ctx_with_stress({}, aggregate=(ids, agg))
    out = assert_outcome(sc.check_stress_proxy_table(ctx, {"kind": "aggregate", "portfolio_ids": ids}), "pass")
    assert out["evidence"][0]["tool"] == "get_aggregate_stress_test"
    assert ctx.calls == [("get_aggregate_stress_test", {"portfolio_ids": ids})]


def test_proxy_table_fails_without_class_breakdown(outputs):
    # Output precedente a TASK-38: niente method, niente class_breakdown.
    broken = copy.deepcopy(outputs[9102])
    for s in broken["scenarios"]:
        if s["scenario_type"] == "historical":
            for key in ("method", "coverage_pct", "class_breakdown", "methodology_note", "flags"):
                s.pop(key, None)
            s["estimated_portfolio_impact_pct"] = OLD_IMPACTS[s["scenario_name"]]
    out = assert_outcome(sc.check_stress_proxy_table(ctx_with_stress({9102: broken}), P(9102)), "fail")
    assert out["evidence"][0]["path"].endswith(".class_breakdown")


def test_proxy_table_fails_with_same_drawdown_for_every_class(outputs):
    broken = copy.deepcopy(outputs[9103])
    gfc = scenario(broken, "Global Financial Crisis")
    for row in gfc["class_breakdown"]:
        row["drawdown_pct"] = -45.44
    out = assert_outcome(sc.check_stress_proxy_table(ctx_with_stress({9103: broken}), P(9103)), "fail")
    gold = next(e for e in out["evidence"] if "asset_class=gold" in e["path"])
    assert gold["observed"] == -45.44 and gold["expected"] == 20.0 and gold["tolerance"] == 0.005


def test_proxy_table_unknown_class_uses_equity_proxy(outputs):
    # AUDTHM.DE (unknown) in 9103: proxy equity, non un valore proprio.
    gfc = scenario(outputs[9103], "Global Financial Crisis")
    unknown = next(r for r in gfc["class_breakdown"] if r["asset_class"] == "unknown")
    assert unknown["drawdown_pct"] == -54.0


def test_proxy_table_skips(outputs):
    assert_outcome(sc.check_stress_proxy_table(ctx_with_stress(outputs), P(9106)), "skip", "empty_portfolio")
    na = copy.deepcopy(outputs[9102])
    for s in na["scenarios"]:
        if s["scenario_type"] == "historical":
            s.update(method="not_available", coverage_pct=None, class_breakdown=[])
    assert_outcome(sc.check_stress_proxy_table(ctx_with_stress({9102: na}), P(9102)),
                   "skip", "scenario_not_available")


def test_proxy_table_unknown_scenario_name_fails(outputs):
    broken = copy.deepcopy(outputs[9102])
    scenario(broken, "Covid Crash")["scenario_name"] = "Crollo inventato"
    assert_outcome(sc.check_stress_proxy_table(ctx_with_stress({9102: broken}), P(9102)), "fail")


# ---------------------------------------------------------------------------
# A-STRESS-METHOD-COVERAGE (V365-001)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_method_coverage_pass(outputs, pid):
    assert_outcome(sc.check_stress_method_coverage(ctx_with_stress(outputs), P(pid)), "pass")


def test_method_coverage_fails_without_method(outputs):
    broken = copy.deepcopy(outputs[9101])
    scenario(broken, "Covid Crash").pop("method")
    out = assert_outcome(sc.check_stress_method_coverage(ctx_with_stress({9101: broken}), P(9101)), "fail")
    assert out["evidence"][0]["path"] == "scenarios[scenario_name=Covid Crash].method"


def test_method_coverage_fails_proxy_with_high_coverage(outputs):
    broken = copy.deepcopy(outputs[9102])
    scenario(broken, "Bear Market 2022")["coverage_pct"] = 80.0
    out = assert_outcome(sc.check_stress_method_coverage(ctx_with_stress({9102: broken}), P(9102)), "fail")
    assert out["evidence"][0]["observed"] == 80.0


def test_method_coverage_fails_without_proxy_flag_or_note(outputs):
    broken = copy.deepcopy(outputs[9102])
    s = scenario(broken, "Dot-Com Crash")
    s["flags"] = []
    s.pop("methodology_note")
    out = assert_outcome(sc.check_stress_method_coverage(ctx_with_stress({9102: broken}), P(9102)), "fail")
    assert {e["path"].rsplit(".", 1)[1] for e in out["evidence"]} == {"flags", "methodology_note"}


def test_method_coverage_skip_empty(outputs):
    assert_outcome(sc.check_stress_method_coverage(ctx_with_stress(outputs), P(9106)), "skip", "empty_portfolio")


# ---------------------------------------------------------------------------
# A-STRESS-CONTRIB-SUM (V365-001, V365-002)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_contrib_sum_pass(outputs, pid):
    assert_outcome(sc.check_stress_contrib_sum(ctx_with_stress(outputs), P(pid)), "pass")


def test_contrib_sum_pass_on_aggregate():
    ids = [9101, 9102, 9103]
    agg = stress_output(merged_holdings(ids))
    assert_outcome(sc.check_stress_contrib_sum(ctx_with_stress({}, aggregate=(ids, agg)),
                                               {"kind": "aggregate", "portfolio_ids": ids}), "pass")


def test_contrib_sum_fails_on_altered_contribution(outputs):
    broken = copy.deepcopy(outputs[9103])
    s = scenario(broken, "Global Equity Crash")
    gold = next(r for r in s["class_breakdown"] if r["asset_class"] == "gold")
    gold["contribution_pct"] = round(gold["contribution_pct"] * 4, 2)  # shock equity applicato al peso dell'oro
    out = assert_outcome(sc.check_stress_contrib_sum(ctx_with_stress({9103: broken}), P(9103)), "fail")
    paths = {e["path"] for e in out["evidence"]}
    assert "scenarios[scenario_name=Global Equity Crash].class_breakdown[*].contribution_pct" in paths
    assert "scenarios[scenario_name=Global Equity Crash].class_breakdown[asset_class=gold].contribution_pct" in paths


def test_contrib_sum_fails_on_impact_from_other_weight(outputs):
    broken = copy.deepcopy(outputs[9102])
    set_impact(broken, "Bear Market 2022", -20.32)
    assert_outcome(sc.check_stress_contrib_sum(ctx_with_stress({9102: broken}), P(9102)), "fail")


def test_contrib_sum_skip_empty(outputs):
    assert_outcome(sc.check_stress_contrib_sum(ctx_with_stress(outputs), P(9106)), "skip", "empty_portfolio")


# ---------------------------------------------------------------------------
# A-STRESS-SHOCK-TABLE (V365-002)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_shock_table_pass(outputs, pid):
    assert_outcome(sc.check_stress_shock_table(ctx_with_stress(outputs), P(pid)), "pass")


def test_shock_table_fails_with_legacy_table():
    broken = stress_output(holdings_of(9103), shock_scenarios=legacy_shock_table())
    out = assert_outcome(sc.check_stress_shock_table(ctx_with_stress({9103: broken}), P(9103)), "fail")
    tech_gold = next(e for e in out["evidence"]
                     if e["path"] == "scenarios[scenario_name=US Tech Crash].class_breakdown[asset_class=gold].shock_pct")
    assert tech_gold["observed"] == -30.0 and tech_gold["expected"] == 0.0


def test_shock_table_fails_on_bond_with_equity_shock(outputs):
    broken = copy.deepcopy(outputs[9102])
    s = scenario(broken, "Global Equity Crash")
    next(r for r in s["class_breakdown"] if r["asset_class"] == "bond")["shock_pct"] = -20.0
    out = assert_outcome(sc.check_stress_shock_table(ctx_with_stress({9102: broken}), P(9102)), "fail")
    assert out["evidence"][0]["observed"] == -20.0 and out["evidence"][0]["expected"] == -3.0


def test_shock_table_fails_on_unknown_without_flag(outputs):
    broken = copy.deepcopy(outputs[9103])
    scenario(broken, "Bond Selloff").pop("flags")
    out = assert_outcome(sc.check_stress_shock_table(ctx_with_stress({9103: broken}), P(9103)), "fail")
    assert out["evidence"][0]["expected"] == "unknown_asset_class_equity_shock"


def test_shock_table_skip_empty(outputs):
    assert_outcome(sc.check_stress_shock_table(ctx_with_stress(outputs), P(9106)), "skip", "empty_portfolio")


# ---------------------------------------------------------------------------
# A-STRESS-NONEQUITY-POSITION-SHOCK (V365-002)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_nonequity_position_pass(outputs, pid):
    assert_outcome(sc.check_stress_nonequity_position_shock(ctx_with_stress(outputs), P(pid)), "pass")


def test_nonequity_position_tech_multiplier_accepted(outputs):
    tech = scenario(outputs[9101], "US Tech Crash")
    assert {"symbol": "AUDTECH.DE", "loss_pct": -45.0, "asset_class": "equity"} in tech["most_impacted"]


def test_nonequity_position_fails_with_legacy_table():
    broken = stress_output(holdings_of(9103), shock_scenarios=legacy_shock_table())
    out = assert_outcome(sc.check_stress_nonequity_position_shock(ctx_with_stress({9103: broken}), P(9103)), "fail")
    gold = next(e for e in out["evidence"]
                if e["path"] == "scenarios[scenario_name=US Tech Crash].most_impacted[symbol=AUDGLD.DE].loss_pct")
    assert gold["observed"] == -30.0 and gold["expected"] == 0.0


def test_nonequity_position_fails_on_bond_etf_at_minus_30(outputs):
    broken = copy.deepcopy(outputs[9102])
    tech = scenario(broken, "US Tech Crash")
    tech["most_impacted"] = [{"symbol": "AUDGOV.MI", "loss_pct": -30.0, "asset_class": "bond"}]
    out = assert_outcome(sc.check_stress_nonequity_position_shock(ctx_with_stress({9102: broken}), P(9102)), "fail")
    assert out["evidence"][0]["expected"] == 2.0


def test_nonequity_position_fails_on_zero_loss(outputs):
    broken = copy.deepcopy(outputs[9103])
    scenario(broken, "US Tech Crash")["most_impacted"].append(
        {"symbol": "AUDGLD.DE", "loss_pct": 0.0, "asset_class": "gold"})
    assert_outcome(sc.check_stress_nonequity_position_shock(ctx_with_stress({9103: broken}), P(9103)), "fail")


def test_nonequity_position_skips(outputs):
    assert_outcome(sc.check_stress_nonequity_position_shock(ctx_with_stress(outputs), P(9106)),
                   "skip", "empty_portfolio")
    none = copy.deepcopy(outputs[9102])
    for s in none["scenarios"]:
        s.pop("most_impacted", None)
    assert_outcome(sc.check_stress_nonequity_position_shock(ctx_with_stress({9102: none}), P(9102)),
                   "skip", "not_applicable")


# ---------------------------------------------------------------------------
# A-CLASS-STRESS-CONSISTENT (V365-002, V365-012)
# ---------------------------------------------------------------------------


def ctx_consistent(pid: int, stress: dict, positions: dict | None = None) -> FakeAuditContext:
    positions = positions if positions is not None else positions_output(pid)
    responses = [("get_positions", {"portfolio_id": pid}, positions), ("get_stress_test", {"portfolio_id": pid}, stress)]
    responses += [("search_asset_info", {"portfolio_id": pid, "symbol": r["symbol"]}, asset_info(pid, r["symbol"]))
                  for r in positions["positions"]]
    return FakeAuditContext(responses)


@pytest.mark.parametrize("pid", [9101, 9102, 9103])
def test_class_stress_consistent_pass(outputs, pid):
    assert_outcome(sc.check_class_stress_consistent(ctx_consistent(pid, outputs[pid]), P(pid)), "pass")


@pytest.mark.parametrize("pid", [9102, 9103])
def test_class_stress_consistent_fails_with_legacy_shock_class(pid):
    with mock.patch.object(_stress, "_shock_asset_class", legacy_shock_asset_class):
        broken = stress_output(holdings_of(pid))
    out = assert_outcome(sc.check_class_stress_consistent(ctx_consistent(pid, broken), P(pid)), "fail")
    tools = {e["tool"] for e in out["evidence"]}
    assert {"get_stress_test", "get_positions"} <= tools
    equity = next(e for e in out["evidence"] if e["tool"] == "get_stress_test" and "asset_class=equity" in e["path"])
    assert equity["observed"] > (equity["expected"] or 0.0)


def test_class_stress_consistent_skips(outputs):
    empty = {"positions": []}
    assert_outcome(sc.check_class_stress_consistent(
        FakeAuditContext([("get_positions", {"portfolio_id": 9106}, empty)]), P(9106)), "skip", "empty_portfolio")
    truncated = {"positions": [dict(positions_output(9101)["positions"][0], symbol=f"S{i}") for i in range(30)]}
    assert_outcome(sc.check_class_stress_consistent(
        FakeAuditContext([("get_positions", {"portfolio_id": 9101}, truncated)]), P(9101)), "skip", "truncated_output")


def test_class_stress_consistent_tool_error_propagates(outputs):
    ctx = FakeAuditContext([("get_positions", {"portfolio_id": 9101}, RuntimeError("boom"))])
    with pytest.raises(FakeToolError):
        sc.check_class_stress_consistent(ctx, P(9101))


# ---------------------------------------------------------------------------
# A-CLASS-ETC-NOT-EQUITY (V365-012)
# ---------------------------------------------------------------------------


def test_etc_not_equity_pass():
    info = asset_info(9103, "AUDGLD.DE")
    assert (info["type"], info["instrument_type"], info["asset_class"]) == ("stock", "etc", "gold")
    out = assert_outcome(sc.check_class_etc_not_equity(ctx_instrument(9103, "AUDGLD.DE"), I(9103, "AUDGLD.DE")), "pass")
    assert out["evidence"][0]["args"] == {"portfolio_id": 9103, "symbol": "AUDGLD.DE"}


def test_etc_not_equity_fails_with_legacy_quote_type_map():
    real = copilot_tools.classify_asset

    def legacy(**kwargs):
        # QUOTE_TYPE_MAP vecchio: EQUITY -> stock -> equity, senza la regola ETC del classificatore.
        result = real(**kwargs)
        if (kwargs.get("asset_type") or "").lower() == "stock":
            return type(result)("equity", "default", False, result.instrument_type)
        return result

    with mock.patch.object(copilot_tools, "classify_asset", legacy):
        info = asset_info(9103, "AUDGLD.DE")
    out = assert_outcome(sc.check_class_etc_not_equity(ctx_instrument(9103, "AUDGLD.DE", info=info),
                                                       I(9103, "AUDGLD.DE")), "fail")
    assert out["evidence"][0]["observed"] == "equity"
    assert out["evidence"][0]["expected"] == ["gold", "commodity"]


def test_etc_not_equity_skip_for_etf():
    assert_outcome(sc.check_class_etc_not_equity(ctx_instrument(9101, "AUDEQ.MI"), I(9101, "AUDEQ.MI")),
                   "skip", "not_applicable")


def test_etc_not_equity_etn_on_silver_must_not_be_equity():
    info = {"symbol": "AUDSLV", "name": "AUD Silver ETN", "type": "stock", "asset_class": "equity",
            "instrument_type": "etn"}
    assert_outcome(sc.check_class_etc_not_equity(ctx_instrument(9103, "AUDSLV", info=info), I(9103, "AUDSLV")),
                   "fail")


# ---------------------------------------------------------------------------
# A-CLASS-ETP-TER-NONZERO (V365-012, V365-007)
# ---------------------------------------------------------------------------


def test_etp_ter_nonzero_pass():
    costs = cost_output(9103)
    row = next(r for r in costs["position_costs"] if r["symbol"] == "AUDGLD.DE")
    assert row["ter_source"] == "inferred" and row["ter_pct"] == 0.15
    out = assert_outcome(sc.check_class_etp_ter_nonzero(ctx_instrument(9103, "AUDGLD.DE", costs=costs),
                                                        I(9103, "AUDGLD.DE")), "pass")
    assert {e["tool"] for e in out["evidence"]} == {"search_asset_info", "get_cost_breakdown"}


def test_etp_ter_nonzero_fails_with_legacy_infer_ter():
    costs = cost_output(9103, infer=legacy_infer_ter)
    out = assert_outcome(sc.check_class_etp_ter_nonzero(ctx_instrument(9103, "AUDGLD.DE", costs=costs),
                                                        I(9103, "AUDGLD.DE")), "fail")
    cost_ev = next(e for e in out["evidence"] if e["tool"] == "get_cost_breakdown")
    assert cost_ev["observed"] == 0.0 and cost_ev["path"] == "position_costs[symbol=AUDGLD.DE].ter_pct"


def test_etp_ter_nonzero_skips():
    # Titolo diretto (bond): fuori dall'insieme degli ETP.
    assert_outcome(sc.check_class_etp_ter_nonzero(ctx_instrument(9102, "AUDBTP"), I(9102, "AUDBTP")),
                   "skip", "not_applicable")
    costs = cost_output(9103)
    costs["position_costs"] = [r for r in costs["position_costs"] if r["symbol"] != "AUDGLD.DE"]
    assert_outcome(sc.check_class_etp_ter_nonzero(ctx_instrument(9103, "AUDGLD.DE", costs=costs),
                                                  I(9103, "AUDGLD.DE")), "skip", "truncated_output")


# ---------------------------------------------------------------------------
# A-CLASS-BOND-TYPE (V-BOND-QUOTETYPE)
# ---------------------------------------------------------------------------


def test_bond_type_pass():
    assert_outcome(sc.check_class_bond_type(ctx_instrument(9102, "AUDBTP"), I(9102, "AUDBTP")), "pass")


def test_bond_type_fails_on_etf_stored_as_bond():
    # resolve_refreshed_asset_type che trasforma un etf con quote type BOND in bond.
    info = asset_info(9108, "AUDCORP.MI")
    assert info["type"] == "bond"
    out = assert_outcome(sc.check_class_bond_type(ctx_instrument(9108, "AUDCORP.MI", info=info),
                                                  I(9108, "AUDCORP.MI")), "fail")
    assert "UCITS" in out["evidence"][0]["note"] and "ETF" in out["evidence"][0]["note"]


def test_bond_type_whole_word_only():
    info = {"symbol": "AUDX", "name": "Fondazione Bond 2031 Etfx", "type": "bond", "asset_class": "bond"}
    assert_outcome(sc.check_class_bond_type(ctx_instrument(9102, "AUDX", info=info), I(9102, "AUDX")), "pass")


def test_bond_type_skip_when_not_bond():
    assert_outcome(sc.check_class_bond_type(ctx_instrument(9102, "AUDGOV.MI"), I(9102, "AUDGOV.MI")),
                   "skip", "not_applicable")


# ---------------------------------------------------------------------------
# A-CLASS-UNKNOWN-DECLARED (V365-002, decisione 3)
# ---------------------------------------------------------------------------


def test_unknown_declared_pass(outputs):
    assert asset_info(9103, "AUDTHM.DE")["asset_class"] == "unknown"
    assert_outcome(sc.check_class_unknown_declared(ctx_instrument(9103, "AUDTHM.DE", stress=outputs[9103]),
                                                   I(9103, "AUDTHM.DE")), "pass")


def test_unknown_declared_fails_when_merged_into_equity(outputs):
    # Strumento unknown sommato alla riga equity senza flag.
    with mock.patch.object(_stress, "_shock_asset_class",
                           lambda h: "equity" if _stress.holding_asset_class(h) == "unknown"
                           else _stress.holding_asset_class(h)):
        broken = stress_output(holdings_of(9103))
    out = assert_outcome(sc.check_class_unknown_declared(ctx_instrument(9103, "AUDTHM.DE", stress=broken),
                                                         I(9103, "AUDTHM.DE")), "fail")
    assert {e["expected"] for e in out["evidence"]} == {"unknown_asset_class_equity_shock", "contiene unknown"}


def test_unknown_declared_skip_when_classified(outputs):
    assert_outcome(sc.check_class_unknown_declared(ctx_instrument(9103, "AUDGLD.DE", stress=outputs[9103]),
                                                   I(9103, "AUDGLD.DE")), "skip", "not_applicable")
