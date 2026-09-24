from app.models import Position
from app.repository._positions import PositionsMixin


class _Repo(PositionsMixin):
    def __init__(self):
        self.calls = 0

    def _compute_positions(self, portfolio_id, user_id, stale_days):
        self.calls += 1
        return [Position.model_construct(asset_id=1, symbol="VWCE", market_value=100.0)]


def test_get_positions_not_memoized_outside_scope():
    repo = _Repo()
    repo.get_positions(1, "u")
    repo.get_positions(1, "u")
    assert repo.calls == 2


def test_get_positions_memoized_inside_scope():
    repo = _Repo()
    with repo.memoize_positions():
        first = repo.get_positions(1, "u")
        first[0].market_value = 0.0  # callers mutating results must not affect the memo
        second = repo.get_positions(1, "u")
        repo.get_positions(2, "u")
    assert repo.calls == 2
    assert second[0].market_value == 100.0
    repo.get_positions(1, "u")
    assert repo.calls == 3
