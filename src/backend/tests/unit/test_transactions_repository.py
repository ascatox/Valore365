from datetime import date, timedelta

from sqlalchemy import Date

from app.repository._base import BaseRepositoryMixin
from app.repository._transactions import TransactionsMixin


class _FakeResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _FakeConn:
    def __init__(self) -> None:
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return _FakeResult()


class _BeginContext:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    def begin(self):
        return _BeginContext(self.conn)


class _Repo(TransactionsMixin):
    def __init__(self, conn: _FakeConn) -> None:
        self.engine = _FakeEngine(conn)

    def _get_portfolio_for_user(self, conn, portfolio_id: int, user_id: str):
        return {"id": portfolio_id, "owner_user_id": user_id}


def test_get_transactions_in_range_binds_nullable_dates_as_date_type():
    conn = _FakeConn()
    repo = _Repo(conn)

    rows = repo.get_transactions_in_range(1, "u", start_date=None, end_date=date(2026, 1, 31))

    assert rows == []
    assert conn.params == {
        "portfolio_id": 1,
        "start_date": None,
        "end_date": date(2026, 1, 31),
    }
    assert isinstance(conn.statement._bindparams["start_date"].type, Date)
    assert isinstance(conn.statement._bindparams["end_date"].type, Date)


# --- Batch valuation -------------------------------------------------------
#
# get_portfolio_value_at_date is now a thin delegate over
# get_portfolio_values_in_range, so comparing the two would prove nothing.
# Instead these tests compare one batch call covering every date against one
# single-date call per date: the single-date calls fetch only history up to
# their own day and fold from scratch, which is exactly what the old per-day
# implementation did. The scripted connection below honours the bound
# :target_date the way Postgres would, so the two really do differ in inputs.

_EUR = "EUR"


class _ScriptedResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _ScriptedConn:
    """Fake connection that filters canned rows by the bound parameters."""

    def __init__(self, *, cash_balance: float, transactions, assets, price_bars, fx_rates) -> None:
        self.cash_balance = cash_balance
        self.transactions = transactions
        self.assets = assets
        self.price_bars = price_bars
        self.fx_rates = fx_rates

    def execute(self, statement, params):
        sql = " ".join(str(statement).split())

        if "from portfolios" in sql:
            return _ScriptedResult([
                {"id": params["id"], "base_currency": _EUR, "cash_balance": self.cash_balance}
            ])

        if "from transactions" in sql:
            cutoff = params["target_date"]
            return _ScriptedResult([r for r in self.transactions if r["trade_date"] <= cutoff])

        if "from assets" in sql:
            ids = set(params["asset_ids"])
            return _ScriptedResult([r for r in self.assets if r["id"] in ids])

        if "from price_bars_1d" in sql:
            ids = set(params["asset_ids"])
            cutoff = params["target_date"]
            return _ScriptedResult([
                r for r in self.price_bars if r["asset_id"] in ids and r["price_date"] <= cutoff
            ])

        if "from fx_rates_1d" in sql:
            wanted = set(params["from_ccy"])
            cutoff = params["target_date"]
            return _ScriptedResult([
                r for r in self.fx_rates if r["from_ccy"] in wanted and r["price_date"] <= cutoff
            ])

        raise AssertionError(f"unexpected query: {sql}")


class _CountingEngine:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.begin_count = 0

    def begin(self):
        self.begin_count += 1
        return _BeginContext(self.conn)


class _ValuationRepo(TransactionsMixin, BaseRepositoryMixin):
    def __init__(self, conn: _ScriptedConn) -> None:
        self.engine = _CountingEngine(conn)


def _scripted_repo(**overrides) -> _ValuationRepo:
    """A portfolio with a EUR asset, a USD asset, a clamped sell and sparse prices."""
    defaults = dict(
        cash_balance=500.0,
        transactions=[
            _tx(date(2026, 1, 10), "deposit", None, qty=1000.0, price=1.0),
            _tx(date(2026, 1, 12), "buy", 1, qty=10.0, price=20.0),
            _tx(date(2026, 1, 15), "buy", 2, qty=5.0, price=30.0, ccy="USD"),
            _tx(date(2026, 1, 20), "dividend", None, qty=1.0, price=12.0),
            # Sells more of asset 1 than is held: must clamp at zero, not go negative.
            _tx(date(2026, 1, 22), "sell", 1, qty=99.0, price=25.0),
            _tx(date(2026, 1, 25), "withdrawal", None, qty=1.0, price=100.0),
        ],
        assets=[
            {"id": 1, "symbol": "AAA", "quote_currency": _EUR},
            {"id": 2, "symbol": "BBB", "quote_currency": "USD"},
        ],
        # Deliberately sparse: days in between must fall back to the last close.
        price_bars=[
            {"asset_id": 1, "price_date": date(2026, 1, 12), "close": 20.0},
            {"asset_id": 1, "price_date": date(2026, 1, 18), "close": 24.0},
            {"asset_id": 2, "price_date": date(2026, 1, 15), "close": 30.0},
            {"asset_id": 2, "price_date": date(2026, 1, 21), "close": 33.0},
            {"asset_id": 2, "price_date": date(2026, 1, 26), "close": 31.5},
        ],
        fx_rates=[
            {"from_ccy": "USD", "price_date": date(2026, 1, 14), "rate": 0.90},
            {"from_ccy": "USD", "price_date": date(2026, 1, 24), "rate": 0.95},
        ],
    )
    defaults.update(overrides)
    return _ValuationRepo(_ScriptedConn(**defaults))


def _tx(trade_date, side, asset_id, *, qty, price, ccy=_EUR):
    return {
        "asset_id": asset_id,
        "side": side,
        "trade_date": trade_date,
        "quantity": qty,
        "price": price,
        "fees": 0.0,
        "taxes": 0.0,
        "trade_currency": ccy,
    }


def _date_span(start: date, end: date) -> list[date]:
    from datetime import timedelta

    out = []
    cursor = start
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(days=1)
    return out


def test_batch_valuation_matches_one_call_per_date():
    days = _date_span(date(2026, 1, 8), date(2026, 1, 28))

    batched = _scripted_repo().get_portfolio_values_in_range(1, "u", days)
    per_date = {d: _scripted_repo().get_portfolio_value_at_date(1, "u", d) for d in days}

    assert batched == per_date
    # Guard the properties the dataset was built to exercise.
    assert batched[date(2026, 1, 8)] == 0.0                      # before the first transaction
    assert batched[date(2026, 1, 13)] == batched[date(2026, 1, 12)]  # no bar that day, holds last close
    assert batched[date(2026, 1, 23)] == batched[date(2026, 1, 22)]  # sell clamped, nothing left of asset 1


def test_batch_valuation_uses_a_single_connection():
    days = _date_span(date(2026, 1, 8), date(2026, 3, 31))
    repo = _scripted_repo()

    repo.get_portfolio_values_in_range(1, "u", days)

    assert len(days) > 80
    assert repo.engine.begin_count == 1


def test_batch_valuation_accepts_unsorted_and_duplicate_dates():
    repo = _scripted_repo()
    days = [date(2026, 1, 20), date(2026, 1, 12), date(2026, 1, 20), date(2026, 1, 16)]

    values = repo.get_portfolio_values_in_range(1, "u", days)

    assert set(values) == set(days)
    assert values == _scripted_repo().get_portfolio_values_in_range(1, "u", sorted(set(days)))


def test_batch_valuation_without_transactions_returns_cash_only_from_today():
    repo = _scripted_repo(transactions=[])
    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

    values = repo.get_portfolio_values_in_range(1, "u", [yesterday, date.today(), tomorrow])

    assert values[yesterday] == 0.0
    assert values[date.today()] == 500.0
    assert values[tomorrow] == 500.0


def test_batch_valuation_before_first_transaction_matches_empty_portfolio_rule():
    # Transactions exist, but all of them are dated after the requested days:
    # each such day must follow the same rule as a portfolio with no rows at all.
    future = date.today() + timedelta(days=30)
    repo = _scripted_repo(transactions=[_tx(future, "deposit", None, qty=1000.0, price=1.0)])
    yesterday = date.today() - timedelta(days=1)

    values = repo.get_portfolio_values_in_range(1, "u", [yesterday, date.today(), future])

    assert values[yesterday] == 0.0
    assert values[date.today()] == 500.0
    assert values[future] == 1000.0


def test_batch_valuation_returns_empty_for_no_dates():
    repo = _scripted_repo()

    assert repo.get_portfolio_values_in_range(1, "u", []) == {}
    assert repo.engine.begin_count == 0


def test_batch_valuation_clamps_oversized_sell_at_zero():
    # Selling more than is held must leave the holding at zero, not negative:
    # a later buy has to start from 0, otherwise it is silently swallowed.
    txs = [
        _tx(date(2026, 1, 12), "buy", 1, qty=10.0, price=20.0),
        _tx(date(2026, 1, 22), "sell", 1, qty=99.0, price=25.0),
        _tx(date(2026, 1, 27), "buy", 1, qty=4.0, price=24.0),
    ]
    repo = _scripted_repo(transactions=txs, cash_balance=0.0)

    values = repo.get_portfolio_values_in_range(1, "u", [date(2026, 1, 23), date(2026, 1, 27)])

    assert values[date(2026, 1, 23)] == 0.0
    # 4 units at the last close on or before 27 Jan (24.0 from 18 Jan).
    assert values[date(2026, 1, 27)] == 96.0


def test_batch_valuation_pins_absolute_values():
    # Absolute expectations, so a change in the fold itself is caught rather
    # than merely being applied consistently to both sides of an equivalence.
    values = _scripted_repo().get_portfolio_values_in_range(
        1, "u", [date(2026, 1, 12), date(2026, 1, 15), date(2026, 1, 25), date(2026, 1, 26)]
    )

    # 1000 cash deposited, 10 units of asset 1 at 20.00 EUR.
    assert values[date(2026, 1, 12)] == 1200.0
    # + 5 units of asset 2 at 30.00 USD, converted at the 14 Jan rate of 0.90.
    assert values[date(2026, 1, 15)] == 1335.0
    # After the 12.00 dividend, the clamped sell and the 100.00 withdrawal:
    # cash 912.00 + 5 units of asset 2 at 33.00 USD x 0.90.
    assert values[date(2026, 1, 25)] == 1060.5
    # 26 Jan revalues asset 2 at 31.50 USD and picks up the 24 Jan rate of 0.95.
    assert values[date(2026, 1, 26)] == 1061.62
