from datetime import datetime, timezone

import pytest

from app.repository._base import BaseRepositoryMixin


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


def _buy_row(quantity: float) -> dict:
    return {
        "id": 1,
        "trade_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "side": "buy",
        "quantity": quantity,
    }


def test_inventory_timeline_accepts_naive_candidate_against_aware_rows():
    conn = _FakeConn([_buy_row(10)])

    BaseRepositoryMixin()._assert_non_negative_inventory_timeline(
        conn,
        1,
        1,
        candidate={"id": None, "trade_at": datetime(2026, 10, 13), "side": "sell", "quantity": 5.0},
    )


def test_inventory_timeline_still_rejects_oversell_with_naive_candidate():
    conn = _FakeConn([_buy_row(1)])

    with pytest.raises(ValueError, match="Quantita insufficiente"):
        BaseRepositoryMixin()._assert_non_negative_inventory_timeline(
            conn,
            1,
            1,
            candidate={"id": None, "trade_at": datetime(2026, 10, 13), "side": "sell", "quantity": 5.0},
        )
