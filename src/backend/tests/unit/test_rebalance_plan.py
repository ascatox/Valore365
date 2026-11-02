"""TASK-39 (V365-003): rebalancing plan with sells funding the buys."""

from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.models import AllocationItem, PortfolioSummary, PortfolioTargetAllocationItem, Position
from app.services.rebalance import RebalanceHolding, compute_rebalance_plan


def _h(symbol: str, value: float, target: float | None) -> RebalanceHolding:
    return RebalanceHolding(key=symbol, symbol=symbol, current_value=value, target_weight_pct=target)


def _orders(plan) -> dict[str, tuple[str, float]]:
    return {o.symbol: (o.side, round(o.amount, 6)) for o in plan.orders}


def _assert_conserved(plan) -> None:
    assert plan.cash_after >= 0
    assert plan.cash_after == pytest.approx(
        plan.portfolio_cash + plan.extra_cash + plan.sells_total - plan.buys_total, abs=1e-6
    )


def _distance(weights, attr: str) -> float:
    return sum(abs(getattr(w, attr) - w.target_weight_pct) for w in weights)


AUDIT = [_h("VTI", 6122.0, 60), _h("VEUR", 2463.0, 25), _h("VFEM", 1415.0, 15)]


# --- service ------------------------------------------------------------------

def test_audit_case_cash_zero_sells_fund_buys():
    plan = compute_rebalance_plan(AUDIT, portfolio_cash=0, extra_cash=0)
    orders = _orders(plan)
    assert orders["VTI"][0] == "sell"
    assert orders["VTI"][1] == pytest.approx(122.0)  # drift × TOTAL, not × position
    assert orders["VEUR"] == ("buy", pytest.approx(37.0))
    assert orders["VFEM"] == ("buy", pytest.approx(85.0))
    assert plan.sells_total == pytest.approx(plan.buys_total)
    _assert_conserved(plan)
    assert plan.cash_after == pytest.approx(0.0)
    assert [o.side for o in plan.orders][0] == "sell"
    for w in plan.weights:
        assert w.weight_after_pct == pytest.approx(w.target_weight_pct)


def test_extra_cash_is_added_to_portfolio_cash_and_included_in_base():
    plan = compute_rebalance_plan(AUDIT, portfolio_cash=500, extra_cash=500)
    assert plan.base_value == pytest.approx(11000.0)
    _assert_conserved(plan)
    # Total invested at the end equals total base: all cash deployed.
    assert plan.cash_after == pytest.approx(0.0, abs=1e-6)
    for w in plan.weights:
        assert w.weight_after_pct == pytest.approx(w.target_weight_pct)
    # VTI 6122/11000 = 55.65% < 60%: it is now a buy.
    assert _orders(plan)["VTI"][0] == "buy"


def test_all_weather_five_assets():
    holdings = [
        _h("TLT", 3500, 40), _h("VTI", 3850, 30), _h("IEF", 1500, 15),
        _h("DJP", 500, 7.5), _h("GLD", 650, 7.5),
    ]
    plan = compute_rebalance_plan(holdings, portfolio_cash=0)
    orders = _orders(plan)
    assert orders["VTI"] == ("sell", pytest.approx(850.0))
    assert orders["TLT"] == ("buy", pytest.approx(500.0))
    assert orders["DJP"] == ("buy", pytest.approx(250.0))
    assert "IEF" not in orders  # 15.0% == target
    assert orders["GLD"] == ("buy", pytest.approx(100.0))
    _assert_conserved(plan)
    assert _distance(plan.weights, "weight_after_pct") < _distance(plan.weights, "current_weight_pct")


def test_incomplete_targets_leave_untargeted_untouched():
    holdings = [_h("A", 6000, 50), _h("B", 2000, 30), _h("X", 2000, None)]
    plan = compute_rebalance_plan(holdings, portfolio_cash=0)
    assert "X" not in _orders(plan)
    assert plan.untargeted_symbols == ["X"]
    assert plan.untargeted_value == pytest.approx(2000)
    # Targets apply to the remaining value (8000); 20% of it stays unallocated as cash.
    assert plan.base_value == pytest.approx(8000)
    assert plan.unallocated_target_pct == pytest.approx(20)
    assert _orders(plan) == {"A": ("sell", pytest.approx(2000)), "B": ("buy", pytest.approx(400))}
    _assert_conserved(plan)
    assert plan.cash_after == pytest.approx(1600)


def test_single_instrument():
    plan = compute_rebalance_plan([_h("VWCE", 9000, 100)], portfolio_cash=1000)
    assert _orders(plan) == {"VWCE": ("buy", pytest.approx(1000))}
    _assert_conserved(plan)


def test_zero_positions_with_cash_buys_targets():
    holdings = [_h("A", 0, 70), _h("B", 0, 30)]
    plan = compute_rebalance_plan(holdings, portfolio_cash=0, extra_cash=1000)
    assert _orders(plan) == {"A": ("buy", pytest.approx(700)), "B": ("buy", pytest.approx(300))}
    _assert_conserved(plan)


def test_zero_positions_and_zero_cash_gives_no_orders():
    plan = compute_rebalance_plan([_h("A", 0, 70), _h("B", 0, 30)], portfolio_cash=0)
    assert plan.orders == []
    _assert_conserved(plan)


def test_buy_only_never_sells_and_spends_only_cash():
    plan = compute_rebalance_plan(AUDIT, portfolio_cash=0, extra_cash=100, mode="buy_only")
    assert all(o.side == "buy" for o in plan.orders)
    assert plan.sells_total == 0
    assert plan.buys_total <= 100 + 1e-9
    _assert_conserved(plan)


def test_buy_only_scales_buys_proportionally_when_cash_is_short():
    # base 10050; needs: VEUR 0.25*10050-2463=49.5, VFEM 0.15*10050-1415=92.5
    plan = compute_rebalance_plan(AUDIT, portfolio_cash=0, extra_cash=50, mode="buy_only")
    assert plan.buys_scaled is True
    orders = _orders(plan)
    assert orders["VEUR"][1] / orders["VFEM"][1] == pytest.approx(49.5 / 92.5)
    assert plan.buys_total == pytest.approx(50)
    assert plan.cash_after == pytest.approx(0, abs=1e-9)


def test_sell_only_only_sells_and_keeps_proceeds_as_cash():
    plan = compute_rebalance_plan(AUDIT, portfolio_cash=0, mode="sell_only")
    assert _orders(plan) == {"VTI": ("sell", pytest.approx(122.0))}
    assert plan.cash_after == pytest.approx(122.0)
    _assert_conserved(plan)


def test_tolerance_band_half_point():
    holdings = [_h("A", 5040, 50), _h("B", 4960, 50)]  # drift 0.4 pp
    assert compute_rebalance_plan(holdings).orders == []
    holdings = [_h("A", 5060, 50), _h("B", 4940, 50)]  # drift 0.6 pp
    assert _orders(compute_rebalance_plan(holdings)) == {
        "A": ("sell", pytest.approx(60)), "B": ("buy", pytest.approx(60)),
    }


def test_tolerance_band_not_triggered_keeps_small_cash():
    holdings = [_h("A", 5020, 50), _h("B", 4960, 50)]  # 50.2 / 49.6 with 20 of cash
    plan = compute_rebalance_plan(holdings, portfolio_cash=20)
    assert plan.orders == []
    assert plan.cash_after == pytest.approx(20)


def test_one_holding_out_of_band_triggers_full_rebalance():
    # Audit case: VEUR (-0.37 pp) is inside the band but still receives the VTI proceeds.
    plan = compute_rebalance_plan(AUDIT, portfolio_cash=0)
    assert set(_orders(plan)) == {"VTI", "VEUR", "VFEM"}


def test_untradable_overweight_is_not_sold_and_buys_are_scaled():
    holdings = [
        RebalanceHolding("A", "A", 6000, 50, tradable=False),
        _h("B", 2000, 25), _h("C", 1500, 25),
    ]
    plan = compute_rebalance_plan(holdings, portfolio_cash=500)
    assert "A" not in _orders(plan)
    assert plan.buys_scaled is True
    assert plan.buys_total == pytest.approx(500)
    _assert_conserved(plan)


def test_max_orders_keeps_largest_drift_and_stays_funded():
    plan = compute_rebalance_plan(AUDIT, portfolio_cash=0, max_orders=2)
    assert _orders(plan) == {"VTI": ("sell", pytest.approx(122)), "VFEM": ("buy", pytest.approx(85))}
    _assert_conserved(plan)
    assert plan.cash_after == pytest.approx(37)


def test_order_independent():
    holdings = [
        _h("TLT", 3500, 40), _h("VTI", 3800, 30), _h("IEF", 1400, 15),
        _h("DJP", 500, 7.5), _h("GLD", 800, 7.5), _h("X", 300, None),
    ]
    reference = compute_rebalance_plan(holdings, portfolio_cash=120, extra_cash=80)
    rng = random.Random(42)
    for _ in range(10):
        shuffled = holdings[:]
        rng.shuffle(shuffled)
        plan = compute_rebalance_plan(shuffled, portfolio_cash=120, extra_cash=80)
        assert plan.orders == reference.orders
        assert plan.weights == reference.weights
        assert plan.cash_after == reference.cash_after


def test_weights_after_closer_to_target_in_every_mode():
    for mode, extra in (("buy_only", 200), ("rebalance", 0), ("sell_only", 0)):
        plan = compute_rebalance_plan(AUDIT, portfolio_cash=0, extra_cash=extra, mode=mode)
        assert _distance(plan.weights, "weight_after_pct") < _distance(plan.weights, "current_weight_pct"), mode
        _assert_conserved(plan)


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        compute_rebalance_plan(AUDIT, mode="yolo")


# --- copilot tool -------------------------------------------------------------

def _pos(asset_id: int, symbol: str, value: float) -> Position:
    return Position(
        asset_id=asset_id, symbol=symbol, name=symbol, quantity=value / 100, avg_cost=100,
        market_price=100, market_value=value, unrealized_pl=0, unrealized_pl_pct=0, weight=0,
    )


def _tool_repo(values: dict[str, float], targets: dict[str, float], cash: float) -> MagicMock:
    ids = {s: i for i, s in enumerate(sorted(set(values) | set(targets)), start=1)}
    positions = [_pos(ids[s], s, v) for s, v in values.items()]
    invested = sum(values.values())
    repo = MagicMock()
    repo.get_positions.return_value = positions
    repo.get_summary.return_value = PortfolioSummary(
        portfolio_id=1, base_currency="EUR", market_value=invested, cost_basis=invested,
        unrealized_pl=0, unrealized_pl_pct=0, cash_balance=cash,
    )
    repo.get_allocation.return_value = [
        AllocationItem(asset_id=ids[s], symbol=s, market_value=v, weight_pct=round(v / invested * 100, 2))
        for s, v in values.items()
    ]
    repo.list_portfolio_target_allocations.return_value = [
        PortfolioTargetAllocationItem(asset_id=ids[s], symbol=s, name=s, weight_pct=w) for s, w in targets.items()
    ]
    return repo


def _tool(repo, **args) -> dict:
    return copilot_tools._calculate_rebalance_orders(args, repo, MagicMock(), 1, "u")


def test_tool_audit_case_defaults_to_self_financing_rebalance():
    repo = _tool_repo({"VTI": 6122, "VEUR": 2463, "VFEM": 1415}, {"VTI": 60, "VEUR": 25, "VFEM": 15}, cash=0)
    out = _tool(repo)
    assert out["mode"] == "rebalance"
    by_symbol = {o["symbol"]: o for o in out["orders"]}
    assert by_symbol["VTI"]["side"] == "sell"
    assert by_symbol["VTI"]["amount_eur"] == pytest.approx(122.0)
    assert by_symbol["VEUR"]["side"] == "buy"
    assert by_symbol["VFEM"]["side"] == "buy"
    assert by_symbol["VTI"]["current_weight_pct"] == pytest.approx(61.22)
    assert by_symbol["VTI"]["target_weight_pct"] == pytest.approx(60.0)
    assert by_symbol["VTI"]["weight_after_pct"] == pytest.approx(60.0)
    totals = out["totals"]
    assert totals["sells_eur"] == pytest.approx(totals["buys_eur"])
    assert totals["cash_before"] == 0
    assert totals["extra_cash"] == 0
    assert totals["cash_after"] == pytest.approx(0.0)
    assert totals["invariant_ok"] is True
    assert any("commissioni" in n.lower() for n in out["notes"])


def test_tool_includes_portfolio_cash_and_extra_cash():
    repo = _tool_repo({"VTI": 6122, "VEUR": 2463, "VFEM": 1415}, {"VTI": 60, "VEUR": 25, "VFEM": 15}, cash=500)
    out = _tool(repo, available_cash=500)
    totals = out["totals"]
    assert out["total_value"] == pytest.approx(11000.0)
    assert totals["cash_before"] == 500
    assert totals["extra_cash"] == 500
    assert totals["cash_after"] == pytest.approx(
        totals["cash_before"] + totals["extra_cash"] + totals["sells_eur"] - totals["buys_eur"], abs=0.01
    )
    assert totals["cash_after"] >= 0
    assert totals["invariant_ok"] is True


def test_tool_incomplete_targets_reports_untargeted_holdings():
    repo = _tool_repo({"A": 6000, "B": 2000, "X": 2000}, {"A": 50, "B": 30}, cash=0)
    out = _tool(repo)
    assert {o["symbol"] for o in out["orders"]} == {"A", "B"}
    assert out["untargeted_holdings"] == ["X"]
    assert out["unallocated_target_pct"] == pytest.approx(20.0)
    assert any("senza target" in n for n in out["notes"])


def test_tool_modes_and_invalid_mode():
    repo = _tool_repo({"VTI": 6122, "VEUR": 2463, "VFEM": 1415}, {"VTI": 60, "VEUR": 25, "VFEM": 15}, cash=0)
    sell = _tool(repo, mode="sell_only")
    assert [o["side"] for o in sell["orders"]] == ["sell"]
    buy = _tool(repo, mode="buy_only", available_cash=100)
    assert {o["side"] for o in buy["orders"]} == {"buy"}
    assert buy["totals"]["buys_eur"] <= 100
    assert "error" in _tool(repo, mode="yolo")


def test_tool_target_not_held_and_no_targets():
    repo = _tool_repo({}, {"A": 100}, cash=1000)
    out = _tool(repo)
    assert out["orders"][0]["symbol"] == "A"
    assert out["orders"][0]["amount_eur"] == pytest.approx(1000)
    empty = _tool_repo({"A": 100}, {}, cash=0)
    assert _tool(empty)["orders"] == []


def test_tool_schema_exposes_mode_enum_with_rebalance_default():
    tool = next(t for t in copilot_tools.TOOL_DEFINITIONS if t["name"] == "calculate_rebalance_orders")
    mode = tool["parameters"]["properties"]["mode"]
    assert mode["enum"] == ["rebalance", "buy_only", "sell_only"]
    assert mode.get("default") == "rebalance"


# --- REST preview route (shares the service, legacy semantics kept) -----------

def _route_client(values: dict[str, float], targets: dict[str, float]):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes_rebalancing import register_rebalancing_routes
    from app.auth import AuthContext
    from app.rate_limit import require_auth_rate_limited

    repo = _tool_repo(values, targets, cash=1000)  # portfolio cash is ignored by the preview
    repo.get_quote_currencies_for_assets.return_value = {}
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_rebalancing_routes(
        router, repo, settings=MagicMock(), finance_client=MagicMock(),
        historical_service=MagicMock(), ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)
    app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id="u")
    return TestClient(app)


def _preview(client, **payload) -> dict:
    response = client.post("/api/portfolios/1/rebalance/preview", json={"use_latest_prices": False, **payload})
    assert response.status_code == 200, response.text
    return response.json()


def test_route_rebalance_audit_case_self_financing():
    client = _route_client({"VTI": 6122, "VEUR": 2463, "VFEM": 1415}, {"VTI": 60, "VEUR": 25, "VFEM": 15})
    out = _preview(client, mode="rebalance", max_transactions=5)
    items = {i["symbol"]: i for i in out["items"]}
    assert items["VTI"]["side"] == "sell" and items["VTI"]["gross_total"] == pytest.approx(122.0)
    assert items["VEUR"]["gross_total"] == pytest.approx(37.0)
    assert items["VFEM"]["gross_total"] == pytest.approx(85.0)
    assert out["summary"]["estimated_cash_residual"] == pytest.approx(0.0)
    assert items["VTI"]["drift_pct"] == pytest.approx(1.22)


def test_route_buy_only_deploys_all_cash_and_sell_only_sells():
    client = _route_client({"VTI": 6122, "VEUR": 2463, "VFEM": 1415}, {"VTI": 60, "VEUR": 25, "VFEM": 15})
    buy = _preview(client, mode="buy_only", cash_to_allocate=1000)
    assert {i["side"] for i in buy["items"]} == {"buy"}
    assert buy["summary"]["proposed_buy_total"] == pytest.approx(1000.0)
    sell = _preview(client, mode="sell_only")
    assert [(i["symbol"], i["side"]) for i in sell["items"]] == [("VTI", "sell")]
    assert sell["summary"]["estimated_cash_residual"] == pytest.approx(122.0)


def test_route_untargeted_holding_buys_are_funded_by_sells():
    # Legacy weights include X (no target): targets sum to 100 on 80% of the value.
    client = _route_client({"A": 6000, "B": 2000, "X": 2000}, {"A": 50, "B": 50})
    out = _preview(client, mode="rebalance")
    assert out["summary"]["estimated_cash_residual"] >= 0
    assert "X" not in {i["symbol"] for i in out["items"]}
