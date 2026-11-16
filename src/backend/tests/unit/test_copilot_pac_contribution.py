"""TASK-83: `_calculate_pac_contribution` non dichiara allocato un importo senza destinazione.

Invariante: `Σ distribution[].amount_eur == total_allocated` (al centesimo) e
`total_allocated + unallocated_amount == monthly_amount`.

TASK-90 (decisione del proprietario, `methodology.md` §7): il versamento va in proporzione a
quanto manca a ogni strumento per arrivare al target sulla base dopo il versamento (strumenti con
target + liquidità + importo), mai oltre il target; l'importo oltre il fabbisogno totale (solo con
target che sommano meno di 100) va in proporzione ai target. Le attese di TASK-83 «nessuno
strumento sottopesato → niente distribuito» e «quote in proporzione allo scostamento attuale» sono
cambiate di conseguenza.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.models import AllocationItem, PortfolioSummary, PortfolioTargetAllocationItem, Position

PID = 1


def make_repo(values: dict[str, float], targets: dict[str, float], cash: float = 0.0) -> MagicMock:
    ids = {s: i for i, s in enumerate(sorted(set(values) | set(targets)), start=100)}
    invested = sum(values.values())
    repo = MagicMock()
    repo.get_positions.return_value = [
        Position(
            asset_id=ids[s], symbol=s, name=s, quantity=v / 50.0, avg_cost=50.0, market_price=50.0,
            market_value=v, unrealized_pl=0.0, unrealized_pl_pct=0.0,
            weight=round(v / invested * 100.0, 2),
        )
        for s, v in values.items()
    ]
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


def pac(values, targets, amount=500.0, cash=0.0) -> dict:
    return copilot_tools._calculate_pac_contribution(
        {"monthly_amount": amount}, make_repo(values, targets, cash), MagicMock(), PID, "u",
    )


def cents(x: float) -> int:
    return int(round(x * 100))


def assert_conserved(result: dict, amount: float) -> None:
    rows = result["distribution"]
    assert sum(cents(d["amount_eur"]) for d in rows) == cents(result["total_allocated"])
    assert cents(result["total_allocated"]) + cents(result["unallocated_amount"]) == cents(amount)
    assert all(d["amount_eur"] > 0 for d in rows)


def test_all_holdings_exactly_at_target_keep_their_weights():
    # TASK-90 (prima: niente distribuito). Sulla base dopo il versamento (10.500 €) a ciascuno
    # mancano 250 €: i pesi restano 50/50.
    result = pac({"A": 5000.0, "B": 5000.0}, {"A": 50.0, "B": 50.0})
    assert [(d["symbol"], d["amount_eur"], d["new_weight_after"]) for d in result["distribution"]] == [
        ("A", 250.0, 50.0), ("B", 250.0, 50.0)]
    assert result["total_allocated"] == 500.0 and result["unallocated_amount"] == 0.0
    assert result["total_need_eur"] == 500.0 and "note" not in result
    assert_conserved(result, 500.0)


def test_targets_summing_below_100_all_above_target():
    # TASK-90 (prima: niente distribuito). Fabbisogno 0: l'eccedenza va in proporzione ai target 60/30.
    result = pac({"A": 6666.67, "B": 3333.33}, {"A": 60.0, "B": 30.0})
    assert {d["symbol"]: d["amount_eur"] for d in result["distribution"]} == {"A": 333.33, "B": 166.67}
    assert result["total_allocated"] == 500.0 and result["unallocated_amount"] == 0.0
    assert result["total_need_eur"] == 0.0
    assert "90.0%" in result["note"] and "500.0 EUR" in result["note"]  # i target non coprono il 100%
    assert_conserved(result, 500.0)


def test_no_underweight_with_some_holdings_above_target():
    # A sopra il target, B esattamente a target, C senza target (fuori dalla base, nessuna quota).
    # Base 9.000 €, dopo 9.500 €: A 4.750 < 6.000, B 2.850 < 3.000, fabbisogno 0; target 50 + 30 = 80.
    result = pac({"A": 6000.0, "B": 3000.0, "C": 1000.0}, {"A": 50.0, "B": 30.0})
    assert {d["symbol"]: d["amount_eur"] for d in result["distribution"]} == {"A": 312.5, "B": 187.5}
    assert result["total_allocated"] == 500.0 and result["unallocated_amount"] == 0.0
    assert "80.0%" in result["note"]
    assert_conserved(result, 500.0)


def test_all_targets_at_zero_allocate_nothing_and_say_why():
    result = pac({"A": 5000.0, "B": 5000.0}, {"A": 0.0, "B": 0.0})
    assert result["distribution"] == []
    assert result["total_allocated"] == 0.0 and result["unallocated_amount"] == 500.0
    assert "0.0%" in result["note"]
    assert_conserved(result, 500.0)


def test_normal_case_pays_proportionally_to_the_need_after_the_contribution():
    # Pesi 70/20/10 con target 50/40/10, base dopo il versamento 10.500 €: fabbisogni
    # A 0, B 4.200 − 2.000 = 2.200, C 1.050 − 1.000 = 50. Prima (TASK-83) B riceveva tutto e C,
    # a target oggi, scendeva sotto il target.
    result = pac({"A": 7000.0, "B": 2000.0, "C": 1000.0}, {"A": 50.0, "B": 40.0, "C": 10.0})
    assert [(d["symbol"], d["amount_eur"]) for d in result["distribution"]] == [("B", 488.89), ("C", 11.11)]
    assert result["total_allocated"] == 500.0 and result["unallocated_amount"] == 0.0
    assert result["total_need_eur"] == 2250.0
    assert "note" not in result
    assert_conserved(result, 500.0)

    # Fabbisogni B 4.200 − 3.000 = 1.200 e C 3.150 − 1.000 = 2.150 (prima: 1/3 e 2/3 dello scostamento).
    result = pac({"A": 6000.0, "B": 3000.0, "C": 1000.0}, {"A": 30.0, "B": 40.0, "C": 30.0})
    amounts = {d["symbol"]: d["amount_eur"] for d in result["distribution"]}
    assert amounts == {"C": 320.9, "B": 179.1}
    assert_conserved(result, 500.0)


def test_underweight_target_not_held_receives_payment():
    result = pac({"A": 10000.0}, {"A": 50.0, "B": 50.0})
    assert [(d["symbol"], d["amount_eur"]) for d in result["distribution"]] == [("B", 500.0)]
    assert_conserved(result, 500.0)


@pytest.mark.parametrize("amount", [500.0, 100.0, 333.33, 0.07, 1234.567, 999.99])
def test_rows_add_up_exactly_to_total_with_cent_rounding(amount):
    # Sette strumenti con scostamenti diversi: le quote non sono multipli del centesimo.
    values = {f"E{i}": 1000.0 + 37.0 * i for i in range(7)}
    targets = {s: 100 / 7 for s in values}
    result = pac(values, targets, amount)
    assert len(result["distribution"]) >= 3
    assert result["total_allocated"] == round(amount, 2)
    assert result["unallocated_amount"] == 0.0
    assert_conserved(result, round(amount, 2))


def test_three_equal_underweights_split_cents_without_loss():
    values = {"A": 9000.0, "B": 1000.0, "C": 1000.0, "D": 1000.0}
    targets = {"A": 25.0, "B": 25.0, "C": 25.0, "D": 25.0}
    result = pac(values, targets, 100.0)
    amounts = sorted(d["amount_eur"] for d in result["distribution"])
    assert amounts == [33.33, 33.33, 33.34]
    assert result["total_allocated"] == 100.0
    assert_conserved(result, 100.0)


# Portafoglio 9101 del seed: 70.000 / 20.000 / 10.000 € con target 50/40/10, liquidità 9.256,50 €.
SEED_9101 = {"AUDEQ.MI": 70000.0, "AUDBD.MI": 20000.0, "AUDTECH.DE": 10000.0}
SEED_9101_TARGETS = {"AUDEQ.MI": 50.0, "AUDBD.MI": 40.0, "AUDTECH.DE": 10.0}
SEED_9101_CASH = 9256.5
SEED_9101_BASE = 109256.5


def needs_after(values, targets, cash, amount):
    base_after = sum(values.get(s, 0.0) for s in targets) + cash + amount
    return {s: max(t / 100 * base_after - values.get(s, 0.0), 0.0) for s, t in targets.items()}, base_after


@pytest.mark.parametrize("amount", [500.0, SEED_9101_BASE], ids=["small-500", "equal-to-base"])
def test_seed_9101_split_proportional_to_need_never_above_target(amount):
    """TASK-90, criterio #3: versamento piccolo e pari alla base, sotto il fabbisogno totale."""
    result = pac(SEED_9101, SEED_9101_TARGETS, amount, SEED_9101_CASH)
    needs, base_after = needs_after(SEED_9101, SEED_9101_TARGETS, SEED_9101_CASH, amount)
    total_need = sum(needs.values())
    assert total_need >= amount  # con target a 100 il fabbisogno è almeno liquidità + importo
    assert result["total_value"] == SEED_9101_BASE and result["total_need_eur"] == round(total_need, 2)
    rows = {d["symbol"]: d for d in result["distribution"]}
    for s, need in needs.items():
        got = rows[s]["amount_eur"] if s in rows else 0.0
        assert got == pytest.approx(amount * need / total_need, abs=0.01)
        assert got <= need + 0.01  # mai oltre il fabbisogno
    for s, d in rows.items():
        assert d["new_weight_after"] <= d["target_weight"]
        assert d["new_weight_after"] == round((SEED_9101[s] + d["amount_eur"]) / base_after * 100, 2)
    if amount == 500.0:
        assert set(rows) == {"AUDBD.MI", "AUDTECH.DE"}  # AUDEQ.MI resta sopra il target
    else:
        assert set(rows) == set(SEED_9101)  # AUDEQ.MI scende sotto il target: riceve la sua quota
        assert rows["AUDBD.MI"]["new_weight_after"] < 40.0  # prima del TASK-90: oltre il 40 %
    assert "note" not in result
    assert_conserved(result, amount)


def test_seed_9101_amount_above_total_need_with_targets_below_100():
    """TASK-90, criterio #3: importo oltre il fabbisogno totale (target 9101 ridotti a 45/36/9 = 90).

    Base dopo 50.000 €: 159.256,50; fabbisogni AUDEQ.MI 1.665,43, AUDBD.MI 37.332,34, AUDTECH.DE
    4.333,08 (43.330,85 in tutto). I 6.669,15 € di eccedenza vanno in proporzione ai target 45/36/9."""
    targets = {"AUDEQ.MI": 45.0, "AUDBD.MI": 36.0, "AUDTECH.DE": 9.0}
    amount = 50000.0
    result = pac(SEED_9101, targets, amount, SEED_9101_CASH)
    needs, _ = needs_after(SEED_9101, targets, SEED_9101_CASH, amount)
    total_need = sum(needs.values())
    excess = amount - total_need
    assert excess > 0
    rows = {d["symbol"]: d["amount_eur"] for d in result["distribution"]}
    for s, t in targets.items():
        assert rows[s] == pytest.approx(needs[s] + excess * t / 90.0, abs=0.01)
    assert result["total_allocated"] == amount and result["unallocated_amount"] == 0.0
    assert result["total_need_eur"] == round(total_need, 2)
    assert "90.0%" in result["note"]
    assert_conserved(result, amount)


def test_non_positive_amount_is_an_error():
    assert "error" in pac({"A": 1.0}, {"A": 50.0}, 0)
    assert "error" in pac({"A": 1.0}, {"A": 50.0}, 0.004)  # sotto il centesimo


def test_no_targets_returns_note_without_total():
    result = pac({"A": 1000.0}, {})
    assert result == {"distribution": [], "note": "Nessun target configurato."}
