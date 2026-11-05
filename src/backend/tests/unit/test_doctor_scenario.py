"""Scenario Lab (app/services/doctor_policy/scenario.py): golden PRD cases, modes, validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.doctor_policy import METHODOLOGY_VERSION, snapshot_from_holdings
from app.services.doctor_policy.errors import InvalidRequest
from app.services.doctor_policy.scenario import (
    SnapshotChanged,
    compare_scenarios,
    parse_scenario_request,
    preview_scenario,
    scenario_input_hash,
)
from app.services.portfolio_doctor import AnalyzedHolding

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
DOC = {
    "schema_version": 1,
    "rules": [
        {"rule_id": "max-single", "metric_code": "max_single_position_pct", "operator": "max", "max_value": 35},
        {"rule_id": "equity", "metric_code": "equity_weight_pct", "operator": "range", "min_value": 40, "max_value": 80},
    ],
}


def _h(asset_id, symbol, name, value, isin, asset_type="etf"):
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type, quote_currency="USD",
        market_value=float(value), weight_pct=0.0, isin=isin,
    )


def prd_holdings():
    """PRD example: V = 685.000 €, VWRA H = 319.210 € (46,6%)."""
    return [
        _h(1, "VWRA", "Vanguard FTSE All-World UCITS ETF", 319_210, "IE00BK5BQT80"),
        _h(2, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF", 200_000, "IE00BDBRDM35"),
        _h(3, "EIMI", "iShares Core MSCI EM IMI UCITS ETF", 100_000, "IE00BKM4GZ66"),
        _h(4, "SGLD", "Invesco Physical Gold ETC", 65_790, "IE00B579F325"),
    ]


def prd_snapshot(portfolio_ids=(1,), cash=0.0, holdings=None):
    hs = holdings or prd_holdings()
    return snapshot_from_holdings(
        hs, portfolio_ids=list(portfolio_ids), cash_value=cash,
        price_as_of={h.asset_id: "2026-11-03" for h in hs},
    )


def run(request, snapshot=None, doc=DOC):
    return preview_scenario(snapshot or prd_snapshot(), request, policy_document=doc, now=NOW)


def by_symbol(result):
    return {c.symbol: c for c in result.changes}


# -- golden -----------------------------------------------------------------


def test_prd_required_new_cash_golden():
    snap = prd_snapshot()
    assert snap.invested_value == pytest.approx(685_000)
    assert snap.weight_of(snap.holdings[0]) == pytest.approx(46.6, abs=0.01)
    r = run({"mode": "new_cash_only", "new_cash": 0})
    assert r.feasible is False
    assert r.infeasible_code == "insufficient_cash"
    # max(0, H/p − V) = 319210/0.35 − 685000 = 227028.571…
    assert r.required_new_cash == pytest.approx(319_210 / 0.35 - 685_000, abs=0.01)
    assert round(r.required_new_cash) == 227_029
    assert "227.029 €" in r.infeasible_reason
    assert r.after is None and r.changes == [] and r.total_after is None
    assert r.disclaimer == "Simulazione teorica; nessun ordine eseguito."


def test_prd_required_cash_is_sufficient_and_resolves_the_violation():
    first = run({"mode": "new_cash_only", "new_cash": 0})
    r = run({"mode": "new_cash_only", "new_cash": first.required_new_cash, "label": "Versa"})
    assert r.feasible and r.label == "Versa"
    changes = by_symbol(r)
    assert changes["VWRA"].action == "hold"
    assert changes["VWRA"].after_weight == pytest.approx(35.0, abs=1e-5)
    # AGGH would pass 35% with a plain pro rata: capped by water-filling.
    assert changes["AGGH"].after_weight <= 35.0 + 1e-9
    assert all(c.delta_value >= 0 for c in r.changes)
    assert [v.rule_id for v in r.violations_resolved] == ["max-single"]
    assert r.violations_resolved[0].reason and r.violations_resolved[0].label
    assert r.violations_new == []
    assert r.total_after == pytest.approx(r.total_before + r.cash_in)
    assert r.after.volatility.value is None and r.after.volatility.status == "not_available"


def test_prd_example_c_no_sell_no_cash_is_infeasible():
    """«Scendi a 35% senza vendere né versare»: infeasible, no invented scenario."""
    r = run({"mode": "rebalance", "target_weights": {"1": 35}, "constraints": {"no_sell": True}})
    assert r.feasible is False and r.infeasible_code == "no_sell"
    assert round(r.required_new_cash) == 227_029
    assert r.after is None and r.changes == []


def test_target_weights_from_request_override_policy_cap():
    r = run({"mode": "new_cash_only", "new_cash": 0, "target_weights": {"1": 40}})
    assert r.required_new_cash == pytest.approx(319_210 / 0.40 - 685_000, abs=0.01)


def test_new_cash_without_caps_keeps_weights():
    r = run({"mode": "new_cash_only", "new_cash": 10_000}, doc=None)
    assert r.feasible
    for c in r.changes:
        assert c.after_weight == pytest.approx(c.before_weight)
    assert any("Nessuna policy" in w for w in r.warnings)
    assert r.after.evaluation_status == "no_policy"


def test_keep_equity_total_new_cash():
    r = run({"mode": "new_cash_only", "new_cash": 300_000, "constraints": {"keep_equity_total": True}})
    assert r.feasible
    assert r.after.metrics["equity_weight_pct"].value == pytest.approx(r.before.metrics["equity_weight_pct"].value)
    assert by_symbol(r)["VWRA"].after_weight <= 35 + 1e-9


def test_keep_equity_total_infeasible_when_only_equity_is_capped():
    holdings = [
        _h(1, "VWRA", "Vanguard FTSE All-World UCITS ETF", 600_000, "IE00BK5BQT80"),
        _h(2, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF", 400_000, "IE00BDBRDM35"),
    ]
    r = run(
        {"mode": "new_cash_only", "new_cash": 2_000_000, "constraints": {"keep_equity_total": True}},
        snapshot=prd_snapshot(holdings=holdings),
    )
    assert r.feasible is False and r.infeasible_code == "keep_equity_total"


def test_capacity_exceeded_single_holding():
    holdings = [_h(1, "VWRA", "Vanguard FTSE All-World UCITS ETF", 100_000, "IE00BK5BQT80")]
    r = run({"mode": "new_cash_only", "new_cash": 500_000}, snapshot=prd_snapshot(holdings=holdings))
    assert r.feasible is False and r.infeasible_code == "capacity_exceeded"


# -- rebalance / manual -----------------------------------------------------


def test_rebalance_with_sales_hits_targets_and_conserves_value():
    r = run({"mode": "rebalance", "target_weights": {"1": 35, "2": 30}})
    assert r.feasible
    c = by_symbol(r)
    assert c["VWRA"].after_weight == pytest.approx(35)
    assert c["AGGH"].after_weight == pytest.approx(30)
    # Unlisted EIMI/SGLD share the remaining 35% pro rata.
    assert c["EIMI"].after_weight / c["SGLD"].after_weight == pytest.approx(100_000 / 65_790)
    assert r.total_after == pytest.approx(r.total_before)
    assert r.costs.total == 0
    assert r.turnover_pct == pytest.approx(sum(abs(x.delta_value) for x in r.changes) / (2 * 685_000) * 100)


def test_rebalance_with_fees_reconciles():
    r = run({"mode": "rebalance", "target_weights": {"1": 35}, "fee_model": {"pct": 0.1, "fixed": 2}})
    assert r.feasible
    assert r.costs.operations == 4 and r.costs.fixed == pytest.approx(8)
    assert r.total_after == pytest.approx(r.total_before - r.costs.total)
    assert by_symbol(r)["VWRA"].after_weight == pytest.approx(35)
    assert r.after.cash_value == pytest.approx(0, abs=1e-6)


def test_rebalance_turnover_limit():
    r = run({"mode": "rebalance", "target_weights": {"1": 35}, "constraints": {"max_turnover_pct": 5}})
    assert r.feasible is False and r.infeasible_code == "turnover_exceeded"
    assert r.turnover_pct > 5


def test_rebalance_weights_must_cover_100_when_all_listed():
    with pytest.raises(InvalidRequest) as exc:
        run({"mode": "rebalance", "target_weights": {"1": 30, "2": 30, "3": 20, "4": 10}})
    assert exc.value.field_errors[0]["code"] == "sum_not_100"


def test_rebalance_zero_weight_no_sell_is_impossible():
    r = run({"mode": "rebalance", "target_weights": {"4": 0}, "constraints": {"no_sell": True}, "new_cash": 1e6})
    assert r.feasible is False and r.infeasible_code == "impossible_without_sell"
    assert r.required_new_cash is None


def test_manual_operations_by_symbol_and_leftover_cash():
    r = run({
        "mode": "manual", "new_cash": 1000,
        "operations": [
            {"symbol": "vwra", "action": "sell", "amount": 50_000},
            {"symbol": "AGGH", "action": "buy", "amount": 40_000},
        ],
    }, snapshot=prd_snapshot(cash=500))
    assert r.feasible
    assert r.after.cash_value == pytest.approx(500 + 11_000)
    assert r.total_after == pytest.approx(r.total_before + 1000)
    assert by_symbol(r)["VWRA"].action == "sell"


def test_manual_insufficient_cash_and_oversell_and_no_sell():
    r = run({"mode": "manual", "operations": [{"asset_id": 2, "action": "buy", "amount": 5000}], "new_cash": 1000})
    assert r.feasible is False and r.infeasible_code == "insufficient_cash"
    assert r.required_new_cash == pytest.approx(5000)
    r = run({"mode": "manual", "operations": [{"asset_id": 4, "action": "sell", "amount": 70_000}]})
    assert r.infeasible_code == "oversell"
    r = run({
        "mode": "manual", "constraints": {"no_sell": True},
        "operations": [{"asset_id": 4, "action": "sell", "amount": 10}],
    })
    assert r.infeasible_code == "no_sell"


def test_manual_use_cash_balance():
    snap = prd_snapshot(cash=10_000)
    req = {"mode": "manual", "operations": [{"asset_id": 2, "action": "buy", "amount": 8000}]}
    assert run(req, snapshot=snap).feasible is False
    r = run({**req, "constraints": {"use_cash_balance": True}}, snapshot=snap)
    assert r.feasible and r.after.cash_value == pytest.approx(2000)
    assert r.total_after == pytest.approx(r.total_before)


def test_manual_keep_equity_total_violation():
    r = run({
        "mode": "manual", "constraints": {"keep_equity_total": True},
        "operations": [{"asset_id": 1, "action": "sell", "amount": 1000}, {"asset_id": 2, "action": "buy", "amount": 1000}],
    })
    assert r.feasible is False and r.infeasible_code == "keep_equity_total"


def test_sell_everything_gives_empty_after_state():
    holdings = [_h(1, "VWRA", "Vanguard FTSE All-World UCITS ETF", 1000, "IE00BK5BQT80")]
    r = run(
        {"mode": "manual", "operations": [{"asset_id": 1, "action": "sell", "amount": 1000}]},
        snapshot=prd_snapshot(holdings=holdings),
    )
    assert r.feasible
    assert r.after.invested_value == 0 and r.after.cash_value == pytest.approx(1000)
    assert r.after.evaluation_status == "empty_portfolio"


# -- validation ---------------------------------------------------------------


@pytest.mark.parametrize("body, field", [
    ({"mode": "manual", "operations": [{"asset_id": 99, "action": "buy", "amount": 1}]}, "operations[0]"),
    ({"mode": "manual", "operations": [{"symbol": "NOPE", "action": "buy", "amount": 1}]}, "operations[0]"),
    ({"mode": "rebalance", "target_weights": {"99": 10}}, "target_weights.99"),
])
def test_unknown_asset_is_400(body, field):
    with pytest.raises(InvalidRequest) as exc:
        run(body)
    assert exc.value.status_code == 400
    assert exc.value.field_errors[0]["field"] == field
    assert exc.value.field_errors[0]["code"] == "unknown_asset"


@pytest.mark.parametrize("body", [
    {"mode": "manual", "operations": [{"asset_id": 1, "action": "buy", "amount": -5}]},
    {"mode": "manual", "operations": [{"asset_id": 1, "action": "buy", "amount": 0}]},
    {"mode": "manual", "operations": [{"asset_id": 1, "action": "buy", "amount": float("nan")}]},
    {"mode": "manual", "operations": [{"asset_id": 1, "action": "buy", "amount": float("inf")}]},
    {"mode": "manual", "operations": [{"asset_id": 1, "action": "buy", "amount": "100"}]},
    {"mode": "manual", "operations": [{"asset_id": 1, "action": "short", "amount": 1}]},
    {"mode": "manual", "operations": [{"action": "buy", "amount": 1}]},
    {"mode": "manual", "operations": [{"asset_id": 1, "action": "buy", "amount": 1}] * 51},
    {"mode": "manual", "operations": []},
    {"mode": "new_cash_only", "new_cash": -1},
    {"mode": "new_cash_only", "new_cash": True},
    {"mode": "new_cash_only", "operations": [{"asset_id": 1, "action": "buy", "amount": 1}]},
    {"mode": "rebalance", "target_weights": {}},
    {"mode": "rebalance", "target_weights": {"1": 101}},
    {"mode": "rebalance", "target_weights": {"1": 60, "2": 50}},
    {"mode": "rebalance", "target_weights": {"1": 35, "VWRA": 30}},
    {"mode": "rebalance", "target_weights": {"1": 35}, "fee_model": {"pct": -1}},
    {"mode": "rebalance", "target_weights": {"1": 35}, "tax_model": "it"},
    {"mode": "rebalance", "target_weights": {"1": 35}, "extra": 1},
    {"mode": "magic"},
])
def test_strict_validation(body):
    with pytest.raises(InvalidRequest):
        run(body)


def test_snapshot_changed_is_409():
    snap = prd_snapshot()
    with pytest.raises(SnapshotChanged) as exc:
        run({"mode": "new_cash_only", "portfolio_ids": [1], "snapshot_id": "deadbeefdeadbeef"}, snapshot=snap)
    assert exc.value.status_code == 409 and exc.value.code == "snapshot_changed"
    assert exc.value.details["current_snapshot_id"] == snap.snapshot_id
    ok = run({"mode": "new_cash_only", "portfolio_ids": [1], "snapshot_id": snap.snapshot_id}, snapshot=snap)
    assert ok.snapshot_id == snap.snapshot_id


def test_request_parsing_accepts_portfolio_id_and_hash_ignores_scope():
    a = parse_scenario_request({"portfolio_id": 5, "mode": "new_cash_only", "new_cash": 10})
    b = parse_scenario_request({"portfolio_ids": [7], "snapshot_id": "x", "mode": "new_cash_only", "new_cash": 10})
    assert a.portfolio_ids == [5]
    assert scenario_input_hash(a) == scenario_input_hash(b)
    c = parse_scenario_request({"portfolio_ids": [7], "mode": "new_cash_only", "new_cash": 11})
    assert scenario_input_hash(c) != scenario_input_hash(a)


# -- compare -------------------------------------------------------------------


def test_compare_uses_one_snapshot_and_ranks():
    snap = prd_snapshot()
    cmp = compare_scenarios(
        snap,
        [
            {"mode": "rebalance", "target_weights": {"1": 35}, "constraints": {"no_sell": True}, "label": "C"},
            {"mode": "new_cash_only", "new_cash": 230_000, "label": "Versa"},
            {"mode": "rebalance", "target_weights": {"1": 35}, "fee_model": {"pct": 0.2}, "label": "Ribilancia"},
        ],
        policy_document=DOC, now=NOW, expected_snapshot_id=snap.snapshot_id,
    )
    assert cmp.snapshot_id == snap.snapshot_id
    assert {s.snapshot_id for s in cmp.scenarios} == {snap.snapshot_id}
    assert [s.label for s in cmp.scenarios] == ["C", "Versa", "Ribilancia"]
    assert cmp.ranking[-1].index == 0 and cmp.ranking[-1].feasible is False
    assert cmp.best_index == 1  # no violation left and no costs
    assert set(cmp.current.metrics) == set(cmp.scenarios[1].after.metrics)
    assert cmp.current.evaluation_summary.failed == 1
    assert cmp.methodology_version == METHODOLOGY_VERSION
    assert "consigli" not in cmp.explanation.lower()
    with pytest.raises(SnapshotChanged):
        compare_scenarios(snap, [{"mode": "new_cash_only"}] * 2, policy_document=DOC, expected_snapshot_id="0" * 16)
    with pytest.raises(InvalidRequest):
        compare_scenarios(snap, [{"mode": "new_cash_only"}], policy_document=DOC)


# -- computational bounds (new_cash_only on large scopes) ----------------------


def test_water_fill_is_not_quadratic_in_saturated_groups():
    """20000 groups saturating a few per round: was ~4 s (list membership), now ~0.03 s."""
    import time

    from app.services.doctor_policy import scenario

    weights = {f"g{i:05d}": 100.0 + i for i in range(20_000)}
    capacity = {k: 30_000.0 - v for k, v in weights.items()}  # heavier -> less room
    amount = sum(capacity.values()) * 0.999
    started = time.perf_counter()
    alloc, left = scenario._water_fill(amount, weights, capacity)
    assert time.perf_counter() - started < 1.0
    assert left == 0.0
    assert sum(alloc.values()) == pytest.approx(amount)
    assert all(alloc[k] <= capacity[k] + 1e-6 for k in weights)


def test_new_cash_on_20_portfolios_x_300_assets_is_fast():
    import time

    holdings = [_h(i + 1, f"S{i}", f"Stock {i}", 100.0 + i, f"US{i:010d}", asset_type="stock") for i in range(6000)]
    holdings[0].market_value = sum(h.market_value for h in holdings) * 0.2
    snap = prd_snapshot(portfolio_ids=range(1, 21), holdings=holdings)
    doc = {"schema_version": 1, "rules": [
        {"rule_id": "m", "metric_code": "max_single_position_pct", "operator": "max", "max_value": 0.017},
    ]}
    from app.services.doctor_policy import scenario
    from app.schemas.doctor_scenario import ScenarioInput

    req = ScenarioInput.model_validate({"mode": "new_cash_only", "new_cash": 1e11, "fee_model": {"pct": 0.1, "fixed": 2}})
    book = scenario._book(snap)
    started = time.perf_counter()
    plan = scenario._plan_new_cash(book, req, doc)
    assert time.perf_counter() - started < 1.0
    assert plan.buys


def test_required_cash_refinement_is_bounded(monkeypatch):
    from app.services.doctor_policy import scenario

    monkeypatch.setattr(scenario, "MAX_REQUIRED_CASH_ITERATIONS", 0)
    with pytest.raises(InvalidRequest) as info:
        run({"portfolio_ids": [1], "mode": "new_cash_only", "new_cash": 0})
    assert info.value.status_code == 400
    assert info.value.details["field_errors"][0]["code"] == "too_complex"
    assert "troppo complesso" in info.value.message.lower()
