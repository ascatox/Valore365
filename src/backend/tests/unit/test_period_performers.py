from datetime import date

from app.models import Position
from app.repository._positions import PositionsMixin


def _pos(asset_id, symbol, day_change_pct=0.0, quantity=1.0):
    return Position.model_construct(
        asset_id=asset_id, symbol=symbol, name=symbol, quantity=quantity, day_change_pct=day_change_pct,
    )


class _Repo(PositionsMixin):
    def __init__(self, positions, prices=None):
        self.positions = positions
        self.prices = prices or {}
        self.price_calls = []

    def get_positions(self, portfolio_id, user_id, stale_days=5):
        return self.positions

    def _get_period_prices(self, asset_ids, start_date):
        self.price_calls.append((asset_ids, start_date))
        return self.prices


def test_one_day_window_reuses_day_change():
    repo = _Repo([_pos(1, "A", 0.68), _pos(2, "B", -2.76)])
    result = repo.get_period_performers(1, "u", 1)
    assert [(r.symbol, r.return_pct) for r in result] == [("A", 0.68), ("B", -2.76)]
    assert repo.price_calls == []


def test_multi_day_window_uses_start_close_and_current_price():
    repo = _Repo(
        [_pos(1, "A"), _pos(2, "B"), _pos(3, "NOHIST")],
        prices={
            1: ((date(2026, 8, 29), 100.0), 110.0),
            2: ((date(2026, 8, 28), 50.0), 45.0),
            3: (None, 12.0),
        },
    )
    result = repo.get_period_performers(1, "u", 30, today=date(2026, 9, 28))
    assert repo.price_calls == [([1, 2, 3], date(2026, 8, 29))]
    assert [(r.symbol, r.return_pct, r.start_date) for r in result] == [
        ("A", 10.0, date(2026, 8, 29)),
        ("B", -10.0, date(2026, 8, 28)),
    ]


def test_closed_positions_are_ignored():
    repo = _Repo([_pos(1, "A", 1.0, quantity=0.0)])
    assert repo.get_period_performers(1, "u", 1) == []
