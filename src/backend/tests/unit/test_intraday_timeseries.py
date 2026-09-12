from dataclasses import dataclass
from datetime import datetime

from app.repository._base import AssetMeta
from app.repository._summary import SummaryMixin


@dataclass
class _Bar:
    ts: datetime
    close: float


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _Conn:
    def __init__(self, tx_rows: list[dict]) -> None:
        self.tx_rows = tx_rows

    def execute(self, statement, params):
        sql = " ".join(str(statement).split())
        if "from transactions" in sql:
            return _Result(self.tx_rows)
        if "asset_provider_symbols" in sql:
            return _Result([
                {"asset_id": aid, "provider_symbol": f"SYM{aid}"} for aid in params["asset_ids"]
            ])
        if "from fx_rates_1d" in sql:
            return _Result([{"from_ccy": "USD", "rate": 0.50}])
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


class _FinanceClient:
    def __init__(self, bars_by_symbol: dict[str, list[_Bar]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[str] = []

    def get_intraday_bars(self, symbol, period='5d', interval='1h'):
        self.calls.append(symbol)
        return list(self.bars_by_symbol.get(symbol, []))


class _Portfolio:
    base_currency = "EUR"
    cash_balance = 0.0


class _Repo(SummaryMixin):
    """Intraday timeseries with the DB and the price provider stubbed out."""

    def __init__(self, conn: _Conn, asset_meta: dict[int, AssetMeta]) -> None:
        self.engine = _Engine(conn)
        self._asset_meta_map = asset_meta
        self.cash_calls: list[int] = []
        self.cash_call_order: list[str] = []
        self.finance_client = None

    def _get_portfolio_for_user(self, conn, portfolio_id, user_id):
        return _Portfolio()

    def _get_asset_meta(self, conn, asset_ids):
        return {aid: self._asset_meta_map[aid] for aid in asset_ids}

    def get_current_cash_balance_value(self, portfolio_id, user_id):
        # Records when the cash query runs relative to the price fetches, so the
        # ordering below is asserted rather than assumed.
        self.cash_call_order.append("cash")
        if self.finance_client is not None:
            self.cash_call_order.extend(f"fetch:{s}" for s in self.finance_client.calls)
        return 100.0


def _tx(asset_id: int, side: str, qty: float) -> dict:
    return {"asset_id": asset_id, "side": side, "quantity": qty}


def _at(hour: int) -> datetime:
    return datetime(2026, 9, 12, hour, 0, 0)


def _build(bars_by_symbol, tx_rows=None, asset_meta=None):
    tx_rows = tx_rows if tx_rows is not None else [_tx(1, "buy", 10.0)]
    asset_meta = asset_meta or {1: AssetMeta(symbol="SYM1", quote_currency="EUR")}
    repo = _Repo(_Conn(tx_rows), asset_meta)
    client = _FinanceClient(bars_by_symbol)
    repo.finance_client = client
    return repo, client


def test_intraday_reads_cash_before_fetching_prices():
    # The cash query used to run after the yfinance fan-out, so it asked the
    # connection pool for a connection after ~60s of blocking network calls.
    repo, client = _build({"SYM1": [_Bar(_at(9), 20.0)]})

    repo.get_intraday_timeseries(1, "u", client)

    assert repo.cash_call_order == ["cash"], "cash balance must be read before any price fetch"
    assert client.calls == ["SYM1"]


def test_intraday_uses_latest_price_at_or_before_each_timestamp():
    # Asset 2 has no bar at 09:00 and none before it, so it contributes nothing
    # there; from 10:00 on it holds its last close until a newer bar appears.
    repo, client = _build(
        {
            "SYM1": [_Bar(_at(9), 20.0), _Bar(_at(11), 22.0)],
            "SYM2": [_Bar(_at(10), 5.0)],
        },
        tx_rows=[_tx(1, "buy", 10.0), _tx(2, "buy", 4.0)],
        asset_meta={
            1: AssetMeta(symbol="SYM1", quote_currency="EUR"),
            2: AssetMeta(symbol="SYM2", quote_currency="EUR"),
        },
    )

    points = repo.get_intraday_timeseries(1, "u", client)

    assert [p.ts for p in points] == [
        "2026-09-12T09:00:00", "2026-09-12T10:00:00", "2026-09-12T11:00:00",
    ]
    # 09:00 - 100 cash + 10 x 20.00; asset 2 has no bar yet.
    assert points[0].market_value == 300.0
    # 10:00 - asset 1 still at its 09:00 close, asset 2 joins at 5.00.
    assert points[1].market_value == 320.0
    # 11:00 - asset 1 reprices to 22.00, asset 2 holds its 10:00 close.
    assert points[2].market_value == 340.0


def test_intraday_converts_non_base_currency_at_the_latest_rate():
    repo, client = _build(
        {"SYM1": [_Bar(_at(9), 20.0)]},
        asset_meta={1: AssetMeta(symbol="SYM1", quote_currency="USD")},
    )

    points = repo.get_intraday_timeseries(1, "u", client)

    # 100 cash + 10 units x 20.00 USD x 0.50.
    assert points[0].market_value == 200.0


def test_intraday_ignores_sold_out_positions():
    repo, client = _build(
        {"SYM1": [_Bar(_at(9), 20.0)]},
        tx_rows=[_tx(1, "buy", 10.0), _tx(1, "sell", 10.0)],
    )

    assert repo.get_intraday_timeseries(1, "u", client) == []


def test_intraday_returns_empty_without_bars():
    repo, client = _build({})

    assert repo.get_intraday_timeseries(1, "u", client) == []
