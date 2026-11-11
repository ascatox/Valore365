"""TASK-75: regole dell'Auditor del gruppo B (ribilanciamento, PAC, simulazioni).

Per ogni regola: ``pass`` sugli output reali dei tool (handler di
``copilot_tools`` su un repository finto, ``sanitize_output`` come il server
MCP), ``fail`` quando si reintroduce il difetto del finding (output sbagliato
riprodotto o monkeypatch del codice), ``skip`` con il codice giusto quando i
dati non bastano. Contesto finto copiato da ``docs/auditor/architecture.md``
§10 (nessun modulo di test condiviso).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from unittest.mock import MagicMock

import jsonschema
import pytest

import app.copilot_tools as copilot_tools
from app.mcp_server.tools import sanitize_output
from app.models import AllocationItem, PortfolioSummary, PortfolioTargetAllocationItem, Position
from app.services.auditor.rules import rebalance_simulation as rs

# ---------------------------------------------------------------------------
# Contesto finto di riferimento (architecture.md §10, copiato)
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
# Output reali dei tool su un repository finto (niente DB)
# ---------------------------------------------------------------------------

PID = 9101
SCOPE = {"kind": "portfolio", "portfolio_id": PID}
R_ARGS = {"portfolio_id": PID, "mode": "rebalance"}
BO_ARGS = {"portfolio_id": PID, "mode": "buy_only", "available_cash": 1000.0}
SO_ARGS = {"portfolio_id": PID, "mode": "sell_only"}
PAC_ARGS = {"portfolio_id": PID, "monthly_amount": 500.0}
POS_ARGS = {"portfolio_id": PID}

# Come il portafoglio 9101 del seed (rules.md §1): 70/20/10 con target 50/40/10.
BALANCED = {"AUDEQ.MI": 7000.0, "AUDBD.MI": 2000.0, "AUDTECH.DE": 1000.0}
BALANCED_TARGETS = {"AUDEQ.MI": 50.0, "AUDBD.MI": 40.0, "AUDTECH.DE": 10.0}
BALANCED_CASH = 300.0

_SCHEMA_PATH = Path(__file__).resolve().parents[4] / "docs" / "auditor" / "schemas" / "report.schema.json"


def make_repo(values: dict[str, float], targets: dict[str, float], cash: float) -> MagicMock:
    ids = {s: i for i, s in enumerate(sorted(set(values) | set(targets)), start=9101)}
    invested = sum(values.values())
    positions = [
        Position(
            asset_id=ids[s], symbol=s, name=s, quantity=v / 50.0, avg_cost=50.0, market_price=50.0,
            market_value=v, unrealized_pl=0.0, unrealized_pl_pct=0.0,
            weight=round(v / invested * 100.0, 2) if invested else 0.0,
        )
        for s, v in values.items()
    ]
    repo = MagicMock()
    repo.get_positions.return_value = positions
    repo.get_summary.return_value = PortfolioSummary(
        portfolio_id=PID, base_currency="EUR", market_value=invested, cost_basis=invested,
        unrealized_pl=0.0, unrealized_pl_pct=0.0, cash_balance=cash,
    )
    repo.get_allocation.return_value = [
        AllocationItem(asset_id=ids[s], symbol=s, market_value=v, weight_pct=round(v / invested * 100.0, 2))
        for s, v in values.items()
    ]
    repo.list_portfolio_target_allocations.return_value = [
        PortfolioTargetAllocationItem(asset_id=ids[s], symbol=s, name=s, weight_pct=w) for s, w in targets.items()
    ]
    return repo


def run_tool(repo: MagicMock, tool: str, args: dict[str, Any]) -> dict[str, Any] | Exception:
    """Come run_tool_sync + sanitize_output: un dict con sola chiave error diventa errore del tool."""
    tool_args = {k: v for k, v in args.items() if k != "portfolio_id"}
    result = copilot_tools.execute_tool(tool, tool_args, repo, MagicMock(), args["portfolio_id"], "test-user")
    if isinstance(result, dict) and set(result) == {"error"}:
        return RuntimeError(str(result["error"]))
    return sanitize_output(result)


def real_responses(values=BALANCED, targets=BALANCED_TARGETS, cash=BALANCED_CASH) -> dict[str, Any]:
    repo = make_repo(values, targets, cash)
    out: dict[str, Any] = {}

    def add(tool: str, args: dict[str, Any]) -> None:
        out[canonical_key(tool, args)] = (tool, args, run_tool(repo, tool, args))

    for tool in ("get_positions", "get_portfolio_summary", "get_target_drift"):
        add(tool, POS_ARGS)
    for args in (R_ARGS, BO_ARGS, SO_ARGS):
        add("calculate_rebalance_orders", args)
    add("calculate_pac_contribution", PAC_ARGS)
    positions = out[canonical_key("get_positions", POS_ARGS)][2]["positions"]
    if positions:
        s, v = positions[0]["symbol"], positions[0]["market_value"]
        for action, amount in (("buy", 1000.0), ("sell", round(v / 2, 2)), ("sell", round(v + 1000.0, 2))):
            add("calculate_what_if", {"portfolio_id": PID, "action": action, "symbol": s, "amount_eur": amount})
    return out


def make_ctx(responses: dict[str, Any]) -> FakeAuditContext:
    return FakeAuditContext([v for v in responses.values()])


def get(responses: dict[str, Any], tool: str, args: dict[str, Any]) -> Any:
    return copy.deepcopy(responses[canonical_key(tool, args)][2])


def put(responses: dict[str, Any], tool: str, args: dict[str, Any], value: Any) -> None:
    responses[canonical_key(tool, args)] = (tool, args, value)


def what_if_args(responses, action: str, amount: float) -> dict[str, Any]:
    s = get(responses, "get_positions", POS_ARGS)["positions"][0]["symbol"]
    return {"portfolio_id": PID, "action": action, "symbol": s, "amount_eur": amount}


_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_OUTCOME_VALIDATOR = jsonschema.Draft202012Validator(
    {"$schema": _SCHEMA.get("$schema"), "$defs": _SCHEMA["$defs"], "$ref": "#/$defs/Outcome"}
)

ALLOWED_CALLS = {
    canonical_key(t, a) for t, a in [
        ("get_positions", POS_ARGS), ("get_portfolio_summary", POS_ARGS), ("get_target_drift", POS_ARGS),
        ("calculate_rebalance_orders", R_ARGS), ("calculate_rebalance_orders", BO_ARGS),
        ("calculate_rebalance_orders", SO_ARGS), ("calculate_pac_contribution", PAC_ARGS),
    ]
}


def evaluate(check, responses) -> dict[str, Any]:
    ctx = make_ctx(responses)
    outcome = check(ctx, dict(SCOPE))
    _OUTCOME_VALIDATOR.validate(outcome)
    json.dumps(outcome)
    # Argomenti canonici (architettura §5.2): nessun'altra combinazione.
    positions = get(responses, "get_positions", POS_ARGS)["positions"]
    allowed = set(ALLOWED_CALLS)
    if positions:
        s, v = positions[0]["symbol"], positions[0]["market_value"]
        for action, amount in (("buy", 1000.0), ("sell", round(v / 2, 2)), ("sell", round(v + 1000.0, 2))):
            allowed.add(canonical_key("calculate_what_if",
                                      {"portfolio_id": PID, "action": action, "symbol": s, "amount_eur": amount}))
    for tool, args in ctx.calls:
        assert canonical_key(tool, args) in allowed, (tool, args)
    return outcome


def assert_status(outcome, status: str, code: str | None = None) -> None:
    assert outcome["status"] == status, outcome
    if code is not None:
        assert outcome["reason_code"] == code, outcome


ALL_CHECKS = [r["check"] for r in rs.RULES]
REBALANCE_CHECKS = [
    rs.check_reb_cash_conservation, rs.check_reb_cash_nonneg, rs.check_reb_sells_reach_target,
    rs.check_reb_drift_nonincreasing, rs.check_reb_mode_sides, rs.check_reb_sell_cap,
]
PAC_CHECKS = [rs.check_pac_sum, rs.check_pac_underweight_only]


# ---------------------------------------------------------------------------
# Dichiarazioni
# ---------------------------------------------------------------------------

CATALOG = {
    "B-REB-CASH-CONSERVATION": ("P0", "rebalance", ["V365-003"]),
    "B-REB-CASH-NONNEG": ("P0", "rebalance", ["V365-003"]),
    "B-REB-SELLS-REACH-TARGET": ("P1", "rebalance", ["V365-003"]),
    "B-REB-DRIFT-NONINCREASING": ("P1", "rebalance", ["V365-003"]),
    "B-REB-MODE-SIDES": ("P1", "rebalance", ["V365-003"]),
    "B-REB-SELL-CAP": ("P1", "rebalance", ["V365-003"]),
    "B-PAC-SUM": ("P1", "rebalance", []),
    "B-PAC-UNDERWEIGHT-ONLY": ("P2", "rebalance", []),
    "B-WHATIF-BUY-WEIGHT": ("P2", "simulation", []),
    "B-WHATIF-SELL-BOUND": ("P2", "simulation", []),
}


def test_declarations_match_catalog():
    import re

    assert [r["id"] for r in rs.RULES] == list(CATALOG)
    for r in rs.RULES:
        sev, area, findings = CATALOG[r["id"]]
        assert re.match(r"^[ABCD]-[A-Z0-9]+(?:-[A-Z0-9]+)*$", r["id"])
        assert r["group"] == "B" and r["id"].startswith("B-")
        assert (r["severity"], r["area"], r["findings"]) == (sev, area, findings)
        assert r["scopes"] == ["portfolio"]
        assert r["title"] and r["id"] not in r["title"]
        assert callable(r["check"]) and r["tools"]
        # Difetti noti (rules.md §6, TASK-79): solo B-PAC-SUM, task TASK-83.
        assert r.get("known_defect") == {"B-PAC-SUM": "TASK-83"}.get(r["id"])


def test_rules_module_imports_only_stdlib():
    source = Path(rs.__file__).read_text(encoding="utf-8")
    imports = [line.strip() for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert imports == ["from __future__ import annotations", "import math", "from typing import Any, Mapping"]


# ---------------------------------------------------------------------------
# Pass sugli output reali e skip comuni
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("check", ALL_CHECKS, ids=[r["id"] for r in rs.RULES])
def test_pass_on_real_tool_outputs(check):
    outcome = evaluate(check, real_responses())
    assert_status(outcome, "pass")
    assert outcome["evidence"]


@pytest.mark.parametrize("check", ALL_CHECKS, ids=[r["id"] for r in rs.RULES])
def test_skip_empty_portfolio(check):
    responses = real_responses(values={}, targets=BALANCED_TARGETS, cash=0.0)
    assert get(responses, "get_positions", POS_ARGS)["positions"] == []
    assert_status(evaluate(check, responses), "skip", "empty_portfolio")


@pytest.mark.parametrize("check", REBALANCE_CHECKS + PAC_CHECKS)
def test_skip_no_targets(check):
    responses = real_responses(targets={})
    assert "totals" not in get(responses, "calculate_rebalance_orders", R_ARGS)
    assert "total_allocated" not in get(responses, "calculate_pac_contribution", PAC_ARGS)
    assert_status(evaluate(check, responses), "skip", "no_targets")


def test_whatif_rules_do_not_need_targets():
    responses = real_responses(targets={})
    assert_status(evaluate(rs.check_whatif_buy_weight, responses), "pass")
    assert_status(evaluate(rs.check_whatif_sell_bound, responses), "pass")


@pytest.mark.parametrize("check", [rs.check_reb_sells_reach_target, rs.check_reb_drift_nonincreasing,
                                   rs.check_reb_sell_cap])
def test_skip_not_applicable_within_band(check):
    # Pesi già sui target e portafoglio grande: anche i 1000 € del buy_only restano
    # entro la banda di 0,5 pp, quindi nessun ordine in nessuna modalità (output reali).
    responses = real_responses(values={"A": 500000.0, "B": 500000.0}, targets={"A": 50.0, "B": 50.0}, cash=0.0)
    for args in (R_ARGS, BO_ARGS, SO_ARGS):
        assert get(responses, "calculate_rebalance_orders", args)["orders"] == []
    assert_status(evaluate(check, responses), "skip", "not_applicable")


def test_partial_totals_is_a_fail_not_a_skip():
    responses = real_responses()
    so = get(responses, "calculate_rebalance_orders", SO_ARGS)
    put(responses, "calculate_rebalance_orders", SO_ARGS, {"mode": "sell_only", "orders": [], "note": "x"})
    assert so["totals"]
    assert_status(evaluate(rs.check_reb_cash_conservation, responses), "fail", "invariant_violated")


def test_tool_error_propagates():
    responses = real_responses()
    put(responses, "calculate_rebalance_orders", R_ARGS, RuntimeError("boom"))
    with pytest.raises(FakeToolError):
        rs.check_reb_cash_conservation(make_ctx(responses), dict(SCOPE))


# ---------------------------------------------------------------------------
# Difetto V365-003: output di novembre (sola vendita, proventi spariti)
# ---------------------------------------------------------------------------

def _november_plan(mode: str, extra: float) -> dict[str, Any]:
    """Output di novembre: solo `sell VTI 815,07 €`, nessun acquisto, `cash_after` 0."""
    return {
        "mode": mode,
        "orders": [{
            "side": "sell", "symbol": "VTI", "amount_eur": 815.07, "shares_approx": 2.6,
            "current_weight_pct": 61.22, "target_weight_pct": 60.0, "weight_after_pct": 61.22 - 8.15,
        }],
        "totals": {
            "sells_eur": 815.07, "buys_eur": 0.0, "cash_before": 0.0, "extra_cash": extra,
            "cash_after": 0.0, "invariant": "cash_after = cash_before + extra_cash + sells_eur - buys_eur",
            "invariant_ok": True,
        },
        "total_value": 10000.0, "tolerance_pp": 0.5, "untargeted_holdings": [], "untargeted_value": 0.0,
        "target_sum_pct": 100.0, "unallocated_target_pct": 0.0, "notes": [],
    }


def _november_responses() -> dict[str, Any]:
    responses = real_responses(values={"VTI": 6122.0, "VEUR": 2463.0, "VFEM": 1415.0},
                               targets={"VTI": 60.0, "VEUR": 25.0, "VFEM": 15.0}, cash=0.0)
    put(responses, "calculate_rebalance_orders", R_ARGS, _november_plan("rebalance", 0.0))
    put(responses, "calculate_rebalance_orders", BO_ARGS, _november_plan("buy_only", 1000.0))
    put(responses, "calculate_rebalance_orders", SO_ARGS, _november_plan("sell_only", 0.0))
    return responses


def test_cash_conservation_real_audit_case_passes():
    responses = real_responses(values={"VTI": 6122.0, "VEUR": 2463.0, "VFEM": 1415.0},
                               targets={"VTI": 60.0, "VEUR": 25.0, "VFEM": 15.0}, cash=0.0)
    assert_status(evaluate(rs.check_reb_cash_conservation, responses), "pass")


def test_cash_conservation_fails_on_november_output():
    outcome = evaluate(rs.check_reb_cash_conservation, _november_responses())
    assert_status(outcome, "fail", "invariant_violated")
    ev = next(e for e in outcome["evidence"] if e["path"] == "totals.cash_after")
    assert ev["observed"] == 0.0 and ev["expected"] == 815.07


def test_cash_conservation_fails_on_monkeypatched_legacy_plan(monkeypatch):
    """Monkeypatch del codice: il vecchio piano (sola vendita, proventi persi) dietro il tool reale."""
    real_plan = copilot_tools.compute_rebalance_plan

    def legacy_plan(holdings, **kwargs):
        plan = real_plan(holdings, **kwargs)
        sells = [o for o in plan.orders if o.side == "sell"]
        return type(plan)(
            mode=plan.mode, orders=sells, weights=plan.weights, base_value=plan.base_value,
            portfolio_cash=plan.portfolio_cash, extra_cash=plan.extra_cash,
            sells_total=sum(o.amount for o in sells), buys_total=0.0, cash_after=0.0,
            target_sum_pct=plan.target_sum_pct,
        )

    monkeypatch.setattr(copilot_tools, "compute_rebalance_plan", legacy_plan)
    outcome = evaluate(rs.check_reb_cash_conservation, real_responses())
    assert_status(outcome, "fail", "invariant_violated")
    assert any(e["path"] == "totals.invariant_ok" and e["observed"] is False for e in outcome["evidence"])


def test_cash_conservation_fails_when_buy_only_ignores_available_cash():
    responses = real_responses()
    bo = get(responses, "calculate_rebalance_orders", BO_ARGS)
    bo["totals"]["extra_cash"] = 0.0
    bo["totals"]["cash_after"] = round(bo["totals"]["cash_after"] - 1000.0, 2)
    put(responses, "calculate_rebalance_orders", BO_ARGS, bo)
    outcome = evaluate(rs.check_reb_cash_conservation, responses)
    assert_status(outcome, "fail")
    assert any(e["path"] == "totals.extra_cash" for e in outcome["evidence"])


def test_cash_conservation_fails_when_totals_disagree_with_orders():
    responses = real_responses()
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    r["totals"]["buys_eur"] = round(r["totals"]["buys_eur"] - 100.0, 2)
    r["totals"]["cash_after"] = round(r["totals"]["cash_after"] + 100.0, 2)
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    outcome = evaluate(rs.check_reb_cash_conservation, responses)
    assert_status(outcome, "fail")
    assert any(e["path"] == "totals.buys_eur" for e in outcome["evidence"])


# ---------------------------------------------------------------------------
# B-REB-CASH-NONNEG: liquidità contata due volte
# ---------------------------------------------------------------------------

def test_cash_nonneg_fails_when_cash_is_counted_twice():
    responses = real_responses()
    for args in (R_ARGS, BO_ARGS):
        plan = get(responses, "calculate_rebalance_orders", args)
        cash = plan["totals"]["cash_before"] + plan["totals"]["extra_cash"]
        buy = next(o for o in plan["orders"] if o["side"] == "buy")
        buy["amount_eur"] = round(buy["amount_eur"] + cash, 2)       # cash_used = liquidità + liquidità
        plan["totals"]["buys_eur"] = round(plan["totals"]["buys_eur"] + cash, 2)
        plan["totals"]["cash_after"] = round(plan["totals"]["cash_after"] - cash, 2)
        put(responses, "calculate_rebalance_orders", args, plan)
    outcome = evaluate(rs.check_reb_cash_nonneg, responses)
    assert_status(outcome, "fail", "invariant_violated")
    paths = {e["path"] for e in outcome["evidence"]}
    assert {"totals.cash_after", "totals.buys_eur"} <= paths
    assert min(e["observed"] for e in outcome["evidence"] if e["path"] == "totals.cash_after") < 0


# ---------------------------------------------------------------------------
# B-REB-SELLS-REACH-TARGET: vendita = scostamento % × valore della posizione
# ---------------------------------------------------------------------------

def _legacy_drift_sale(mode: str) -> dict[str, Any]:
    base = sum(BALANCED.values()) + BALANCED_CASH
    value = BALANCED["AUDEQ.MI"]
    cw = value / base * 100
    amount = round((cw - 50.0) / 100 * value, 2)
    return {
        "mode": mode,
        "orders": [{
            "side": "sell", "symbol": "AUDEQ.MI", "amount_eur": amount, "shares_approx": round(amount / 50, 4),
            "current_weight_pct": round(cw, 2), "target_weight_pct": 50.0,
            "weight_after_pct": round((value - amount) / base * 100, 2),
        }],
        "totals": {"sells_eur": amount, "buys_eur": 0.0, "cash_before": BALANCED_CASH, "extra_cash": 0.0,
                   "cash_after": round(BALANCED_CASH + amount, 2), "invariant": "…", "invariant_ok": True},
    }


def test_sells_reach_target_fails_on_drift_times_value_sale():
    responses = real_responses()
    put(responses, "calculate_rebalance_orders", R_ARGS, _legacy_drift_sale("rebalance"))
    put(responses, "calculate_rebalance_orders", SO_ARGS, _legacy_drift_sale("sell_only"))
    outcome = evaluate(rs.check_reb_sells_reach_target, responses)
    assert_status(outcome, "fail", "invariant_violated")
    ev = outcome["evidence"][0]
    assert ev["path"] == "orders[0].weight_after_pct" and ev["expected"] == 50.0 and ev["observed"] > 55


def test_sells_reach_target_reduced_buys_require_no_idle_cash():
    responses = real_responses()
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    buy = next(o for o in r["orders"] if o["side"] == "buy" and o["target_weight_pct"] == 40.0)
    buy["weight_after_pct"] = 35.0          # acquisto ridotto…
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    assert_status(evaluate(rs.check_reb_sells_reach_target, responses), "pass")   # …con cash_after 0
    r["totals"]["cash_after"] = 500.0       # …mentre la liquidità resta ferma
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    outcome = evaluate(rs.check_reb_sells_reach_target, responses)
    assert_status(outcome, "fail")
    assert outcome["evidence"][-1]["path"] == "totals.cash_after"


def test_sells_reach_target_buy_over_target_fails():
    responses = real_responses()
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    buy = next(o for o in r["orders"] if o["side"] == "buy")
    buy["weight_after_pct"] = round(buy["target_weight_pct"] + 3.0, 2)
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    assert_status(evaluate(rs.check_reb_sells_reach_target, responses), "fail")


# ---------------------------------------------------------------------------
# B-REB-DRIFT-NONINCREASING: segno dell'ordine invertito
# ---------------------------------------------------------------------------

def test_drift_nonincreasing_fails_on_buy_of_overweight_holding():
    responses = real_responses()
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    sell = next(o for o in r["orders"] if o["side"] == "sell")
    sell["side"] = "buy"                                   # segno invertito
    sell["weight_after_pct"] = round(sell["current_weight_pct"] + 5.0, 2)
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    outcome = evaluate(rs.check_reb_drift_nonincreasing, responses)
    assert_status(outcome, "fail", "invariant_violated")
    assert outcome["evidence"][0]["note"].startswith("modalità rebalance, buy AUDEQ.MI")


# ---------------------------------------------------------------------------
# B-REB-MODE-SIDES: modalità ignorata
# ---------------------------------------------------------------------------

def test_mode_sides_fails_when_buy_only_returns_rebalance_orders():
    responses = real_responses()
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    assert any(o["side"] == "sell" for o in r["orders"])
    put(responses, "calculate_rebalance_orders", BO_ARGS, {**r, "mode": "buy_only"})
    outcome = evaluate(rs.check_reb_mode_sides, responses)
    assert_status(outcome, "fail", "invariant_violated")
    assert {e["path"] for e in outcome["evidence"]} >= {"orders[0].side", "totals.sells_eur"}


def test_mode_sides_fails_when_sell_only_buys():
    responses = real_responses()
    put(responses, "calculate_rebalance_orders", SO_ARGS,
        {**get(responses, "calculate_rebalance_orders", R_ARGS), "mode": "sell_only"})
    assert_status(evaluate(rs.check_reb_mode_sides, responses), "fail")


# ---------------------------------------------------------------------------
# B-REB-SELL-CAP: vendita sul totale del portafoglio
# ---------------------------------------------------------------------------

def test_sell_cap_fails_when_sale_is_sized_on_portfolio_total():
    responses = real_responses()
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    sell = next(o for o in r["orders"] if o["side"] == "sell")
    sell["amount_eur"] = r["total_value"]                 # totale del portafoglio, non la posizione
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    outcome = evaluate(rs.check_reb_sell_cap, responses)
    assert_status(outcome, "fail", "invariant_violated")
    assert outcome["evidence"][0]["observed"] == 10300.0 and outcome["evidence"][0]["expected"] == 7000.0


def test_sell_cap_fails_on_sale_of_unheld_symbol():
    responses = real_responses()
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    next(o for o in r["orders"] if o["side"] == "sell")["symbol"] = "NONHELD"
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    assert_status(evaluate(rs.check_reb_sell_cap, responses), "fail")


def test_sell_cap_truncated_output():
    values = {f"S{i:02d}": 100.0 for i in range(31)}
    values["S00"] = 5000.0
    responses = real_responses(values=values, targets={s: 100 / 31 for s in values}, cash=0.0)
    positions = get(responses, "get_positions", POS_ARGS)
    assert len(positions["positions"]) == 30
    sold = {o["symbol"] for o in get(responses, "calculate_rebalance_orders", R_ARGS)["orders"]
            if o["side"] == "sell"}
    assert sold == {"S00"}
    # La vendita verificabile passa; una vendita su un simbolo oltre le 30 righe non è verificabile.
    assert_status(evaluate(rs.check_reb_sell_cap, responses), "pass")
    r = get(responses, "calculate_rebalance_orders", R_ARGS)
    hidden = sorted(set(values) - {p["symbol"] for p in positions["positions"]})[0]
    r["orders"][0]["symbol"] = hidden
    put(responses, "calculate_rebalance_orders", R_ARGS, r)
    put(responses, "calculate_rebalance_orders", SO_ARGS, r)
    assert_status(evaluate(rs.check_reb_sell_cap, responses), "skip", "truncated_output")


def test_sell_cap_not_applicable_without_sells():
    responses = real_responses()
    for args in (R_ARGS, SO_ARGS):
        plan = get(responses, "calculate_rebalance_orders", args)
        plan["orders"] = [o for o in plan["orders"] if o["side"] != "sell"]
        put(responses, "calculate_rebalance_orders", args, plan)
    assert_status(evaluate(rs.check_reb_sell_cap, responses), "skip", "not_applicable")


# ---------------------------------------------------------------------------
# B-PAC-SUM
# ---------------------------------------------------------------------------

def test_pac_sum_fails_on_empty_distribution_with_full_total():
    responses = real_responses()
    pac = get(responses, "calculate_pac_contribution", PAC_ARGS)
    pac["distribution"] = []
    pac["total_allocated"] = 500.0
    put(responses, "calculate_pac_contribution", PAC_ARGS, pac)
    outcome = evaluate(rs.check_pac_sum, responses)
    assert_status(outcome, "fail", "invariant_violated")
    ev = next(e for e in outcome["evidence"] if e["path"] == "distribution[*].amount_eur")
    assert ev["observed"] == 0 and ev["expected"] == 500.0


def test_pac_sum_fails_when_total_differs_from_amount():
    responses = real_responses()
    pac = get(responses, "calculate_pac_contribution", PAC_ARGS)
    pac["distribution"][0]["amount_eur"] = round(pac["distribution"][0]["amount_eur"] - 50, 2)
    pac["total_allocated"] = 450.0
    put(responses, "calculate_pac_contribution", PAC_ARGS, pac)
    outcome = evaluate(rs.check_pac_sum, responses)
    assert_status(outcome, "fail")
    assert outcome["evidence"][0]["path"] == "total_allocated"


@pytest.mark.parametrize("targets", [
    {"AUDEQ.MI": 45.0, "AUDBD.MI": 45.0},          # target che sommano a 90: tutti sopra il target
    {"AUDEQ.MI": 50.0, "AUDBD.MI": 50.0},          # tutti esattamente a target
], ids=["targets-sum-90", "all-at-target"])
def test_pac_sum_on_real_service_with_no_underweight_holding(targets):
    """TASK-75: verifica del difetto probabile segnalato da TASK-72 sulla funzione reale.

    Con nessuno strumento sottopesato `_calculate_pac_contribution` restituisce una
    distribuzione vuota ma `total_allocated` = importo: B-PAC-SUM deve fallire.
    """
    repo = make_repo({"AUDEQ.MI": 5000.0, "AUDBD.MI": 5000.0}, targets, 0.0)
    raw = copilot_tools._calculate_pac_contribution({"monthly_amount": 500.0}, repo, MagicMock(), PID, "u")
    assert raw["distribution"] == []                  # difetto reale confermato
    assert raw["total_allocated"] == 500.0
    responses = real_responses(values={"AUDEQ.MI": 5000.0, "AUDBD.MI": 5000.0}, targets=targets, cash=0.0)
    assert get(responses, "calculate_pac_contribution", PAC_ARGS) == sanitize_output(raw)
    outcome = evaluate(rs.check_pac_sum, responses)
    assert_status(outcome, "fail", "invariant_violated")
    ev = next(e for e in outcome["evidence"] if e["path"] == "distribution[*].amount_eur")
    assert (ev["observed"], ev["expected"]) == (0, 500.0)
    # La regola gemella non giudica una distribuzione vuota.
    assert_status(evaluate(rs.check_pac_underweight_only, responses), "skip", "not_applicable")


def test_pac_sum_passes_on_real_service_with_many_rows():
    values = {f"E{i}": 1000.0 + 37.0 * i for i in range(7)}
    targets = {s: 100 / 7 for s in values}
    responses = real_responses(values=values, targets=targets, cash=0.0)
    pac = get(responses, "calculate_pac_contribution", PAC_ARGS)
    assert len(pac["distribution"]) >= 3
    assert_status(evaluate(rs.check_pac_sum, responses), "pass")
    assert_status(evaluate(rs.check_pac_underweight_only, responses), "pass")


# ---------------------------------------------------------------------------
# B-PAC-UNDERWEIGHT-ONLY
# ---------------------------------------------------------------------------

def test_pac_underweight_fails_on_payment_to_overweight_holding():
    responses = real_responses()
    pac = get(responses, "calculate_pac_contribution", PAC_ARGS)
    drift = {d["symbol"]: d for d in get(responses, "get_target_drift", POS_ARGS)["drift"]}
    eq = drift["AUDEQ.MI"]
    pac["distribution"].append({
        "symbol": "AUDEQ.MI", "amount_eur": 100.0, "shares_approx": 2.0,
        "current_weight": eq["current_weight"], "target_weight": eq["target_weight"], "new_weight_after": 70.0,
    })
    put(responses, "calculate_pac_contribution", PAC_ARGS, pac)
    outcome = evaluate(rs.check_pac_underweight_only, responses)
    assert_status(outcome, "fail", "invariant_violated")
    ev = outcome["evidence"][0]
    assert ev["path"].endswith(".current_weight") and ev["observed"] == 70.0 and ev["expected"] == 50.0


def test_pac_underweight_fails_on_untargeted_symbol_or_negative_amount():
    responses = real_responses()
    pac = get(responses, "calculate_pac_contribution", PAC_ARGS)
    pac["distribution"][0]["symbol"] = "NOTARGET"
    pac["distribution"][0]["amount_eur"] = -5.0
    put(responses, "calculate_pac_contribution", PAC_ARGS, pac)
    outcome = evaluate(rs.check_pac_underweight_only, responses)
    assert_status(outcome, "fail")
    tools = {(e["tool"], e["path"]) for e in outcome["evidence"]}
    assert ("get_target_drift", "drift[symbol=NOTARGET]") in tools
    assert ("calculate_pac_contribution", "distribution[0].amount_eur") in tools


# ---------------------------------------------------------------------------
# B-WHATIF-BUY-WEIGHT
# ---------------------------------------------------------------------------

def test_whatif_buy_fails_when_new_weight_uses_total_before_purchase():
    responses = real_responses()
    args = what_if_args(responses, "buy", 1000.0)
    res = get(responses, "calculate_what_if", args)
    mv = get(responses, "get_portfolio_summary", POS_ARGS)["market_value"]
    res["new_weight"] = round((7000.0 + 1000.0) / mv * 100, 2)        # totale prima dell'acquisto
    res["max_position_weight_after"] = res["new_weight"]
    put(responses, "calculate_what_if", args, res)
    outcome = evaluate(rs.check_whatif_buy_weight, responses)
    assert_status(outcome, "fail", "invariant_violated")
    ev = next(e for e in outcome["evidence"] if e["path"] == "new_weight")
    assert ev["observed"] == 80.0 and ev["expected"] == pytest.approx(72.7273, abs=1e-4)


def test_whatif_buy_fails_on_old_weight_or_max_weight():
    responses = real_responses()
    args = what_if_args(responses, "buy", 1000.0)
    res = get(responses, "calculate_what_if", args)
    res["old_weight"] = 68.0
    res["max_position_weight_after"] = 20.0
    put(responses, "calculate_what_if", args, res)
    outcome = evaluate(rs.check_whatif_buy_weight, responses)
    assert_status(outcome, "fail")
    assert {"old_weight", "max_position_weight_after"} <= {e["path"] for e in outcome["evidence"]}


# ---------------------------------------------------------------------------
# B-WHATIF-SELL-BOUND
# ---------------------------------------------------------------------------

def test_whatif_sell_fails_when_oversell_is_accepted_with_negative_weight():
    responses = real_responses()
    args = what_if_args(responses, "sell", round(7000.0 + 1000.0, 2))
    assert isinstance(responses[canonical_key("calculate_what_if", args)][2], Exception)
    put(responses, "calculate_what_if", args, {
        "symbol": "AUDEQ.MI", "action": "sell", "amount_eur": 8000.0, "old_weight": 70.0,
        "new_weight": round(-1000.0 / 2000.0 * 100, 2), "old_drift": 20.0, "new_drift": -100.0,
        "max_position_weight_before": 70.0, "max_position_weight_after": 50.0,
        "impact_on_concentration": "migliora",
    })
    outcome = evaluate(rs.check_whatif_sell_bound, responses)
    assert_status(outcome, "fail", "invariant_violated")
    assert [e["path"] for e in outcome["evidence"]] == ["ok", "new_weight"]
    assert outcome["evidence"][1]["observed"] == -50.0


def test_whatif_sell_fails_on_wrong_new_weight():
    responses = real_responses()
    args = what_if_args(responses, "sell", 3500.0)
    res = get(responses, "calculate_what_if", args)
    res["new_weight"] = round((7000.0 - 3500.0) / 10000.0 * 100, 2)   # totale prima della vendita
    put(responses, "calculate_what_if", args, res)
    outcome = evaluate(rs.check_whatif_sell_bound, responses)
    assert_status(outcome, "fail")
    assert outcome["evidence"][0]["path"] == "new_weight"


def test_whatif_sell_not_applicable_for_tiny_position():
    responses = real_responses(values={"TINY": 0.01}, targets={}, cash=0.0)
    assert_status(evaluate(rs.check_whatif_sell_bound, responses), "skip", "not_applicable")


def test_whatif_real_tool_rejects_oversell():
    responses = real_responses()
    outcome = evaluate(rs.check_whatif_sell_bound, responses)
    assert_status(outcome, "pass")
    ok_ev = next(e for e in outcome["evidence"] if e["path"] == "ok")
    assert ok_ev["observed"] is False and "superiore al valore della posizione" in ok_ev["note"]
