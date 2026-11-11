"""TASK-77: regole del gruppo D dell'Auditor (coerenza fra tool, vista aggregata e dati).

Per ogni regola: pass su dati corretti, fail quando si reintroduce il difetto del finding
(output sbagliato riprodotto), skip con il codice giusto quando i dati non bastano.
Le risposte finte hanno le chiavi reali dei tool: positions, summary, cash balance e le
varianti aggregate sono prodotte dagli handler veri (``copilot_tools`` e
``mcp_server.aggregate_tools``) su repository finti; le altre copiano la forma di
``copilot_tools.py`` / ``copilot_doctor_tools.py`` / ``services/performance_audit.py``.
"""

from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import jsonschema
import pytest

from app.copilot_doctor_tools import POLICY_DISABLED_MESSAGE
from app.copilot_tools import _get_cash_balance, _get_portfolio_summary, _get_positions
from app.mcp_server.aggregate_tools import AGGREGATE_NOTE, _positions as agg_positions_handler
from app.mcp_server.aggregate_tools import _summary as agg_summary_handler
from app.services.auditor import offline_returns
from app.services.auditor.rules import consistency as D

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA = json.loads((REPO_ROOT / "docs" / "auditor" / "schemas" / "report.schema.json").read_text(encoding="utf-8"))
OUTCOME_VALIDATOR = jsonschema.Draft202012Validator({"$ref": "#/$defs/Outcome", "$defs": SCHEMA["$defs"]})
SCRIPT = REPO_ROOT / "scripts" / "audit" / "twr_mwr_offline_auditor.py"

# --------------------------------------------------------------------------
# Contesto finto di riferimento (architecture.md §10, copiato)
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Builder delle risposte con gli handler veri
# --------------------------------------------------------------------------

P1, P3, P6 = 9101, 9103, 9106
SCOPE_P1 = {"kind": "portfolio", "portfolio_id": P1}
SCOPE_P3 = {"kind": "portfolio", "portfolio_id": P3}
SCOPE_P6 = {"kind": "portfolio", "portfolio_id": P6}
SCOPE_AGG = {"kind": "aggregate", "portfolio_ids": [P1, P3]}


def holding(symbol: str, qty: float, price: float, avg_cost: float, *, asset_id: int = 0, **extra: Any):
    return SimpleNamespace(
        asset_id=asset_id or abs(hash(symbol)) % 100000, symbol=symbol, name=f"{symbol} UCITS ETF",
        quantity=qty, market_price=price, market_value=qty * price, avg_cost=avg_cost,
        unrealized_pl_pct=(price / avg_cost - 1) * 100 if avg_cost else 0.0, day_change_pct=0.4,
        weight=0.0, price_fallback=extra.get("price_fallback"), fx_missing=extra.get("fx_missing", False),
        price_date=None, price_stale=extra.get("price_stale", False), stale_reason=extra.get("stale_reason"),
        last_price_at=None,
    )


def weigh(holdings: list, extra_total: float = 0.0) -> list:
    """Pesi come _positions.py: market_value / totale × 100 (extra_total = difetto con la liquidità)."""
    total = sum(h.market_value for h in holdings) + extra_total
    for h in holdings:
        h.weight = h.market_value / total * 100 if total else 0.0
    return holdings


def positions_out(holdings: list) -> dict:
    repo = SimpleNamespace(get_positions=lambda pid, uid: holdings)
    return _get_positions({}, repo, None, 1, "u")


def merge(*portfolios: list) -> list:
    """Come get_positions_multi: una riga per strumento, pesi sul totale."""
    merged: dict[str, Any] = {}
    for rows in portfolios:
        for h in rows:
            if h.symbol not in merged:
                merged[h.symbol] = copy.copy(h)
                merged[h.symbol].cost = h.avg_cost * h.quantity
                continue
            m = merged[h.symbol]
            m.cost += h.avg_cost * h.quantity
            m.quantity += h.quantity
            m.market_value += h.market_value
            m.avg_cost = m.cost / m.quantity
    return weigh(list(merged.values()))


def agg_positions_out(holdings: list, ids: list[int]) -> dict:
    deps = SimpleNamespace(repo=SimpleNamespace(get_positions_multi=lambda i, u: holdings))
    return {"portfolio_ids": ids, "base_currency": "EUR", "aggregate_note": AGGREGATE_NOTE,
            **agg_positions_handler(deps, ids, "u")}


def summary_ns(market_value: float, cost_basis: float, cash: float, implicit: float = 0.0, **flags: Any):
    return SimpleNamespace(
        market_value=market_value, cost_basis=cost_basis, unrealized_pl=market_value - cost_basis,
        unrealized_pl_pct=(market_value / cost_basis - 1) * 100 if cost_basis else 0.0,
        day_change=3.2, day_change_pct=0.3, cash_balance=cash, implicit_contributions_total=implicit,
        base_currency="EUR", fx_missing_currencies=flags.get("fx_missing_currencies", []),
        price_fallback_symbols=flags.get("price_fallback_symbols", []),
        stale_price_symbols=flags.get("stale_price_symbols", []),
    )


def summary_out(ns) -> dict:
    return _get_portfolio_summary({}, SimpleNamespace(get_summary=lambda pid, uid: ns), None, 1, "u")


def agg_summary_out(ns, ids: list[int]) -> dict:
    deps = SimpleNamespace(repo=SimpleNamespace(get_summary_multi=lambda i, u: ns))
    return {"portfolio_ids": ids, "base_currency": "EUR", "aggregate_note": AGGREGATE_NOTE,
            **agg_summary_handler(deps, ids, "u")}


def summary_of(holdings: list, cash: float, implicit: float = 0.0, **flags: Any):
    mv = sum(h.market_value for h in holdings)
    cb = sum(round(h.avg_cost * h.quantity, 2) for h in holdings)
    return summary_ns(mv, cb, cash, implicit, **flags)


def cash_out(balance: float, components: dict, implicit: float = 0.0, fx_missing: Sequence[str] = ()) -> dict:
    detail = SimpleNamespace(balance=balance, implicit_contributions=implicit, components=components,
                             fx_missing_currencies=list(fx_missing))
    repo = SimpleNamespace(get_current_cash_balance_detail=lambda pid, uid: detail,
                           get_portfolio_base_currency=lambda pid, uid: "EUR")
    return _get_cash_balance({}, repo, None, 1, "u")


def p1_holdings() -> list:
    return weigh([holding("AUDEQ.MI", 7, 100.0, 95.0, asset_id=9201), holding("AUDBD.MI", 4, 50.0, 52.0, asset_id=9202),
                  holding("AUDTECH.DE", 2, 50.0, 40.0, asset_id=9203)])


def p3_holdings() -> list:
    return weigh([holding("AUDGLD.DE", 4, 100.0, 90.0, asset_id=9207), holding("AUDEQ.MI", 2.5, 100.0, 96.0, asset_id=9201),
                  holding("AUDCMD.MI", 2, 100.0, 105.0, asset_id=9208), holding("AUDTHM.DE", 3, 50.0, 50.0, asset_id=9209)])


def check(rule_check, ctx, scope) -> dict:
    out = rule_check(ctx, scope)
    OUTCOME_VALIDATOR.validate(out)
    json.dumps(out)
    return out


def assert_status(out: dict, status: str, code: str | None = None) -> None:
    assert out["status"] == status, out
    if code is not None:
        assert out["reason_code"] == code, out


# --------------------------------------------------------------------------
# Dichiarazioni e import
# --------------------------------------------------------------------------

CATALOG = {
    "D-WEIGHTS-SUM": ("P1", "values", [], ["portfolio", "aggregate"]),
    "D-SUMMARY-POSITIONS": ("P1", "values", [], ["portfolio", "aggregate"]),
    "D-POSITION-VALUE-PRICE": ("P2", "values", ["V365-008"], ["portfolio", "aggregate"]),
    "D-CASH-CONSISTENCY": ("P1", "values", ["C2-CASH-FX"], ["portfolio"]),
    "D-SUMMARY-PERFORMANCE-VALUE": ("P1", "performance", ["C1-TWR-MIXED", "TASK-49"], ["portfolio", "aggregate"]),
    "D-AGG-SUMS": ("P1", "aggregate", ["V365-011"], ["aggregate"]),
    "D-AGG-POSITIONS": ("P1", "aggregate", ["V365-011"], ["aggregate"]),
    "D-AGG-PERFORMANCE-VALUE": ("P2", "aggregate", ["V365-011"], ["aggregate"]),
    "D-PERF-RECOMPUTE": ("P1", "performance", ["C1-TWR-MIXED"], ["portfolio", "aggregate"]),
    "D-PERF-TOOL-MATCH": ("P2", "performance", ["C1-TWR-MIXED"], ["portfolio", "aggregate"]),
    "D-DOCTOR-TER": ("P1", "doctor", ["V365-007"], ["portfolio"]),
    "D-DOCTOR-CLASS-WEIGHTS": ("P1", "doctor", ["V365-002"], ["portfolio"]),
    "D-DOCTOR-CONCENTRATION": ("P2", "doctor", ["V365-010"], ["portfolio"]),
    "D-HEALTH-SCORE-BREAKDOWN": ("P2", "doctor", ["V365-010"], ["portfolio", "aggregate"]),
    "D-XRAY-SUMS": ("P2", "values", ["C6"], ["portfolio", "aggregate"]),
    "D-DUP-TRANSACTIONS": ("P1", "data", ["V365-009", "V-DUP-IMPORT"], ["portfolio"]),
    "D-TRADE-PRICE-SCALE": ("P1", "data", ["V-XLSX-1000", "V365-008", "V-QUOTE-CCY-L"], ["portfolio"]),
    "D-LSE-QUOTE-CURRENCY": ("P1", "data", ["V-QUOTE-CCY-L", "V365-008"], ["instrument"]),
    "D-FX-FLAGS-DECLARED": ("P2", "values", ["C4-FX-FALLBACK"], ["portfolio", "aggregate"]),
    "D-HELD-SYMBOL-MATCH": ("P2", "data", ["V-LOOSE-SYMBOL"], ["instrument"]),
}


def test_declarations_match_the_catalog():
    assert [r["id"] for r in D.RULES] == list(CATALOG)
    rules_md = (REPO_ROOT / "docs" / "auditor" / "rules.md").read_text(encoding="utf-8")
    for rule in D.RULES:
        severity, area, findings, scopes = CATALOG[rule["id"]]
        assert rule["group"] == "D" and rule["id"].startswith("D-")
        assert (rule["severity"], rule["area"], rule["findings"], rule["scopes"]) == (severity, area, findings, scopes)
        assert callable(rule["check"]) and rule["tools"]
        assert f"### {rule['id']}\n- **Titolo:** {rule['title']}\n" in rules_md
    assert next(r for r in D.RULES if r["id"] == "D-PERF-RECOMPUTE")["timeout_s"] == 60.0


def test_rule_module_imports_only_what_the_contract_allows():
    tree = ast.parse(Path(D.__file__).read_text(encoding="utf-8"))
    allowed_app = {"app.copilot_doctor_tools", "app.services.auditor.offline_returns"}
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            name = node.module or ""
        elif isinstance(node, ast.Import):
            name = node.names[0].name
        else:
            continue
        assert name in allowed_app or name.split(".")[0] in stdlib, name


# --------------------------------------------------------------------------
# D-WEIGHTS-SUM
# --------------------------------------------------------------------------


def test_weights_sum_pass_portfolio_and_aggregate():
    ctx = FakeAuditContext([
        ("get_positions", {"portfolio_id": P1}, positions_out(p1_holdings())),
        ("get_aggregate_positions", {"portfolio_ids": [P1, P3]},
         agg_positions_out(merge(p1_holdings(), p3_holdings()), [P1, P3])),
    ])
    assert_status(check(D.check_weights_sum, ctx, SCOPE_P1), "pass")
    assert_status(check(D.check_weights_sum, ctx, SCOPE_AGG), "pass")


def test_weights_sum_fails_when_weights_include_cash():
    # Difetto: pesi calcolati su posizioni + liquidità (94,80 €) -> somma 91,34.
    ctx = FakeAuditContext([("get_positions", {"portfolio_id": P1},
                             positions_out(weigh(p1_holdings(), extra_total=94.80)))])
    out = check(D.check_weights_sum, ctx, SCOPE_P1)
    assert_status(out, "fail", "invariant_violated")
    assert out["evidence"][0]["observed"] == pytest.approx(91.34, abs=0.01)


def test_weights_sum_skips_empty_and_truncated():
    many = weigh([holding(f"AUD{i:02d}.MI", 1, 10.0, 10.0) for i in range(35)])
    ctx = FakeAuditContext([
        ("get_positions", {"portfolio_id": P6}, positions_out([])),
        ("get_positions", {"portfolio_id": P1}, positions_out(many)),
        ("get_aggregate_positions", {"portfolio_ids": [P1, P3]}, agg_positions_out(many, [P1, P3])),
    ])
    assert_status(check(D.check_weights_sum, ctx, SCOPE_P6), "skip", "empty_portfolio")
    assert_status(check(D.check_weights_sum, ctx, SCOPE_P1), "skip", "truncated_output")
    assert_status(check(D.check_weights_sum, ctx, SCOPE_AGG), "skip", "truncated_output")


# --------------------------------------------------------------------------
# D-SUMMARY-POSITIONS
# --------------------------------------------------------------------------


def _summary_positions_ctx(summary: dict) -> FakeAuditContext:
    return FakeAuditContext([
        ("get_portfolio_summary", {"portfolio_id": P1}, summary),
        ("get_positions", {"portfolio_id": P1}, positions_out(p1_holdings())),
        ("get_portfolio_summary", {"portfolio_id": P6}, summary_out(summary_ns(0, 0, 0))),
        ("get_positions", {"portfolio_id": P6}, positions_out([])),
    ])


def test_summary_positions_pass():
    ctx = _summary_positions_ctx(summary_out(summary_of(p1_holdings(), 94.80)))
    assert_status(check(D.check_summary_positions, ctx, SCOPE_P1), "pass")
    agg = merge(p1_holdings(), p3_holdings())
    ctx = FakeAuditContext([
        ("get_aggregate_summary", {"portfolio_ids": [P1, P3]}, agg_summary_out(summary_of(agg, 200.0), [P1, P3])),
        ("get_aggregate_positions", {"portfolio_ids": [P1, P3]}, agg_positions_out(agg, [P1, P3])),
    ])
    assert_status(check(D.check_summary_positions, ctx, SCOPE_AGG), "pass")


def test_summary_positions_fails_when_summary_adds_cash_to_market_value():
    s = summary_of(p1_holdings(), 94.80)
    s.market_value += s.cash_balance  # difetto: liquidità nel market_value
    s.unrealized_pl = s.market_value - s.cost_basis
    out = check(D.check_summary_positions, _summary_positions_ctx(summary_out(s)), SCOPE_P1)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "market_value"


def test_summary_positions_skips_empty():
    ctx = _summary_positions_ctx(summary_out(summary_of(p1_holdings(), 94.80)))
    assert_status(check(D.check_summary_positions, ctx, SCOPE_P6), "skip", "empty_portfolio")


# --------------------------------------------------------------------------
# D-POSITION-VALUE-PRICE
# --------------------------------------------------------------------------


def test_position_value_price_pass_and_fail_on_quantity_divided_by_thousand():
    ctx = FakeAuditContext([("get_positions", {"portfolio_id": P1}, positions_out(p1_holdings()))])
    assert_status(check(D.check_position_value_price, ctx, SCOPE_P1), "pass")
    bad = p1_holdings()
    bad[0].quantity = bad[0].quantity / 1000  # difetto V-XLSX-1000: quantità ÷ 1000, prezzo invariato
    ctx = FakeAuditContext([("get_positions", {"portfolio_id": P1}, positions_out(bad))])
    out = check(D.check_position_value_price, ctx, SCOPE_P1)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "positions[symbol=AUDEQ.MI].market_value"


def test_position_value_price_skips_empty():
    ctx = FakeAuditContext([("get_aggregate_positions", {"portfolio_ids": [P1, P3]}, agg_positions_out([], [P1, P3]))])
    assert_status(check(D.check_position_value_price, ctx, SCOPE_AGG), "skip", "empty_portfolio")


# --------------------------------------------------------------------------
# D-CASH-CONSISTENCY (esempio §9.1 della metodologia)
# --------------------------------------------------------------------------

CASH_91 = {"opening_balance": 0.0, "deposits": 1000.0, "withdrawals": 0.0, "dividends": 14.8, "interest": 0.0,
           "fees": 0.0, "buys": 800.0, "sells": 330.0, "implicit_contributions": 0.0}


def _cash_ctx(summary_cash: float, cash: dict, pid: int = P1) -> FakeAuditContext:
    return FakeAuditContext([
        ("get_portfolio_summary", {"portfolio_id": pid}, summary_out(summary_ns(550.0, 500.0, summary_cash))),
        ("get_cash_balance", {"portfolio_id": pid}, cash),
    ])


def test_cash_consistency_pass_also_on_empty_portfolio():
    assert_status(check(D.check_cash_consistency, _cash_ctx(544.80, cash_out(544.80, CASH_91)), SCOPE_P1), "pass")
    zero = {k: 0.0 for k in CASH_91}
    assert_status(check(D.check_cash_consistency, _cash_ctx(0.0, cash_out(0.0, zero), P6), SCOPE_P6), "pass")


def test_cash_consistency_fails_when_summary_ignores_buys_and_sells_task49():
    out = check(D.check_cash_consistency, _cash_ctx(1014.80, cash_out(544.80, CASH_91)), SCOPE_P1)
    assert_status(out, "fail")
    assert {e["path"] for e in out["evidence"]} >= {"cash_balance", "total_cash"}


def test_cash_consistency_fails_on_latest_fx_vs_trade_date_fx_task47():
    # get_cash_balance al cambio più recente: saldo diverso dalla somma delle componenti e dal riepilogo.
    out = check(D.check_cash_consistency, _cash_ctx(544.80, cash_out(540.12, CASH_91)), SCOPE_P1)
    assert_status(out, "fail")


def test_cash_consistency_fails_on_unknown_component():
    out = check(D.check_cash_consistency, _cash_ctx(544.80, cash_out(544.80, {**CASH_91, "transfers": 0.0})), SCOPE_P1)
    assert_status(out, "fail")
    assert any(e["path"] == "cash_breakdown.transfers" for e in out["evidence"])


# --------------------------------------------------------------------------
# Export della performance (forma di build_performance_audit_export)
# --------------------------------------------------------------------------


def make_export(ids: list[int], flows: list[tuple[str, float, str]], values: dict[str, float], *,
                start: str = "2025-11-11", end: str = "2026-11-11", service: dict | None = None,
                consistency: dict | None = None) -> dict:
    """flows: (data, importo, side). service: {"twr_pct", "mwr_pct"}; default = ricalcolo offline."""
    rows, net = [], {}
    for day, amount, side in flows:
        synthetic = side == "implicit_contribution"
        row = {"date": day, "amount_eur": amount, "side": side,
               "source": "cash_model" if synthetic else "transaction", "portfolio_id": ids[0],
               "synthetic_flow": synthetic, "in_twr_mwr": day > start}
        if synthetic:
            row["reason"] = "cash_shortfall_end_of_day"
        rows.append(row)
        net[day] = net.get(day, 0.0) + amount
    days = sorted({start, end} | set(net))
    export = {
        "portfolio_ids": ids, "period": "1y", "start_date": start, "end_date": end, "period_days": 365,
        "valuation_method": "end_of_day; flows on start day included in start value; ACT/365",
        "generated_at": "2026-11-11T08:00:00+00:00",
        "valuation_start": values[start], "valuation_before_start": 0.0, "valuation_end": values[end],
        "external_flows": rows, "implicit_flows": [r for r in rows if r["synthetic_flow"]],
        "total_implicit_flows": sum(1 for r in rows if r["synthetic_flow"]),
        "net_flows_by_date": [{"date": d, "amount_eur": round(a, 8), "in_twr_mwr": d > start} for d, a in sorted(net.items())],
        "valuation_on_flow_dates": [{"date": d, "value_eur": values.get(d)} for d in days],
        "service_results": {
            "source": "get_performance_summary",
            "twr": {"twr_pct": None, "twr_annualized_pct": None, "period_days": 365, "start_date": start, "end_date": end},
            "mwr": {"mwr_pct": None, "mwr_annualized_pct": None, "period_days": 365, "start_date": start,
                    "end_date": end, "converged": True, "multiple_roots": False},
            "initial_value": values[start], "current_value": values[end],
            "net_invested": sum(a for _, a, _s in flows), "implicit_contributions": 0.0,
        },
        "consistency_check": {
            "flows_match_service": True, "count_match": True, "totals_match": True,
            "export_flow_count": len(rows), "service_flow_count": len(rows),
            "export_total_amount_eur": sum(a for _, a, _s in flows),
            "service_total_amount_eur": sum(a for _, a, _s in flows), "service_implicit_only": False,
            **(consistency or {}),
        },
        "data_quality": {"fx_missing": [], "prices_missing": [], "notes": []},
        "total_flows": len(rows), "offset": 0, "limit": 200, "truncated": False,
    }
    if service is None:
        audited = offline_returns.audit(export)
        service = {"twr_pct": round(audited["twr"]["twr_pct"], 4) if audited["twr"]["twr_pct"] is not None else None,
                   "mwr_pct": round(audited["xirr"]["mwr_pct"], 4) if audited["xirr"]["mwr_pct"] is not None else None}
    export["service_results"]["twr"]["twr_pct"] = service["twr_pct"]
    export["service_results"]["mwr"]["mwr_pct"] = service["mwr_pct"]
    return export


# Caso C1-TWR-MIXED: deposito 500 il primo giorno, acquisto 10 × 100 a prezzo piatto (scoperto 500 =
# apporto implicito). Modello corretto: valore 1000, TWR 0%, MWR 0%.
C1_FLOWS = [("2025-11-11", 500.0, "deposit"), ("2026-01-12", 500.0, "implicit_contribution")]
C1_VALUES = {"2025-11-11": 500.0, "2026-01-12": 1000.0, "2026-11-11": 1000.0}


def tx(tid: int, side: str, day: str, qty: float, price: float, *, symbol: str | None = "AUDEQ.MI",
       asset_id: int | None = 9201, fees: float = 0.0, ccy: str = "EUR") -> dict:
    return {"id": tid, "asset_id": asset_id,
            "symbol": symbol, "side": side, "trade_at": f"{day}T10:00:00+00:00", "trade_date": day,
            "quantity": qty, "price": price, "fees": fees, "taxes": 0.0, "trade_currency": ccy}


TX_P1 = [tx(3, "buy", "2026-01-12", 10, 100.0), tx(2, "deposit", "2025-11-11", 1, 500.0, symbol=None, asset_id=None)]


# --------------------------------------------------------------------------
# D-SUMMARY-PERFORMANCE-VALUE (esempio §9.1: 5 × 110 + 544,80 = 1094,80)
# --------------------------------------------------------------------------

H_91 = [holding("AUDEQ.MI", 5, 110.0, 100.0, asset_id=9201)]
EXPORT_91 = make_export([P1], [("2025-11-11", 1000.0, "deposit")],
                        {"2025-11-11": 1000.0, "2026-11-11": 1094.80})


def _summary_perf_ctx(summary_cash: float, transactions=None) -> FakeAuditContext:
    return FakeAuditContext(
        [("get_portfolio_summary", {"portfolio_id": P1}, summary_out(summary_of(weigh(H_91), summary_cash))),
         ("get_positions", {"portfolio_id": P1}, positions_out(weigh(H_91)))],
        transactions=transactions if transactions is not None else {P1: TX_P1},
        performance_audit={(P1,): EXPORT_91},
    )


def test_summary_performance_value_pass():
    assert_status(check(D.check_summary_performance_value, _summary_perf_ctx(544.80), SCOPE_P1), "pass")


def test_summary_performance_value_pass_aggregate():
    agg = merge(p1_holdings(), p3_holdings())
    export = make_export([P1, P3], [("2025-11-11", 2000.0, "deposit")], {"2025-11-11": 2000.0, "2026-11-11": 2150.0})
    ctx = FakeAuditContext(
        [("get_aggregate_summary", {"portfolio_ids": [P1, P3]}, agg_summary_out(summary_of(agg, 150.0), [P1, P3])),
         ("get_aggregate_positions", {"portfolio_ids": [P1, P3]}, agg_positions_out(agg, [P1, P3]))],
        transactions={P1: TX_P1, P3: []}, performance_audit={(P1, P3): export},
    )
    assert_status(check(D.check_summary_performance_value, ctx, SCOPE_AGG), "pass")


def test_summary_performance_value_fails_on_double_counted_cash_task49():
    # Difetto TASK-49: la liquidità del riepilogo non scala gli acquisti -> 1564,80 invece di 1094,80.
    out = check(D.check_summary_performance_value, _summary_perf_ctx(1014.80), SCOPE_P1)
    assert_status(out, "fail")
    assert out["evidence"][0]["observed"] == pytest.approx(1564.80)
    assert out["evidence"][0]["expected"] == pytest.approx(1094.80)


def test_summary_performance_value_skips_without_transactions():
    ctx = _summary_perf_ctx(544.80, transactions={P1: []})
    assert_status(check(D.check_summary_performance_value, ctx, SCOPE_P1), "skip", "no_transactions")
    ctx = FakeAuditContext(transactions={P1: [], P3: []})
    assert_status(check(D.check_summary_performance_value, ctx, SCOPE_AGG), "skip", "no_transactions")


# --------------------------------------------------------------------------
# D-AGG-SUMS
# --------------------------------------------------------------------------


def _agg_sums_ctx(agg_ns, ids_out: list[int] | None = None) -> FakeAuditContext:
    s1 = summary_of(p1_holdings(), 94.80, implicit=0.0)
    s3 = summary_of(p3_holdings(), 55.20, implicit=120.0)
    return FakeAuditContext([
        ("get_portfolio_summary", {"portfolio_id": P1}, summary_out(s1)),
        ("get_portfolio_summary", {"portfolio_id": P3}, summary_out(s3)),
        ("get_aggregate_summary", {"portfolio_ids": [P1, P3]}, agg_summary_out(agg_ns, ids_out or [P1, P3])),
    ])


def _agg_ns(**override: float):
    agg = merge(p1_holdings(), p3_holdings())
    ns = summary_of(agg, 150.0, implicit=120.0)
    for k, v in override.items():
        setattr(ns, k, v)
    return ns


def test_agg_sums_pass():
    assert_status(check(D.check_agg_sums, _agg_sums_ctx(_agg_ns()), SCOPE_AGG), "pass")


def test_agg_sums_fails_on_double_count_or_missing_cash():
    # V365-011: aggregazione manuale che conta due volte un portafoglio, o salta la liquidità.
    out = check(D.check_agg_sums, _agg_sums_ctx(_agg_ns(market_value=3000.0)), SCOPE_AGG)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "market_value"
    out = check(D.check_agg_sums, _agg_sums_ctx(_agg_ns(cash_balance=0.0)), SCOPE_AGG)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "cash_balance"


def test_agg_sums_fails_when_scope_differs():
    out = check(D.check_agg_sums, _agg_sums_ctx(_agg_ns(), ids_out=[P1]), SCOPE_AGG)
    assert_status(out, "fail")
    assert out["evidence"][-1]["path"] == "portfolio_ids"


# --------------------------------------------------------------------------
# D-AGG-POSITIONS
# --------------------------------------------------------------------------


def _agg_positions_ctx(agg_out: dict, singles: dict[int, list] | None = None) -> FakeAuditContext:
    singles = singles or {P1: p1_holdings(), P3: p3_holdings()}
    return FakeAuditContext(
        [("get_positions", {"portfolio_id": pid}, positions_out(h)) for pid, h in singles.items()]
        + [("get_aggregate_positions", {"portfolio_ids": [P1, P3]}, agg_out)]
    )


def test_agg_positions_pass():
    ctx = _agg_positions_ctx(agg_positions_out(merge(p1_holdings(), p3_holdings()), [P1, P3]))
    out = check(D.check_agg_positions, ctx, SCOPE_AGG)
    assert_status(out, "pass")


def test_agg_positions_fails_when_rows_of_the_same_instrument_are_not_merged():
    unmerged = weigh(p1_holdings() + p3_holdings())  # due righe AUDEQ.MI
    out = check(D.check_agg_positions, _agg_positions_ctx(agg_positions_out(unmerged, [P1, P3])), SCOPE_AGG)
    assert_status(out, "fail")
    paths = {e["path"] for e in out["evidence"]}
    assert "positions[symbol=AUDEQ.MI].market_value" in paths and "positions_count" in paths


def test_agg_positions_skips_empty_and_truncated():
    ctx = _agg_positions_ctx(agg_positions_out([], [P1, P3]))
    assert_status(check(D.check_agg_positions, ctx, SCOPE_AGG), "skip", "empty_portfolio")
    many = weigh([holding(f"AUD{i:02d}.MI", 1, 10.0, 10.0) for i in range(35)])
    other = weigh([holding("AUDZZZ.MI", 1, 10.0, 10.0)])
    agg = agg_positions_out(weigh([holding("AUDZZZ.MI", 1, 10.0, 10.0), holding("AUD34.MI", 1, 10.0, 10.0)]), [P1, P3])
    agg["positions"] = [r for r in agg["positions"] if r["symbol"] == "AUD34.MI"]  # solo righe non verificabili
    ctx = _agg_positions_ctx(agg, {P1: many, P3: other})
    assert_status(check(D.check_agg_positions, ctx, SCOPE_AGG), "skip", "truncated_output")


# --------------------------------------------------------------------------
# D-AGG-PERFORMANCE-VALUE
# --------------------------------------------------------------------------

SCOPE_AGG3 = {"kind": "aggregate", "portfolio_ids": [P1, P3, P6]}


def _agg_perf_ctx(agg_value: float, *, end_p3: str = "2026-11-11") -> FakeAuditContext:
    e1 = make_export([P1], [("2025-11-11", 1000.0, "deposit")], {"2025-11-11": 1000.0, "2026-11-11": 1094.80})
    e3 = make_export([P3], [("2026-02-02", 900.0, "deposit")], {"2025-11-11": 0.0, "2026-02-02": 900.0,
                                                                  end_p3: 905.20}, end=end_p3)
    agg = make_export([P1, P3, P6], [("2025-11-11", 1000.0, "deposit"), ("2026-02-02", 900.0, "deposit")],
                      {"2025-11-11": 1000.0, "2026-02-02": 1950.0, "2026-11-11": agg_value})
    return FakeAuditContext(transactions={P1: TX_P1, P3: TX_P1, P6: []},
                            performance_audit={(P1,): e1, (P3,): e3, (P1, P3, P6): agg})


def test_agg_performance_value_pass_member_without_transactions_counts_zero():
    ctx = _agg_perf_ctx(2000.0)
    assert_status(check(D.check_agg_performance_value, ctx, SCOPE_AGG3), "pass")


def test_agg_performance_value_fails_on_average_instead_of_sum():
    out = check(D.check_agg_performance_value, _agg_perf_ctx(1000.0), SCOPE_AGG3)
    assert_status(out, "fail")
    assert out["evidence"][0]["expected"] == pytest.approx(2000.0)


def test_agg_performance_value_fails_on_different_end_date():
    out = check(D.check_agg_performance_value, _agg_perf_ctx(2000.0, end_p3="2026-11-10"), SCOPE_AGG3)
    assert_status(out, "fail")
    assert any(e["path"] == "end_date" for e in out["evidence"])


def test_agg_performance_value_skips_when_no_member_has_transactions():
    ctx = FakeAuditContext(transactions={P1: [], P3: []})
    assert_status(check(D.check_agg_performance_value, ctx, SCOPE_AGG), "skip", "no_transactions")


# --------------------------------------------------------------------------
# D-PERF-RECOMPUTE
# --------------------------------------------------------------------------


def test_perf_recompute_pass_on_c1_case_and_aggregate():
    export = make_export([P1], C1_FLOWS, C1_VALUES)
    assert export["service_results"]["twr"]["twr_pct"] == pytest.approx(0.0, abs=1e-9)
    ctx = FakeAuditContext(transactions={P1: TX_P1}, performance_audit={(P1,): export})
    assert_status(check(D.check_perf_recompute, ctx, SCOPE_P1), "pass")
    agg = make_export([P1, P3], [("2025-11-11", 1000.0, "deposit"), ("2026-03-02", 500.0, "deposit"),
                                 ("2026-07-01", -200.0, "withdrawal")],
                      {"2025-11-11": 1000.0, "2026-03-02": 1550.0, "2026-07-01": 1400.0, "2026-11-11": 1480.0})
    ctx = FakeAuditContext(transactions={P1: TX_P1, P3: TX_P1}, performance_audit={(P1, P3): agg})
    assert_status(check(D.check_perf_recompute, ctx, SCOPE_AGG), "pass")


def test_perf_recompute_fails_on_c1_twr_mixed_defect():
    # C1-TWR-MIXED: l'acquisto entra come rendimento -> il servizio dà TWR +200% sugli stessi input
    # (deposito 500, acquisto 10 × 100 a prezzo piatto) che ricalcolati danno 0%.
    export = make_export([P1], C1_FLOWS, C1_VALUES, service={"twr_pct": 200.0, "mwr_pct": 100.0})
    ctx = FakeAuditContext(transactions={P1: TX_P1}, performance_audit={(P1,): export})
    out = check(D.check_perf_recompute, ctx, SCOPE_P1)
    assert_status(out, "fail")
    twr = next(e for e in out["evidence"] if e["path"] == "service_results.twr.twr_pct")
    assert twr["observed"] == 200.0 and twr["expected"] == pytest.approx(0.0, abs=1e-6)


def test_perf_recompute_fails_when_service_flows_differ_from_export():
    # Prima di TASK-46 il servizio leggeva solo il deposito: i flussi ricostruiti non coincidono.
    export = make_export([P1], C1_FLOWS, C1_VALUES,
                         consistency={"flows_match_service": False, "count_match": False, "totals_match": False})
    ctx = FakeAuditContext(transactions={P1: TX_P1}, performance_audit={(P1,): export})
    out = check(D.check_perf_recompute, ctx, SCOPE_P1)
    assert_status(out, "fail")
    assert {e["path"] for e in out["evidence"]} == {
        "consistency_check.flows_match_service", "consistency_check.count_match", "consistency_check.totals_match"}


def test_perf_recompute_skips_without_transactions():
    ctx = FakeAuditContext(transactions={P6: []})
    assert_status(check(D.check_perf_recompute, ctx, SCOPE_P6), "skip", "no_transactions")


# --------------------------------------------------------------------------
# D-PERF-TOOL-MATCH
# --------------------------------------------------------------------------


def performance_out(twr_1y: float | None, mwr_1y: float | None) -> dict:
    periods = ("1m", "3m", "ytd", "1y")
    out: dict[str, Any] = {}
    for p in periods:
        out[f"twr_{p}"] = twr_1y if p == "1y" else 0.5
        out[f"mwr_{p}"] = mwr_1y if p == "1y" else 0.4
    out.update({
        "implicit_contributions_eur": {p: 0.0 for p in periods},
        "implicit_contributions_note": "Apporti impliciti per periodo (valuta base)",
        "twr_annualized_pct": {p: None for p in periods}, "mwr_annualized_pct": {p: None for p in periods},
        "mwr_converged": {p: True for p in periods},
        "mwr_null_reason": {p: None for p in periods}, "mwr_multiple_roots": {p: False for p in periods},
        "calculation_windows": {p: None for p in periods}, "performance_note": "twr_* e mwr_* sono rendimenti di PERIODO",
    })
    return out


EXPORT_PERF = make_export([P1], [("2025-11-11", 1000.0, "deposit"), ("2026-03-02", 500.0, "deposit")],
                          {"2025-11-11": 1000.0, "2026-03-02": 1550.0, "2026-11-11": 1700.0})


def _tool_match_ctx(perf: dict, scope_ids=(P1,)) -> FakeAuditContext:
    ids = list(scope_ids)
    tool = ("get_performance", {"portfolio_id": ids[0]}) if len(ids) == 1 else \
        ("get_aggregate_performance", {"portfolio_ids": ids})
    export = {**copy.deepcopy(EXPORT_PERF), "portfolio_ids": ids}
    return FakeAuditContext([(tool[0], tool[1], perf)], transactions={i: TX_P1 for i in ids},
                            performance_audit={tuple(ids): export})


def test_perf_tool_match_pass_portfolio_and_aggregate():
    s = EXPORT_PERF["service_results"]
    good = performance_out(round(s["twr"]["twr_pct"], 2), round(s["mwr"]["mwr_pct"], 2))
    assert_status(check(D.check_perf_tool_match, _tool_match_ctx(good), SCOPE_P1), "pass")
    agg = {"portfolio_ids": [P1, P3], "base_currency": "EUR", "aggregate_note": AGGREGATE_NOTE, **good}
    assert_status(check(D.check_perf_tool_match, _tool_match_ctx(agg, (P1, P3)), SCOPE_AGG), "pass")


def test_perf_tool_match_fails_on_different_rounding_or_annualization():
    s = EXPORT_PERF["service_results"]
    days, twr = 365.0 / 200.0, s["twr"]["twr_pct"]
    annualized = round(((1 + twr / 100) ** days - 1) * 100, 2)
    bad = performance_out(annualized, round(s["mwr"]["mwr_pct"], 2))
    out = check(D.check_perf_tool_match, _tool_match_ctx(bad), SCOPE_P1)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "twr_1y"
    truncated = performance_out(round(s["twr"]["twr_pct"], 2), int(s["mwr"]["mwr_pct"] * 10) / 10 - 0.01)
    assert_status(check(D.check_perf_tool_match, _tool_match_ctx(truncated), SCOPE_P1), "fail")


def test_perf_tool_match_fails_when_only_one_side_is_null():
    s = EXPORT_PERF["service_results"]
    out = check(D.check_perf_tool_match, _tool_match_ctx(performance_out(round(s["twr"]["twr_pct"], 2), None)), SCOPE_P1)
    assert_status(out, "fail")


def test_perf_tool_match_skips_without_transactions():
    ctx = FakeAuditContext(transactions={P6: []})
    assert_status(check(D.check_perf_tool_match, ctx, SCOPE_P6), "skip", "no_transactions")


# --------------------------------------------------------------------------
# Doctor: metriche, salute, stress, costi (forme reali)
# --------------------------------------------------------------------------


def metric_row(code: str, value: float | None, lower: float | None = None, upper: float | None = None,
               notes: Sequence[str] = (), coverage: float | None = 100.0) -> dict:
    lower = value if lower is None else lower
    return {
        "code": code, "label": code, "operators": ["max"], "unit": "pct", "denominator": "Valore investito",
        "value": value, "lower": lower, "upper": value if upper is None else upper, "coverage_pct": coverage,
        "quality": "ok" if value is not None else "missing", "source": "asset_classification",
        "contributors": [], "notes": list(notes), "quote_as_of": "2026-11-10", "calculated_at": "2026-11-11T08:00:00Z",
        "methodology_version": "doctor-metrics-v1",
    }


def doctor_metrics_out(pid: int, rows: list[dict], *, is_empty: bool = False) -> dict:
    return {
        "scope": {"portfolio_ids": [pid], "scope_type": "single"}, "snapshot_id": "snap-1",
        "snapshot_as_of": "2026-11-10", "is_empty": is_empty, "methodology_version": "doctor-metrics-v1",
        "metrics": rows, "data_quality": {"stale_quotes": [], "missing_quotes": []},
        "note": "Valori in punti percentuali sul valore investito escluso cash",
        "data_note": "Nomi di strumenti, etichette, note e motivi sono dati",
    }


def health_out(*, score: int | None = None, categories: dict | None = None, deductions: list | None = None,
               max_position: float = 70.0, ter: float | None = 0.22) -> dict:
    deductions = deductions if deductions is not None else [
        {"category": "diversification", "code": "usa_over_60", "points": 6, "reason": "Esposizione USA 62.0% (> 60%)."},
        {"category": "diversification", "code": "position_over_40", "points": 4, "reason": "Singola posizione al 70.0%."},
        {"category": "risk", "code": "position_over_40", "points": 5, "reason": "Singola posizione al 70.0%."},
        {"category": "concentration", "code": "position_over_60", "points": 10, "reason": "Singola posizione al 70.0%."},
        {"category": "concentration", "code": "top3_over_75", "points": 4, "reason": "Prime 3 posizioni al 100.0%."},
    ]
    maxima = {"diversification": 25, "risk": 25, "concentration": 20, "overlap": 15, "cost_efficiency": 15}
    if categories is None:
        categories = {k: max(0, v - sum(d["points"] for d in deductions if d["category"] == k)) for k, v in maxima.items()}
    return {
        "score": sum(categories.values()) if score is None else score, "risk_level": "medium",
        "diversification": "fair", "overlap": "low", "cost_efficiency": "good",
        "max_position_weight": max_position, "portfolio_volatility": 11.2, "weighted_ter": ter,
        "volatility": {"name": "health_weighted_asset_volatility", "value_pct": 11.2, "method": "weighted",
                       "period": "1y", "is_floored": False, "floor_pct": None},
        "category_scores": categories, "category_max_scores": maxima, "score_deductions": deductions,
        "alerts": [], "suggestions": [],
    }


def stress_out(weights: dict[str, float]) -> dict:
    shocks = {"equity": -40.0, "bond": -5.0, "gold": 5.0, "commodity": -15.0, "cash": 0.0, "unknown": -40.0}
    breakdown = [{"asset_class": c, "weight_pct": w, "shock_pct": shocks.get(c, -40.0),
                  "contribution_pct": round(w * shocks.get(c, -40.0) / 100, 2)} for c, w in weights.items()]
    return {
        "analysis_date": "2026-11-11", "portfolio_volatility_pct": 12.0, "volatility": None,
        "scenarios": [
            {"scenario_name": "Global Equity Crash", "scenario_type": "shock", "period": None,
             "estimated_portfolio_impact_pct": round(sum(r["contribution_pct"] for r in breakdown), 2),
             "risk_level": "high", "max_drawdown_pct": -20.0, "affected_classes": list(weights),
             "class_breakdown": breakdown},
            {"scenario_name": "Covid Crash", "scenario_type": "historical", "period": "2020-02-19 → 2020-03-23",
             "estimated_portfolio_impact_pct": -12.0, "risk_level": "medium", "method": "proxy",
             "coverage_pct": 0.0, "class_breakdown": [], "flags": ["class_proxy_drawdowns"]},
        ],
    }


def search_info_out(symbol: str, *, type_: str = "etf", currency: str = "EUR", match: str = "portfolio",
                    warning: str | None = None, stored_symbol: str | None = None) -> dict:
    out = {"symbol": stored_symbol or symbol.upper(), "name": f"{symbol} UCITS ETF", "match": match, "type": type_,
           "currency": currency, "isin": "IE00AUD00001", "asset_class": "equity", "instrument_type": "etf",
           "classification_source": "justetf", "classification_note": "Per allocazione e rischio usa asset_class"}
    if warning:
        out["requested_symbol"] = symbol
        out["warning"] = warning
    return out


def costs_out(weighted_ter: float | None) -> dict:
    return {"weighted_ter_pct": weighted_ter, "total_annual_cost_eur": 2.1, "estimated_annual_cost_known_eur": 2.1,
            "fee_drag_10y_eur": 20.5, "cost_perimeter": "covered_positions", "covered_market_value_eur": 850.0,
            "portfolio_market_value": 1000.0, "ter_coverage_pct": 85.0, "missing_ter_symbols": ["AUDTHM.DE"],
            "inferred_ter_symbols": [], "coverage_note": "TER disponibile per l'85.0%", "position_costs": []}


DISABLED = RuntimeError(POLICY_DISABLED_MESSAGE)


# --------------------------------------------------------------------------
# D-DOCTOR-TER
# --------------------------------------------------------------------------


def _ter_ctx(d: float | None, h: float | None, c: float | None, *, cash_type: bool = False, metrics=None):
    rows = [metric_row("weighted_ter_pct", d)]
    holdings = p1_holdings()
    return FakeAuditContext(
        [("read_doctor_metrics", {"portfolio_id": P1}, metrics if metrics is not None else doctor_metrics_out(P1, rows)),
         ("get_portfolio_health", {"portfolio_id": P1}, health_out(ter=h)),
         ("get_cost_breakdown", {"portfolio_id": P1}, costs_out(c)),
         ("get_positions", {"portfolio_id": P1}, positions_out(holdings))]
        + [("search_asset_info", {"portfolio_id": P1, "symbol": h_.symbol},
            search_info_out(h_.symbol, type_="cash" if cash_type and i == 2 else "etf"))
           for i, h_ in enumerate(holdings)]
    )


def test_doctor_ter_pass():
    assert_status(check(D.check_doctor_ter, _ter_ctx(0.22, 0.22, 0.218), SCOPE_P1), "pass")


def test_doctor_ter_fails_when_doctor_weighs_on_total_instead_of_covered():
    # V365-007: TER coperto 0,218 su 85% del valore; pesato sul totale -> 0,185.
    out = check(D.check_doctor_ter, _ter_ctx(round(0.218 * 0.85, 2), 0.22, 0.218), SCOPE_P1)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "metrics[code=weighted_ter_pct].value"


def test_doctor_ter_skips():
    assert_status(check(D.check_doctor_ter, _ter_ctx(None, 0.22, 0.218), SCOPE_P1), "skip", "no_reference_data")
    assert_status(check(D.check_doctor_ter, _ter_ctx(0.22, 0.22, 0.218, cash_type=True), SCOPE_P1),
                  "skip", "not_applicable")
    assert_status(check(D.check_doctor_ter, _ter_ctx(0.22, 0.22, 0.218, metrics=DISABLED), SCOPE_P1),
                  "skip", "feature_disabled")


def test_doctor_rules_let_unexpected_tool_errors_through():
    ctx = _ter_ctx(0.22, 0.22, 0.218, metrics=RuntimeError("Errore nell'esecuzione del tool read_doctor_metrics"))
    with pytest.raises(FakeToolError):
        D.check_doctor_ter(ctx, SCOPE_P1)


# --------------------------------------------------------------------------
# D-DOCTOR-CLASS-WEIGHTS
# --------------------------------------------------------------------------

W_P3 = {"unknown": 15.0, "equity": 25.0, "commodity": 20.0, "gold": 40.0}


def _class_ctx(equity: float, bond: float, gold: float, weights: dict | None = None, *, metrics=None,
               holdings=None) -> FakeAuditContext:
    rows = [metric_row("equity_weight_pct", equity / 0.85, lower=equity, upper=equity + 15, coverage=85.0),
            metric_row("bond_weight_pct", bond / 0.85, lower=bond, upper=bond + 15, coverage=85.0),
            metric_row("gold_weight_pct", gold / 0.85, lower=gold, upper=gold + 15, coverage=85.0)]
    return FakeAuditContext([
        ("read_doctor_metrics", {"portfolio_id": P3}, metrics if metrics is not None else doctor_metrics_out(P3, rows)),
        ("get_positions", {"portfolio_id": P3}, positions_out(p3_holdings() if holdings is None else holdings)),
        ("get_stress_test", {"portfolio_id": P3}, stress_out(weights or W_P3)),
    ])


def test_doctor_class_weights_pass_with_and_without_cash_class():
    assert_status(check(D.check_doctor_class_weights, _class_ctx(25.0, 0.0, 40.0), SCOPE_P3), "pass")
    with_cash = {"unknown": 14.25, "equity": 23.75, "commodity": 19.0, "gold": 38.0, "cash": 5.0}
    assert_status(check(D.check_doctor_class_weights, _class_ctx(25.0, 0.0, 40.0, with_cash), SCOPE_P3), "pass")
    # precious metals classificati commodity contano con l'oro nel Doctor
    assert_status(check(D.check_doctor_class_weights, _class_ctx(25.0, 0.0, 60.0), SCOPE_P3), "pass")


def test_doctor_class_weights_fails_when_etc_counted_as_equity_in_doctor():
    # V365-002: l'ETC sull'oro (40%) è azionario per il Doctor, oro per lo stress.
    out = check(D.check_doctor_class_weights, _class_ctx(65.0, 0.0, 0.0), SCOPE_P3)
    assert_status(out, "fail")
    paths = {e["path"] for e in out["evidence"]}
    assert {"metrics[code=equity_weight_pct].lower", "metrics[code=gold_weight_pct].lower"} <= paths


def test_doctor_class_weights_skips():
    assert_status(check(D.check_doctor_class_weights, _class_ctx(0, 0, 0, holdings=[]), SCOPE_P3), "skip", "empty_portfolio")
    assert_status(check(D.check_doctor_class_weights, _class_ctx(0, 0, 0, metrics=DISABLED), SCOPE_P3),
                  "skip", "feature_disabled")


# --------------------------------------------------------------------------
# D-DOCTOR-CONCENTRATION
# --------------------------------------------------------------------------


def _conc_ctx(d: float | None, h: float, *, notes=(), is_empty=False, metrics=None) -> FakeAuditContext:
    rows = [metric_row("max_single_position_pct", d, notes=notes)]
    return FakeAuditContext([
        ("read_doctor_metrics", {"portfolio_id": P1},
         metrics if metrics is not None else doctor_metrics_out(P1, rows, is_empty=is_empty)),
        ("get_portfolio_health", {"portfolio_id": P1}, health_out(max_position=h)),
    ])


def test_doctor_concentration_pass_and_same_isin_rule():
    assert_status(check(D.check_doctor_concentration, _conc_ctx(70.0, 70.0), SCOPE_P1), "pass")
    note = ["Stesso strumento (ISIN) su più listing aggregato: AUDEQ.MI/AUDEQ.DE."]
    assert_status(check(D.check_doctor_concentration, _conc_ctx(75.0, 70.0, notes=note), SCOPE_P1), "pass")
    assert_status(check(D.check_doctor_concentration, _conc_ctx(75.0, 70.0), SCOPE_P1), "fail")


def test_doctor_concentration_fails_when_computed_on_total_with_cash():
    # V365-010: la salute calcola la concentrazione sul totale con la liquidità (700 / 1094,80).
    out = check(D.check_doctor_concentration, _conc_ctx(70.0, round(700 / 1094.80 * 100, 2)), SCOPE_P1)
    assert_status(out, "fail")


def test_doctor_concentration_skips():
    assert_status(check(D.check_doctor_concentration, _conc_ctx(None, 0.0, is_empty=True), SCOPE_P1),
                  "skip", "empty_portfolio")
    assert_status(check(D.check_doctor_concentration, _conc_ctx(None, 70.0), SCOPE_P1), "skip", "no_reference_data")
    assert_status(check(D.check_doctor_concentration, _conc_ctx(70.0, 70.0, metrics=DISABLED), SCOPE_P1),
                  "skip", "feature_disabled")


# --------------------------------------------------------------------------
# D-HEALTH-SCORE-BREAKDOWN
# --------------------------------------------------------------------------


def _health_ctx(health: dict, holdings=None) -> FakeAuditContext:
    agg = merge(p1_holdings(), p3_holdings())
    return FakeAuditContext([
        ("get_positions", {"portfolio_id": P1}, positions_out(p1_holdings() if holdings is None else holdings)),
        ("get_portfolio_health", {"portfolio_id": P1}, health),
        ("get_aggregate_positions", {"portfolio_ids": [P1, P3]}, agg_positions_out(agg, [P1, P3])),
        ("get_aggregate_health", {"portfolio_ids": [P1, P3]},
         {"portfolio_ids": [P1, P3], "base_currency": "EUR", "aggregate_note": AGGREGATE_NOTE, **health_out()}),
    ])


def test_health_score_breakdown_pass():
    ctx = _health_ctx(health_out())
    assert_status(check(D.check_health_score_breakdown, ctx, SCOPE_P1), "pass")
    assert_status(check(D.check_health_score_breakdown, ctx, SCOPE_AGG), "pass")


def test_health_score_breakdown_fails_on_points_without_deduction():
    h = health_out()
    h["category_scores"]["risk"] -= 5  # punti tolti senza voce in score_deductions
    h["score"] -= 5
    out = check(D.check_health_score_breakdown, _health_ctx(h), SCOPE_P1)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "category_scores.risk"
    h = health_out(score=90)
    assert_status(check(D.check_health_score_breakdown, _health_ctx(h), SCOPE_P1), "fail")


def test_health_score_breakdown_skips_empty():
    assert_status(check(D.check_health_score_breakdown, _health_ctx(health_out(), holdings=[]), SCOPE_P1),
                  "skip", "empty_portfolio")


# --------------------------------------------------------------------------
# D-XRAY-SUMS
# --------------------------------------------------------------------------


def xray_out(geo: dict, sector: dict, statuses=(70.0, 20.0, 10.0)) -> dict:
    return {
        "etf_count": 3, "coverage_pct": 90.0, "lookthrough_coverage_pct": 70.0,
        "applicable_lookthrough_coverage_pct": 87.5, "applicable_denominator": "equity",
        "available_pct": statuses[0], "not_applicable_pct": statuses[1], "missing_pct": statuses[2],
        "funds_with_holdings_pct": 70.0, "classified_country_pct": 80.0, "classified_sector_pct": 75.0,
        "coverage_denominator": "posizioni esclusa la liquidità", "coverage_note": None, "data_as_of": "2026-11-01",
        "top_underlying_holdings": [], "geographic_exposure": geo, "sector_exposure": sector, "funds": [],
        "coverage_issues": [], "coverage_issues_total": 0,
    }


GEO = {"Stati Uniti": 43.4, "Giappone": 3.85, "Regno Unito": 2.45, "Altri": 20.3, "Non classificato": 30.0}
SECTOR = {"Tecnologia": 25.0, "Finanza": 15.0, "Non classificato": 60.0}


def _xray_ctx(xray: dict, holdings=None) -> FakeAuditContext:
    return FakeAuditContext([
        ("get_positions", {"portfolio_id": P1}, positions_out(p1_holdings() if holdings is None else holdings)),
        ("get_xray_summary", {"portfolio_id": P1}, xray),
    ])


def test_xray_sums_pass():
    assert_status(check(D.check_xray_sums, _xray_ctx(xray_out(GEO, SECTOR)), SCOPE_P1), "pass")
    assert_status(check(D.check_xray_sums, _xray_ctx(xray_out({}, {}, (None, None, None))), SCOPE_P1), "pass")


def test_xray_sums_fails_on_exposure_over_total_with_cash_or_without_unclassified():
    scaled = {k: round(v * 1000 / 1094.80, 2) for k, v in GEO.items()}
    assert_status(check(D.check_xray_sums, _xray_ctx(xray_out(scaled, SECTOR)), SCOPE_P1), "fail")
    no_unclassified = {k: v for k, v in SECTOR.items() if k != "Non classificato"}
    out = check(D.check_xray_sums, _xray_ctx(xray_out(GEO, no_unclassified)), SCOPE_P1)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "sector_exposure[*]"
    assert_status(check(D.check_xray_sums, _xray_ctx(xray_out(GEO, SECTOR, (70.0, 20.0, 0.0))), SCOPE_P1), "fail")


def test_xray_sums_skips_empty():
    assert_status(check(D.check_xray_sums, _xray_ctx(xray_out(GEO, SECTOR), holdings=[]), SCOPE_P1),
                  "skip", "empty_portfolio")


# --------------------------------------------------------------------------
# D-DUP-TRANSACTIONS
# --------------------------------------------------------------------------

P5 = 9105
SCOPE_P5 = {"kind": "portfolio", "portfolio_id": P5}


def import_file(first_id: int) -> list[dict]:
    """Un file d'import di 7 righe (acquisti, dividendi mensili su date diverse, un deposito)."""
    rows = [
        tx(first_id, "deposit", "2026-01-05", 1, 5000.0, symbol=None, asset_id=None),
        tx(first_id + 1, "buy", "2026-01-06", 20, 100.0, fees=2.95),
        tx(first_id + 2, "buy", "2026-01-06", 30, 50.0, symbol="AUDBD.MI", asset_id=9202, fees=2.95),
        tx(first_id + 3, "dividend", "2026-02-15", 1, 12.40),
        tx(first_id + 4, "dividend", "2026-03-15", 1, 12.40),
        tx(first_id + 5, "dividend", "2026-04-15", 1, 12.55),
        tx(first_id + 6, "sell", "2026-05-02", 5, 104.0, fees=2.95),
    ]
    return rows


def test_dup_transactions_pass_with_legit_split_execution():
    rows = import_file(1) + [tx(20, "buy", "2026-06-10", 10, 101.0), tx(21, "buy", "2026-06-10", 10, 101.0)]
    ctx = FakeAuditContext(transactions={P5: rows})
    assert_status(check(D.check_dup_transactions, ctx, SCOPE_P5), "pass")


def test_dup_transactions_fails_on_file_confirmed_four_times():
    # V365-009 / V-DUP-IMPORT: stesso file confermato 4 volte (4 copie di 7 righe).
    rows = import_file(1) + import_file(101) + import_file(201) + import_file(301)
    out = check(D.check_dup_transactions, FakeAuditContext(transactions={P5: rows}), SCOPE_P5)
    assert_status(out, "fail")
    paths = " ".join(e["path"] for e in out["evidence"])
    assert "[side=dividend]" in paths and "[side=buy]" in paths and "[side=deposit]" in paths
    assert all(e["observed"] == 4 for e in out["evidence"])


def test_dup_transactions_thresholds():
    two_dividends = import_file(1) + [tx(50, "dividend", "2026-02-15", 1, 12.40 + 1e-9)]
    assert_status(check(D.check_dup_transactions, FakeAuditContext(transactions={P5: two_dividends}), SCOPE_P5), "fail")
    three_buys = [tx(i, "buy", "2026-06-10", 10, 101.0) for i in range(3)]
    assert_status(check(D.check_dup_transactions, FakeAuditContext(transactions={P5: three_buys}), SCOPE_P5), "fail")
    different_fees = [tx(1, "buy", "2026-06-10", 10, 101.0), tx(2, "buy", "2026-06-10", 10, 101.0),
                      tx(3, "buy", "2026-06-10", 10, 101.0, fees=1.0)]
    assert_status(check(D.check_dup_transactions, FakeAuditContext(transactions={P5: different_fees}), SCOPE_P5), "pass")


def test_dup_transactions_skips_without_transactions():
    assert_status(check(D.check_dup_transactions, FakeAuditContext(transactions={P6: []}), SCOPE_P6),
                  "skip", "no_transactions")


# --------------------------------------------------------------------------
# D-TRADE-PRICE-SCALE
# --------------------------------------------------------------------------

P4 = 9104
SCOPE_P4 = {"kind": "portfolio", "portfolio_id": P4}


def p4_holdings(**fallback: Any) -> list:
    return weigh([holding("AUDUS.L", 10, 101.5, 98.0, asset_id=9210, **fallback),
                  holding("AUDUK.L", 20, 52.0, 51.0, asset_id=9211),
                  holding("AUDEQ.MI", 5, 100.0, 95.0, asset_id=9201)])


def p4_transactions(us_price: float = 110.0, uk_price: float = 45.0, eq_price: float = 95.0) -> list[dict]:
    return [tx(3, "buy", "2026-02-01", 10, us_price, symbol="AUDUS.L", asset_id=9210, ccy="USD"),
            tx(2, "buy", "2026-01-15", 20, uk_price, symbol="AUDUK.L", asset_id=9211, ccy="GBP"),
            tx(1, "buy", "2026-01-10", 5, eq_price),
            tx(0, "deposit", "2026-01-09", 1, 4000.0, symbol=None, asset_id=None)]


def _scale_ctx(transactions: list[dict], holdings=None) -> FakeAuditContext:
    return FakeAuditContext([("get_positions", {"portfolio_id": P4}, positions_out(holdings or p4_holdings()))],
                            transactions={P4: transactions, P6: []})


def test_trade_price_scale_pass_with_usd_and_gbp_trades():
    assert_status(check(D.check_trade_price_scale, _scale_ctx(p4_transactions()), SCOPE_P4), "pass")


def test_trade_price_scale_fails_on_xlsx_thousands_and_pence():
    # V-XLSX-1000: 105,568 letto come 105.568 (quantità ÷ 1000).
    out = check(D.check_trade_price_scale, _scale_ctx(p4_transactions(eq_price=105568.0)), SCOPE_P4)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "[id=1].price"
    # V-QUOTE-CCY-L: pence (GBp) letti come sterline: 4500 invece di 45.
    out = check(D.check_trade_price_scale, _scale_ctx(p4_transactions(uk_price=4500.0)), SCOPE_P4)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "[id=2].price"


def test_trade_price_scale_skips():
    assert_status(check(D.check_trade_price_scale, _scale_ctx([]), SCOPE_P4), "skip", "no_transactions")
    only_cash = [tx(0, "deposit", "2026-01-09", 1, 4000.0, symbol=None, asset_id=None)]
    assert_status(check(D.check_trade_price_scale, _scale_ctx(only_cash), SCOPE_P4), "skip", "no_reference_data")
    fallback = [tx(3, "buy", "2026-02-01", 10, 110.0, symbol="AUDUS.L", asset_id=9210, ccy="USD")]
    ctx = _scale_ctx(fallback, holdings=p4_holdings(price_fallback="avg_cost"))
    assert_status(check(D.check_trade_price_scale, ctx, SCOPE_P4), "skip", "no_reference_data")


# --------------------------------------------------------------------------
# D-LSE-QUOTE-CURRENCY e D-HELD-SYMBOL-MATCH
# --------------------------------------------------------------------------


def instrument(symbol: str) -> dict:
    return {"kind": "instrument", "portfolio_id": P4, "symbol": symbol}


def _info_ctx(symbol: str, info: dict) -> FakeAuditContext:
    return FakeAuditContext([("search_asset_info", {"portfolio_id": P4, "symbol": symbol}, info)])


def test_lse_quote_currency_pass_usd_and_gbp():
    assert_status(check(D.check_lse_quote_currency, _info_ctx("AUDUS.L", search_info_out("AUDUS.L", currency="USD")),
                        instrument("AUDUS.L")), "pass")
    assert_status(check(D.check_lse_quote_currency, _info_ctx("AUDUK.L", search_info_out("AUDUK.L", currency="GBP")),
                        instrument("AUDUK.L")), "pass")


def test_lse_quote_currency_fails_when_quote_currency_is_portfolio_base():
    # V-QUOTE-CCY-L: quote_currency = valuta base del portafoglio alla creazione (tutti i .L in EUR).
    out = check(D.check_lse_quote_currency, _info_ctx("SE15.L", search_info_out("SE15.L", currency="EUR")),
                instrument("SE15.L"))
    assert_status(out, "fail")
    assert out["evidence"][0]["observed"] == "EUR"


def test_lse_quote_currency_skips_non_london_without_calling_tools():
    ctx = FakeAuditContext()
    assert_status(check(D.check_lse_quote_currency, ctx, instrument("AUDEQ.MI")), "skip", "not_applicable")
    assert ctx.calls == []


def test_held_symbol_match_pass_and_fail_on_other_listing():
    assert_status(check(D.check_held_symbol_match, _info_ctx("XAD1.DE", search_info_out("XAD1.DE")),
                        instrument("XAD1.DE")), "pass")
    # V-LOOSE-SYMBOL: risoluzione per ticker base su un altro listing (silenziosa o segnalata).
    silent = search_info_out("XAD1.DE", match="exact", stored_symbol="XAD1.MI")
    out = check(D.check_held_symbol_match, _info_ctx("XAD1.DE", silent), instrument("XAD1.DE"))
    assert_status(out, "fail")
    flagged = search_info_out("XAD1.DE", match="different_listing", stored_symbol="XAD1.MI",
                              warning="Nessun asset con simbolo esatto XAD1.DE")
    out = check(D.check_held_symbol_match, _info_ctx("XAD1.DE", flagged), instrument("XAD1.DE"))
    assert_status(out, "fail")
    assert {e["path"] for e in out["evidence"]} == {"match", "warning", "symbol"}


# --------------------------------------------------------------------------
# D-FX-FLAGS-DECLARED
# --------------------------------------------------------------------------

P7 = 9107
SCOPE_P7 = {"kind": "portfolio", "portfolio_id": P7}


def p7_holdings(**stl: Any) -> list:
    return weigh([holding("AUDSTL.MI", 10, 80.0, 75.0, asset_id=9212, **stl),
                  holding("AUDNPC.MI", 5, 40.0, 40.0, asset_id=9213),
                  holding("AUDEQ.MI", 3, 100.0, 95.0, asset_id=9201)])


def _flags_ctx(holdings: list, **flags: Any) -> FakeAuditContext:
    return FakeAuditContext([
        ("get_portfolio_summary", {"portfolio_id": P7}, summary_out(summary_of(holdings, 10.0, **flags))),
        ("get_positions", {"portfolio_id": P7}, positions_out(holdings)),
    ])


def test_fx_flags_declared_pass():
    stale = p7_holdings(price_stale=True, stale_reason="no_close_in_sessions")
    out = check(D.check_fx_flags_declared, _flags_ctx(stale, stale_price_symbols=["AUDSTL.MI"]), SCOPE_P7)
    assert_status(out, "pass")
    assert_status(check(D.check_fx_flags_declared, _flags_ctx(p1_holdings()), SCOPE_P7), "pass")


def test_fx_flags_declared_fails_on_silent_avg_cost_fallback():
    fallback = p7_holdings(price_fallback="avg_cost")
    out = check(D.check_fx_flags_declared, _flags_ctx(fallback), SCOPE_P7)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "price_fallback_symbols"


def test_fx_flags_declared_fails_on_fx_missing_without_currencies():
    fx = p7_holdings(fx_missing=True, price_fallback="avg_cost")
    out = check(D.check_fx_flags_declared, _flags_ctx(fx, price_fallback_symbols=["AUDSTL.MI"]), SCOPE_P7)
    assert_status(out, "fail")
    assert any(e["path"] == "fx_missing_currencies" for e in out["evidence"])


def test_fx_flags_declared_fails_without_data_quality_note():
    stale = p7_holdings(price_stale=True)
    summary = summary_out(summary_of(stale, 10.0, stale_price_symbols=["AUDSTL.MI"]))
    summary.pop("data_quality_note")
    ctx = FakeAuditContext([("get_portfolio_summary", {"portfolio_id": P7}, summary),
                            ("get_positions", {"portfolio_id": P7}, positions_out(stale))])
    out = check(D.check_fx_flags_declared, ctx, SCOPE_P7)
    assert_status(out, "fail")
    assert out["evidence"][0]["path"] == "data_quality_note"


def test_fx_flags_declared_inclusion_when_truncated_and_skip_empty():
    many = weigh([holding(f"AUD{i:02d}.MI", 1, 10.0 + i, 10.0) for i in range(35)])
    many[34].price_stale = True  # peso più alto: compare fra le 30 righe
    off_page = "AUD00.MI"  # peso più basso: fuori dalle 30 righe, ma nel riepilogo
    out = check(D.check_fx_flags_declared, _flags_ctx(many, stale_price_symbols=["AUD34.MI", off_page]), SCOPE_P7)
    assert_status(out, "pass")
    assert_status(check(D.check_fx_flags_declared, _flags_ctx([]), SCOPE_P7), "skip", "empty_portfolio")


# --------------------------------------------------------------------------
# offline_returns e script offline (non regressione)
# --------------------------------------------------------------------------

GOLDEN_EXPORT = {
    "portfolio_ids": [1, 2], "period": "1y", "start_date": "2025-11-10", "end_date": "2026-11-10",
    "net_flows_by_date": [{"date": "2025-11-10", "amount_eur": 1000.0, "in_twr_mwr": False},
                          {"date": "2026-03-01", "amount_eur": 500.0, "in_twr_mwr": True},
                          {"date": "2026-07-01", "amount_eur": -200.0, "in_twr_mwr": True}],
    "valuation_on_flow_dates": [{"date": "2025-11-10", "value_eur": 1000.0}, {"date": "2026-03-01", "value_eur": 1550.0},
                                {"date": "2026-07-01", "value_eur": 1400.0}, {"date": "2026-11-10", "value_eur": 1480.0}],
    "service_results": {"twr": {"twr_pct": 14.5806}, "mwr": {"mwr_pct": 14.1555}},
}
# Output dello script prima dello spostamento della logica in offline_returns (TASK-77).
GOLDEN_OK = """Portafogli [1, 2]  periodo 1y  2025-11-10 -> 2026-11-10
metrica               servizio       auditor    delta pp  esito
TWR %                  14.5806       14.5806      0.0000  OK
MWR % (period)         14.1555       14.1555      0.0000  OK
XIRR annuo auditor: 0.14155502  residuo NPV: 0.000000
XIRR annuo servizio (da mwr_pct): 0.14155500  residuo NPV: 0.000024
Tolleranza 0.01 pp: OK
"""
GOLDEN_DIFF = """Portafogli [1, 2]  periodo 1y  2025-11-10 -> 2026-11-10
metrica               servizio       auditor    delta pp  esito
TWR %                 200.0000       14.5806   -185.4194  DIFF
MWR % (period)         14.1555       14.1555      0.0000  OK
XIRR annuo auditor: 0.14155502  residuo NPV: 0.000000
XIRR annuo servizio (da mwr_pct): 0.14155500  residuo NPV: 0.000024
Tolleranza 0.01 pp: DISCREPANZA
"""


def test_offline_script_output_unchanged(tmp_path):
    path = tmp_path / "export.json"
    path.write_text(json.dumps(GOLDEN_EXPORT), encoding="utf-8")
    done = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, cwd=tmp_path)
    assert (done.returncode, done.stdout) == (0, GOLDEN_OK)
    bad = copy.deepcopy(GOLDEN_EXPORT)
    bad["service_results"]["twr"]["twr_pct"] = 200.0
    done = subprocess.run([sys.executable, str(SCRIPT), "-"], input=json.dumps(bad), capture_output=True, text=True,
                          cwd=tmp_path)
    assert (done.returncode, done.stdout) == (1, GOLDEN_DIFF)
    done = subprocess.run([sys.executable, str(SCRIPT), "--json", str(path)], capture_output=True, text=True,
                          cwd=tmp_path)
    assert done.returncode == 0 and json.loads(done.stdout)["ok"] is True


def test_offline_returns_matches_script_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("twr_mwr_offline_auditor_t77", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert json.dumps(script.audit(GOLDEN_EXPORT), default=str) == json.dumps(offline_returns.audit(GOLDEN_EXPORT),
                                                                              default=str)
    assert script.DEFAULT_TOLERANCE_PP == offline_returns.DEFAULT_TOLERANCE_PP == D.T_RET
