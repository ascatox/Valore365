"""TASK-83: `_calculate_pac_contribution` non dichiara allocato un importo senza destinazione.

Invariante: `Σ distribution[].amount_eur == total_allocated` (al centesimo) e
`total_allocated + unallocated_amount == monthly_amount`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.models import AllocationItem, PortfolioSummary, PortfolioTargetAllocationItem, Position

PID = 1


def make_repo(values: dict[str, float], targets: dict[str, float]) -> MagicMock:
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
        unrealized_pl=0.0, unrealized_pl_pct=0.0, cash_balance=0.0,
    )
    repo.get_allocation.return_value = [
        AllocationItem(asset_id=ids[s], symbol=s, market_value=v, weight_pct=round(v / invested * 100.0, 2))
        for s, v in values.items()
    ]
    repo.list_portfolio_target_allocations.return_value = [
        PortfolioTargetAllocationItem(asset_id=ids[s], symbol=s, name=s, weight_pct=w) for s, w in targets.items()
    ]
    return repo


def pac(values, targets, amount=500.0) -> dict:
    return copilot_tools._calculate_pac_contribution(
        {"monthly_amount": amount}, make_repo(values, targets), MagicMock(), PID, "u",
    )


def cents(x: float) -> int:
    return int(round(x * 100))


def assert_conserved(result: dict, amount: float) -> None:
    rows = result["distribution"]
    assert sum(cents(d["amount_eur"]) for d in rows) == cents(result["total_allocated"])
    assert cents(result["total_allocated"]) + cents(result["unallocated_amount"]) == cents(amount)
    assert all(d["amount_eur"] > 0 for d in rows)


def test_all_holdings_exactly_at_target_allocates_nothing_and_says_why():
    result = pac({"A": 5000.0, "B": 5000.0}, {"A": 50.0, "B": 50.0})
    assert result["distribution"] == []
    assert result["total_allocated"] == 0.0
    assert result["unallocated_amount"] == 500.0
    assert "Nessuno strumento" in result["note"]
    assert_conserved(result, 500.0)


def test_targets_summing_below_100_all_above_target():
    result = pac({"A": 6666.67, "B": 3333.33}, {"A": 60.0, "B": 30.0})
    assert result["distribution"] == []
    assert result["total_allocated"] == 0.0 and result["unallocated_amount"] == 500.0
    assert "90.0%" in result["note"]  # i target non coprono il 100%
    assert_conserved(result, 500.0)


def test_no_underweight_with_some_holdings_above_target():
    # A sopra il target, B esattamente a target, C senza target (fuori dai target).
    result = pac({"A": 6000.0, "B": 3000.0, "C": 1000.0}, {"A": 50.0, "B": 30.0})
    assert result["distribution"] == []
    assert result["total_allocated"] == 0.0 and result["unallocated_amount"] == 500.0
    assert_conserved(result, 500.0)


def test_normal_case_pays_only_underweight_holdings_proportionally():
    # Pesi 70/20/10 con target 50/40/10: solo B è sottopesato.
    result = pac({"A": 7000.0, "B": 2000.0, "C": 1000.0}, {"A": 50.0, "B": 40.0, "C": 10.0})
    assert [d["symbol"] for d in result["distribution"]] == ["B"]
    assert result["distribution"][0]["amount_eur"] == 500.0
    assert result["total_allocated"] == 500.0 and result["unallocated_amount"] == 0.0
    assert "note" not in result
    assert_conserved(result, 500.0)

    # Due sottopesati con scostamenti 10 e 20 punti: un terzo e due terzi.
    result = pac({"A": 6000.0, "B": 3000.0, "C": 1000.0}, {"A": 30.0, "B": 40.0, "C": 30.0})
    amounts = {d["symbol"]: d["amount_eur"] for d in result["distribution"]}
    assert set(amounts) == {"B", "C"}
    assert amounts == {"C": 333.33, "B": 166.67}
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


def test_non_positive_amount_is_an_error():
    assert "error" in pac({"A": 1.0}, {"A": 50.0}, 0)
    assert "error" in pac({"A": 1.0}, {"A": 50.0}, 0.004)  # sotto il centesimo


def test_no_targets_returns_note_without_total():
    result = pac({"A": 1000.0}, {})
    assert result == {"distribution": [], "note": "Nessun target configurato."}
