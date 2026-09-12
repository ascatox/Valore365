from datetime import date, timedelta

from app.repository._base import AssetMeta, PortfolioData
from app.repository._summary import SummaryMixin

TODAY = date.today()


class _Position:
    def __init__(self, asset_id: int, quantity: float, market_value: float) -> None:
        self.asset_id = asset_id
        self.quantity = quantity
        self.market_value = market_value
        self.avg_cost = 1.0


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _Conn:
    def __init__(self, daily: list[dict], ticks: list[dict]) -> None:
        self.daily = daily
        self.ticks = ticks

    def execute(self, statement, params):
        sql = " ".join(str(statement).split())
        if "ranked_daily" in sql:
            return _Result(self.daily)
        if "from price_ticks" in sql:
            return _Result(self.ticks)
        if "from fx_rates_1d" in sql:
            return _Result([])
        raise AssertionError(f"unexpected query: {sql}")


class _BeginContext:
    def __init__(self, conn) -> None:
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self, conn) -> None:
        self.conn = conn

    def begin(self):
        return _BeginContext(self.conn)


class _Repo(SummaryMixin):
    """get_summary with everything but the day-change inputs stubbed out."""

    def __init__(self, positions, daily, ticks) -> None:
        self.engine = _Engine(_Conn(daily, ticks))
        self._positions = positions

    def _get_portfolio_for_user(self, conn, portfolio_id, user_id):
        return PortfolioData(id=portfolio_id, base_currency="EUR", cash_balance=0.0)

    def _get_asset_meta(self, conn, asset_ids):
        return {aid: AssetMeta(symbol=f"SYM{aid}", quote_currency="EUR") for aid in asset_ids}

    def get_current_cash_balance_value(self, portfolio_id, user_id):
        return 0.0

    def get_positions(self, portfolio_id, user_id):
        return self._positions


def _bar(asset_id: int, day: date, close: float, rn: int) -> dict:
    return {"asset_id": asset_id, "price_date": day, "close": close, "rn": rn}


def _fresh_asset(asset_id: int) -> list[dict]:
    # Priced yesterday and today: 100 -> 110.
    return [
        _bar(asset_id, TODAY, 110.0, 1),
        _bar(asset_id, TODAY - timedelta(days=1), 100.0, 2),
    ]


def _stale_asset(asset_id: int, days_old: int) -> list[dict]:
    # Last priced weeks ago; its two closes are adjacent but both old.
    last = TODAY - timedelta(days=days_old)
    return [
        _bar(asset_id, last, 60.0, 1),
        _bar(asset_id, last - timedelta(days=1), 50.0, 2),
    ]


def test_a_fresh_asset_contributes_its_move_to_the_day_change():
    repo = _Repo([_Position(1, 2.0, 220.0)], _fresh_asset(1), [])

    summary = repo.get_summary(1, "u")

    assert summary.day_change == 20.0          # 2 units x (110 - 100)
    assert summary.day_change_pct == 10.0      # against a previous value of 200


def test_a_stale_asset_does_not_report_an_old_move_as_todays_change():
    # The asset stopped being priced 60 days ago. Its last two closes are one
    # day apart, so a gap check between them would miss this entirely — what
    # matters is that the current price itself is 60 days old.
    repo = _Repo([_Position(1, 2.0, 120.0)], _stale_asset(1, 60), [])

    summary = repo.get_summary(1, "u")

    assert summary.day_change == 0.0


def test_a_stale_asset_stays_in_the_percentage_denominator():
    # One fresh asset (+20 on a previous value of 200) and one stale asset
    # worth 100 previously. Dropping the stale position from the denominator
    # would report 10%; it must stay, giving 20 / 300.
    positions = [_Position(1, 2.0, 220.0), _Position(2, 2.0, 120.0)]
    repo = _Repo(positions, _fresh_asset(1) + _stale_asset(2, 60), [])

    summary = repo.get_summary(1, "u")

    assert summary.day_change == 20.0
    assert summary.day_change_pct == round(20.0 / 300.0 * 100.0, 2)


def test_a_fresh_tick_counts_even_when_the_daily_bars_are_old():
    # Production shape: yfinance still quotes the asset, so the tick carries
    # today's price and a genuine previous_close, while price_bars_1d lags far
    # behind. prev_day then points at an old bar, but only to pick an FX rate —
    # the price pair is consecutive and must not be discarded.
    ticks = [{
        "asset_id": 1,
        "tick_date": TODAY,
        "last": 4.8461,
        "previous_close": 4.8462,
    }]
    repo = _Repo([_Position(1, 1000.0, 4846.1)], _stale_asset(1, 58), ticks)

    summary = repo.get_summary(1, "u")

    assert summary.day_change == round(1000.0 * (4.8461 - 4.8462), 2)
    assert summary.day_change != 0.0


def test_a_weekend_old_price_still_counts():
    # A price three days old is a normal Monday, not a stale asset.
    repo = _Repo([_Position(1, 2.0, 120.0)], _stale_asset(1, 3), [])

    summary = repo.get_summary(1, "u")

    assert summary.day_change == 20.0          # 2 units x (60 - 50)
