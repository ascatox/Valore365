"""TASK-85/95: `get_target_drift`, PAC, ribilanciamento e what-if danno lo stesso peso a ogni strumento.

Decisione del proprietario TASK-95 (2026-11-16, sostituisce la base di TASK-85): la liquidità
non si usa mai per ribilanciare; la base dei pesi è il solo valore degli strumenti con target,
liquidità esclusa. Caso del portafoglio 9101 del seed dell'Auditor: posizioni
70.000 / 20.000 / 10.000 €, liquidità 9.256,50 €, target 50/40/10.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.copilot.snapshot import build_portfolio_snapshot_light
from app.models import AllocationItem, PortfolioSummary, PortfolioTargetAllocationItem, Position
from app.services.rebalance import current_target_weights

PID = 9101
VALUES = {"AUDEQ.MI": 70000.0, "AUDBD.MI": 20000.0, "AUDTECH.DE": 10000.0}
TARGETS = {"AUDEQ.MI": 50.0, "AUDBD.MI": 40.0, "AUDTECH.DE": 10.0}
CASH = 9256.5
TOTAL = 100000.0
# 70.000 / 100.000 = 70 %; 20 %; 10 % (con la base di TASK-85 erano 64,07 / 18,31 / 9,15).
EXPECTED = {"AUDEQ.MI": 70.0, "AUDBD.MI": 20.0, "AUDTECH.DE": 10.0}


def make_repo(values=VALUES, targets=TARGETS, cash=CASH, extra_positions=None) -> MagicMock:
    values = {**values, **(extra_positions or {})}
    ids = {s: i for i, s in enumerate(sorted(set(values) | set(targets)), start=9101)}
    invested = sum(values.values())
    repo = MagicMock()
    repo.get_positions.return_value = [
        Position(
            asset_id=ids[s], symbol=s, name=s, quantity=v / 50.0, avg_cost=50.0, market_price=50.0,
            market_value=v, unrealized_pl=0.0, unrealized_pl_pct=0.0, weight=round(v / invested * 100.0, 2),
        )
        for s, v in values.items()
    ]
    repo.get_summary.return_value = PortfolioSummary(
        portfolio_id=PID, base_currency="EUR", market_value=invested, cost_basis=invested,
        unrealized_pl=0.0, unrealized_pl_pct=0.0, cash_balance=cash,
    )
    # Pesi sulle sole posizioni: la vecchia base, che non deve più entrare nei tre tool.
    repo.get_allocation.return_value = [
        AllocationItem(asset_id=ids[s], symbol=s, market_value=v, weight_pct=round(v / invested * 100.0, 2))
        for s, v in values.items()
    ]
    repo.list_portfolio_target_allocations.return_value = [
        PortfolioTargetAllocationItem(asset_id=ids[s], symbol=s, name=s, weight_pct=w) for s, w in targets.items()
    ]
    return repo


def run(tool: str, args: dict, repo: MagicMock) -> dict:
    return copilot_tools.execute_tool(tool, args, repo, MagicMock(), PID, "u")


def test_seed_9101_same_weight_in_drift_pac_rebalance_and_what_if():
    repo = make_repo()
    drift = run("get_target_drift", {}, repo)
    pac = run("calculate_pac_contribution", {"monthly_amount": 500.0}, repo)
    reb = run("calculate_rebalance_orders", {"mode": "rebalance"}, repo)

    drift_w = {d["symbol"]: d["current_weight"] for d in drift["drift"]}
    assert drift_w == EXPECTED
    assert {d["symbol"]: d["drift"] for d in drift["drift"]} == {
        "AUDEQ.MI": 20.0, "AUDBD.MI": -20.0, "AUDTECH.DE": 0.0}
    reb_w = {o["symbol"]: o["current_weight_pct"] for o in reb["orders"]}
    assert reb_w == {"AUDEQ.MI": 70.0, "AUDBD.MI": 20.0}  # AUDTECH.DE in linea: nessun ordine
    pac_w = {d["symbol"]: d["current_weight"] for d in pac["distribution"]}
    assert set(pac_w) == {"AUDBD.MI", "AUDTECH.DE"}
    assert all(pac_w[s] == EXPECTED[s] for s in pac_w)
    for symbol, expected_drift in (("AUDEQ.MI", 20.0), ("AUDBD.MI", -20.0), ("AUDTECH.DE", 0.0)):
        wi = run("calculate_what_if", {"action": "buy", "symbol": symbol, "amount_eur": 1000.0}, repo)
        assert wi["old_drift"] == expected_drift
        assert wi["target_basis"]["total_value_before"] == TOTAL
        assert wi["target_basis"]["total_value_after"] == TOTAL + 1000

    # Stessa base dichiarata da tutti i tool; la liquidità è riportata ma non entra.
    assert drift["total_value"] == pac["total_value"] == reb["total_value"] == TOTAL
    assert drift["cash_balance"] == reb["totals"]["cash_before"] == CASH
    assert drift["weight_basis_note"] == pac["weight_basis_note"]


def test_seed_9101_rebalance_never_spends_the_cash():
    """TASK-95: vendita AUDEQ.MI e acquisto AUDBD.MI per lo stesso importo, liquidità invariata
    (con la base di TASK-85: vendita 15.371,75, acquisti 23.702,60 + 925,65, liquidità spesa)."""
    reb = run("calculate_rebalance_orders", {"mode": "rebalance"}, make_repo())
    assert [(o["side"], o["symbol"], o["amount_eur"], o["weight_after_pct"]) for o in reb["orders"]] == [
        ("sell", "AUDEQ.MI", 20000.0, 50.0), ("buy", "AUDBD.MI", 20000.0, 40.0)]
    t = reb["totals"]
    assert t["sells_eur"] == t["buys_eur"] == 20000.0
    assert t["cash_before"] == t["cash_after"] == CASH and t["extra_cash"] == 0.0
    assert t["invariant_ok"] is True


def test_seed_9101_pac_keeps_task83_conservation():
    pac = run("calculate_pac_contribution", {"monthly_amount": 500.0}, make_repo())
    cents = sum(int(round(d["amount_eur"] * 100)) for d in pac["distribution"])
    assert cents == int(round(pac["total_allocated"] * 100)) == 50000
    assert pac["unallocated_amount"] == 0.0
    # TASK-90/95: in proporzione al fabbisogno sulla base dopo il versamento (100.500 €, liquidità
    # esclusa): AUDBD.MI 40.200 − 20.000 = 20.200, AUDTECH.DE 10.050 − 10.000 = 50, AUDEQ.MI 0.
    by = {d["symbol"]: d for d in pac["distribution"]}
    assert by["AUDBD.MI"]["amount_eur"] == 498.77
    assert by["AUDTECH.DE"]["amount_eur"] == 1.23
    assert by["AUDBD.MI"]["new_weight_after"] == round((20000 + 498.77) / (TOTAL + 500) * 100, 2)


def test_seed_9101_pac_of_100000_equals_buy_only():
    """TASK-90/95: con 100.000 € i fabbisogni sulla base dopo il versamento (200.000 €) sono
    30.000 / 60.000 / 10.000 = l'importo: PAC e buy_only portano tutti esattamente al target."""
    repo = make_repo()
    pac = run("calculate_pac_contribution", {"monthly_amount": 100000.0}, repo)
    bo = run("calculate_rebalance_orders", {"mode": "buy_only", "available_cash": 100000.0}, repo)
    rows = {d["symbol"]: d for d in pac["distribution"]}
    orders = {o["symbol"]: o for o in bo["orders"]}
    expected = {"AUDEQ.MI": 30000.0, "AUDBD.MI": 60000.0, "AUDTECH.DE": 10000.0}
    assert {s: d["amount_eur"] for s, d in rows.items()} == expected
    assert {s: o["amount_eur"] for s, o in orders.items()} == expected
    assert {s: d["new_weight_after"] for s, d in rows.items()} == TARGETS
    assert pac["total_allocated"] == 100000.0 and pac["unallocated_amount"] == 0.0
    assert pac["total_need_eur"] == 100000.0
    assert bo["totals"]["cash_after"] == CASH  # la liquidità del portafoglio resta


@pytest.mark.parametrize("cash", [0.0, CASH, 50000.0])
@pytest.mark.parametrize("amount", [0.07, 500.0, 333.33, 45000.0, 100000.0, 250000.0])
def test_pac_always_equals_buy_only(amount, cash):
    """TASK-95: la liquidità non entra mai, quindi il PAC coincide sempre con buy_only con
    available_cash = importo (al centesimo, salvo l'arrotondamento dei singoli ordini)."""
    repo = make_repo(cash=cash)
    pac = run("calculate_pac_contribution", {"monthly_amount": amount}, repo)
    bo = run("calculate_rebalance_orders", {"mode": "buy_only", "available_cash": amount}, repo)
    pac_rows = {d["symbol"]: d["amount_eur"] for d in pac["distribution"]}
    bo_rows = {o["symbol"]: o["amount_eur"] for o in bo["orders"]}
    assert pac_rows.keys() == bo_rows.keys()
    assert all(abs(pac_rows[s] - bo_rows[s]) <= 0.01 for s in pac_rows)
    assert pac["total_value"] == bo["total_value"] - amount == TOTAL
    assert bo["totals"]["cash_after"] == pytest.approx(cash, abs=0.01)


def test_untargeted_holding_stays_out_of_the_base_everywhere():
    repo = make_repo(extra_positions={"AUDOUT.MI": 5000.0})
    drift = run("get_target_drift", {}, repo)
    reb = run("calculate_rebalance_orders", {"mode": "rebalance"}, repo)
    assert drift["total_value"] == reb["total_value"] == TOTAL
    assert drift["untargeted_holdings"] == reb["untargeted_holdings"] == ["AUDOUT.MI"]
    assert {d["symbol"]: d["current_weight"] for d in drift["drift"]} == EXPECTED


def test_copilot_snapshot_drift_uses_the_same_weights():
    repo = make_repo()
    repo.list_portfolios.return_value = [SimpleNamespace(id=PID, name="Seed 9101")]
    snapshot = build_portfolio_snapshot_light(repo, PID, "u", page_context="portfolio")
    drift = run("get_target_drift", {}, repo)
    assert snapshot["target_drift"] == [
        {k: d[k] for k in ("symbol", "current_weight", "target_weight", "drift")} for d in drift["drift"]
    ]


def test_current_target_weights_matches_rebalance_plan_base():
    repo = make_repo()
    w = current_target_weights(repo.get_positions(), repo.list_portfolio_target_allocations(), CASH)
    assert w.base_value == pytest.approx(TOTAL)
    assert w.cash == CASH  # riportata, non nella base (TASK-95)
    assert {round(x.current_weight_pct, 2) for x in w.by_key.values()} == set(EXPECTED.values())
