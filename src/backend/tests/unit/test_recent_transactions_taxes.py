"""TASK-93: le righe di get_recent_transactions e get_aggregate_recent_transactions espongono le imposte.

Con ``total`` (lordo), ``fees`` e ``taxes`` la liquidità del modello (TASK-49,
``app.repository._cash_model``) si ricostruisce dalle righe mostrate. Esperimento del report
dell'Auditor del 2026-11-11 (S-2026-11-11-16): 5.460,10 €, contro 5.473,50 senza le imposte.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.copilot_tools import _get_recent_transactions
from app.mcp_server.aggregate_tools import _recent_transactions
from app.models import TransactionListItem
from app.repository._cash_model import cash_delta

# (side, quantity, price, fees, taxes), dalla più recente.
SPEC = [
    ("sell", 10, 95.0, 1.5, 3.0), ("withdrawal", 1, 1000.0, 0, 0), ("dividend", 1, 40.0, 0, 10.4),
    ("interest", 1, 12.0, 0, 0), ("fee", 1, 25.0, 0, 0), ("buy", 50, 90.0, 2.0, 0), ("deposit", 1, 10000.0, 0, 0),
]
CASH_TOTAL = 5460.10


def _items(portfolio_id: int = 1) -> list[TransactionListItem]:
    return [
        TransactionListItem(
            id=10 + i, portfolio_id=portfolio_id, asset_id=7 if side in ("buy", "sell", "dividend") else None,
            side=side, trade_at=datetime(2026, 10, 30 - i, 12, tzinfo=timezone.utc), quantity=q, price=p,
            fees=f, taxes=t, trade_currency="EUR", notes=None, symbol="AUDEQ.MI" if side in ("buy", "sell", "dividend") else None,
            asset_name="ETF", portfolio_name=f"P{portfolio_id}",
        )
        for i, (side, q, p, f, t) in enumerate(SPEC)
    ]


def _rebuild(rows: list[dict]) -> float:
    """Saldo dalle righe con la funzione del modello di liquidità (costi = fees + taxes su buy/sell)."""
    total = 0.0
    for r in rows:
        trade = r["type"] in ("buy", "sell")
        total += cash_delta(r["type"], r["total"], r["fees"] + r["taxes"] if trade else 0.0, r["taxes"])
    return total


def test_recent_transactions_expose_taxes_of_sell_and_dividend():
    rows = _get_recent_transactions({}, SimpleNamespace(list_transactions=lambda pid, uid: _items()), None, 1, "u")[
        "transactions"]
    by_side = {r["type"]: r for r in rows}
    assert (by_side["sell"]["total"], by_side["sell"]["fees"], by_side["sell"]["taxes"]) == (950.0, 1.5, 3.0)
    assert (by_side["dividend"]["total"], by_side["dividend"]["taxes"]) == (40.0, 10.4)
    assert by_side["buy"]["taxes"] == 0 and by_side["deposit"]["taxes"] == 0
    assert _rebuild(rows) == pytest.approx(CASH_TOTAL)
    # Senza le imposte il ricalcolo dava 5.473,50 (13,40 di differenza).
    assert _rebuild([{**r, "taxes": 0.0} for r in rows]) == pytest.approx(CASH_TOTAL + 13.40)


def test_aggregate_recent_transactions_have_the_same_keys():
    single = _get_recent_transactions({}, SimpleNamespace(list_transactions=lambda pid, uid: _items()), None, 1, "u")
    deps = SimpleNamespace(repo=SimpleNamespace(list_transactions_multi=lambda ids, uid: _items()))
    rows = _recent_transactions(deps, [1, 2], "u")["transactions"]
    assert all(set(r) == set(s) | {"portfolio_id", "portfolio_name"} for r, s in zip(rows, single["transactions"]))
    by_side = {r["type"]: r for r in rows}
    assert (by_side["sell"]["taxes"], by_side["dividend"]["taxes"]) == (3.0, 10.4)
    assert _rebuild(rows) == pytest.approx(CASH_TOTAL)


def test_rows_without_taxes_attribute_default_to_zero():
    row = SimpleNamespace(id=1, portfolio_id=1, portfolio_name="P1", trade_at=None, side="buy", symbol="X",
                          asset_name="", quantity=1.0, price=10.0, trade_currency="EUR", fees=0.0)
    deps = SimpleNamespace(repo=SimpleNamespace(list_transactions_multi=lambda ids, uid: [row]))
    assert _recent_transactions(deps, [1], "u")["transactions"][0]["taxes"] == 0
