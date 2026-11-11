"""TASK-85: `get_target_drift`, PAC e ribilanciamento danno lo stesso peso a ogni strumento.

Decisione del proprietario (2026-11-11): la base è quella di `calculate_rebalance_orders`,
cioè il valore degli strumenti con target più la liquidità attuale (modello della performance,
`summary.cash_balance`). Caso del portafoglio 9101 del seed dell'Auditor: posizioni
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
TOTAL = 109256.5
# 70.000 / 109.256,50 = 64,07 %; 20.000 / … = 18,31 %; 10.000 / … = 9,15 %.
EXPECTED = {"AUDEQ.MI": 64.07, "AUDBD.MI": 18.31, "AUDTECH.DE": 9.15}


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


def test_seed_9101_same_weight_in_drift_pac_and_rebalance():
    repo = make_repo()
    drift = run("get_target_drift", {}, repo)
    pac = run("calculate_pac_contribution", {"monthly_amount": 500.0}, repo)
    reb = run("calculate_rebalance_orders", {"mode": "rebalance"}, repo)

    drift_w = {d["symbol"]: d["current_weight"] for d in drift["drift"]}
    reb_w = {o["symbol"]: o["current_weight_pct"] for o in reb["orders"]}
    pac_w = {d["symbol"]: d["current_weight"] for d in pac["distribution"]}

    assert drift_w == EXPECTED
    # Ogni strumento esce dal tolerance band: il ribilanciamento ha un ordine per ciascuno.
    assert reb_w == EXPECTED
    # Il PAC versa sugli strumenti sotto target, con lo stesso peso attuale.
    assert set(pac_w) == {"AUDBD.MI", "AUDTECH.DE"}
    assert all(pac_w[s] == EXPECTED[s] for s in pac_w)

    # Stessa base dichiarata dai tre tool.
    assert drift["total_value"] == pac["total_value"] == reb["total_value"] == TOTAL
    assert drift["cash_balance"] == reb["totals"]["cash_before"] == CASH
    assert drift["weight_basis_note"] == pac["weight_basis_note"]

    # AUDTECH.DE: 0,85 pp sotto target per tutti (prima: «in linea» per get_target_drift).
    tech = next(d for d in drift["drift"] if d["symbol"] == "AUDTECH.DE")
    assert tech["drift"] == -0.85
    assert next(o for o in reb["orders"] if o["symbol"] == "AUDTECH.DE")["side"] == "buy"


def test_seed_9101_pac_keeps_task83_conservation():
    pac = run("calculate_pac_contribution", {"monthly_amount": 500.0}, make_repo())
    cents = sum(int(round(d["amount_eur"] * 100)) for d in pac["distribution"])
    assert cents == int(round(pac["total_allocated"] * 100)) == 50000
    assert pac["unallocated_amount"] == 0.0
    # Ripartizione proporzionale allo scostamento sulla nuova base: −21,69 e −0,85 pp.
    by = {d["symbol"]: d for d in pac["distribution"]}
    assert by["AUDBD.MI"]["amount_eur"] == pytest.approx(500 * 21.69 / 22.54, abs=0.01)
    # Peso dopo il versamento sulla stessa base più il versamento.
    assert by["AUDBD.MI"]["new_weight_after"] == round((20000 + by["AUDBD.MI"]["amount_eur"]) / (TOTAL + 500) * 100, 2)


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
    assert {round(x.current_weight_pct, 2) for x in w.by_key.values()} == set(EXPECTED.values())
