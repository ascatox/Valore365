"""Vista aggregata: several portfolios read as one through the repository.

The scripted connection below answers the repository's SQL from in-memory
tables, honouring the bound portfolio ids, sides and date cutoffs the way
Postgres would, so the multi-portfolio queries and the single-portfolio ones
really read different rows.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.repository import PortfolioRepository, normalize_portfolio_ids, resolve_portfolio_scope

TODAY = date.today()
D0 = TODAY - timedelta(days=30)
D1 = TODAY - timedelta(days=20)
D2 = TODAY - timedelta(days=10)
D3 = TODAY - timedelta(days=5)

USER = "u"

CASH_SIDES = {"deposit", "withdrawal", "dividend", "fee", "interest"}


class _Result:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, db: "_Db") -> None:
        self.db = db

    def execute(self, statement, params=None):
        params = params or {}
        sql = " ".join(str(statement).split())
        db = self.db

        if "from portfolios p" in sql:  # inception date
            ids = set(params["portfolio_ids"])
            rows = []
            for p in db.portfolios:
                if p["id"] in ids and p["owner_user_id"] == params["user_id"]:
                    trades = [t["trade_date"] for t in db.transactions if t["portfolio_id"] == p["id"]]
                    rows.append({
                        "id": p["id"],
                        "created_date": p["created_date"],
                        "first_trade_date": min(trades) if trades else None,
                    })
            return _Result(rows)

        if "from portfolios" in sql:
            if "portfolio_ids" in params:
                ids = set(params["portfolio_ids"])
            else:
                ids = {params["id"]}
            return _Result([
                {"id": p["id"], "base_currency": p["base_currency"], "cash_balance": p["cash_balance"]}
                for p in db.portfolios
                if p["id"] in ids and p["owner_user_id"] == params["user_id"]
            ])

        if "from transactions" in sql:
            if "portfolio_ids" in params:
                ids = set(params["portfolio_ids"])
            else:
                ids = {params["portfolio_id"]}
            rows = [t for t in db.transactions if t["portfolio_id"] in ids]
            if "side in ('buy', 'sell')" in sql:
                rows = [t for t in rows if t["side"] in {"buy", "sell"}]
            if "side in ('deposit'" in sql:
                rows = [t for t in rows if t["side"] in CASH_SIDES]
            if params.get("target_date") is not None:
                rows = [t for t in rows if t["trade_date"] <= params["target_date"]]
            if params.get("end_date") is not None:
                rows = [t for t in rows if t["trade_date"] <= params["end_date"]]
            if params.get("start_date") is not None:
                rows = [t for t in rows if t["trade_date"] >= params["start_date"]]
            rows.sort(key=lambda t: (t["trade_at"], t["id"]))
            return _Result(rows)

        if "asset_provider_symbols" in sql:
            return _Result([
                {"asset_id": a["id"], "provider_symbol": a["symbol"]}
                for a in db.assets if a["id"] in set(params["asset_ids"])
            ])

        if "from assets" in sql:
            return _Result([a for a in db.assets if a["id"] in set(params["asset_ids"])])

        if "from etf_enrichment" in sql or "from price_ticks" in sql or "from fx_rates_1d" in sql:
            return _Result([])

        if "from price_bars_1d" in sql:
            ids = set(params["asset_ids"])
            bars = sorted(
                (b for b in db.bars if b["asset_id"] in ids),
                key=lambda b: (b["asset_id"], b["price_date"]),
            )
            if "ranked_daily" in sql:
                out = []
                for aid in sorted(ids):
                    series = [b for b in bars if b["asset_id"] == aid][::-1][:2]
                    out.extend({**b, "rn": i + 1} for i, b in enumerate(series))
                return _Result(out)
            if "rn = 2" in sql:
                out = []
                for aid in sorted(ids):
                    series = [b for b in bars if b["asset_id"] == aid][::-1]
                    if len(series) >= 2:
                        out.append(series[1])
                return _Result(out)
            if "distinct on (asset_id)" in sql:
                out = []
                for aid in sorted(ids):
                    series = [b for b in bars if b["asset_id"] == aid]
                    if series:
                        out.append(series[-1])
                return _Result(out)
            cutoff = params.get("target_date") or params.get("end_date")
            return _Result([b for b in bars if cutoff is None or b["price_date"] <= cutoff])

        raise AssertionError(f"unexpected query: {sql}")


class _Begin:
    def __init__(self, conn) -> None:
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _Db:
    def __init__(self) -> None:
        self.portfolios: list[dict] = []
        self.transactions: list[dict] = []
        self.assets: list[dict] = []
        self.bars: list[dict] = []

    def begin(self):
        return _Begin(_Conn(self))

    def portfolio(self, pid: int, *, ccy: str = "EUR", owner: str = USER, cash: float = 0.0) -> None:
        self.portfolios.append({
            "id": pid, "base_currency": ccy, "cash_balance": cash,
            "owner_user_id": owner, "created_date": TODAY - timedelta(days=2),
        })

    def tx(self, pid: int, day: date, side: str, asset_id: int | None, qty: float, price: float = 1.0) -> None:
        self.transactions.append({
            "id": len(self.transactions) + 1,
            "portfolio_id": pid,
            "asset_id": asset_id,
            "side": side,
            "trade_at": datetime.combine(day, time(12), tzinfo=timezone.utc),
            "trade_date": day,
            "quantity": qty,
            "price": price,
            "fees": 0.0,
            "taxes": 0.0,
            "trade_currency": "EUR",
            "notes": None,
        })


def _repo() -> PortfolioRepository:
    """Two EUR portfolios sharing asset 10, plus a USD one and someone else's."""
    db = _Db()
    db.portfolio(1)
    db.portfolio(2)
    db.portfolio(3, ccy="USD")
    db.portfolio(4, owner="someone-else")

    db.assets = [
        {"id": 10, "symbol": "VWCE", "name": "All World", "asset_type": "etf", "quote_currency": "EUR"},
        {"id": 20, "symbol": "BND", "name": "Bonds", "asset_type": "etf", "quote_currency": "EUR"},
    ]
    for aid, closes in {10: [(D0, 40.0), (D2, 70.0), (TODAY - timedelta(days=1), 90.0), (TODAY, 100.0)],
                        20: [(D0, 20.0), (TODAY - timedelta(days=1), 25.0), (TODAY, 24.0)]}.items():
        for day, close in closes:
            db.bars.append({"asset_id": aid, "price_date": day, "close": close})

    # Portfolio 1: 10 x asset 10 @ 50, 5 x asset 20 @ 20.
    db.tx(1, D0, "deposit", None, 1000.0)
    db.tx(1, D1, "buy", 10, 10.0, 50.0)
    db.tx(1, D1, "buy", 20, 5.0, 20.0)
    # Portfolio 2: 5 @ 60 + 5 @ 100, then sells 5 -> 5 left at avg cost 80.
    db.tx(2, D0, "deposit", None, 500.0)
    db.tx(2, D1, "buy", 10, 5.0, 60.0)
    db.tx(2, D2, "buy", 10, 5.0, 100.0)
    db.tx(2, D3, "sell", 10, 5.0, 90.0)
    db.tx(2, D3, "dividend", None, 1.0, 12.0)
    # Portfolio 3 (USD) only matters for scope validation.
    db.tx(3, D1, "buy", 20, 1.0, 20.0)
    return PortfolioRepository(db)


# --- Scope ----------------------------------------------------------------


def test_normalize_drops_duplicates_and_invalid_ids_keeping_order():
    assert normalize_portfolio_ids([2, 0, 2, -1, 1, 2]) == [2, 1]


def test_scope_is_normalized_and_carries_the_base_currency():
    scope = resolve_portfolio_scope(_repo(), [2, 1, 2, 0], USER)

    assert scope.portfolio_ids == (2, 1)
    assert scope.base_currency == "EUR"
    assert scope.is_aggregate
    assert scope.cache_key == (1, 2)


def test_scope_rejects_an_empty_selection():
    with pytest.raises(ValueError, match="Seleziona almeno un portafoglio"):
        _repo().resolve_portfolio_scope([0, -3], USER)


def test_scope_rejects_mixed_base_currencies():
    with pytest.raises(ValueError, match="valuta base"):
        _repo().resolve_portfolio_scope([1, 3], USER)


def test_scope_rejects_a_portfolio_of_another_user():
    with pytest.raises(ValueError, match="Portfolio non trovato"):
        _repo().resolve_portfolio_scope([1, 4], USER)


def test_multi_reads_reject_mixed_currency_and_foreign_portfolios():
    repo = _repo()
    for read in (
        lambda ids: repo.get_positions_multi(ids, USER),
        lambda ids: repo.get_summary_multi(ids, USER),
        lambda ids: repo.get_portfolio_values_in_range_multi(ids, USER, [D3]),
        lambda ids: repo.get_external_cashflows_multi(ids, USER),
        lambda ids: repo.get_current_cash_balance_value_multi(ids, USER),
    ):
        with pytest.raises(ValueError, match="valuta base"):
            read([1, 3])
        with pytest.raises(ValueError, match="Portfolio non trovato"):
            read([1, 4])


# --- Positions --------------------------------------------------------------


def test_positions_of_the_same_asset_merge_into_one_row():
    positions = _repo().get_positions_multi([1, 2], USER)

    by_asset = {p.asset_id: p for p in positions}
    assert sorted(by_asset) == [10, 20]

    merged = by_asset[10]
    assert merged.quantity == 15.0
    # 10 @ 50 in portfolio 1 + 5 @ avg 80 in portfolio 2 -> 900 / 15.
    assert merged.avg_cost == 60.0
    assert merged.market_value == 1500.0
    assert merged.unrealized_pl == 600.0
    assert merged.first_trade_at.date() == D1

    # Weights are recomputed over the combined 1620.
    assert merged.weight == round(1500 / 1620 * 100, 2)
    assert by_asset[20].weight == round(120 / 1620 * 100, 2)
    assert [p.asset_id for p in positions] == [10, 20]  # sorted by market value


def test_merged_market_value_is_the_sum_of_the_single_portfolios():
    repo = _repo()
    singles = repo.get_positions(1, USER) + repo.get_positions(2, USER)
    merged = repo.get_positions_multi([1, 2], USER)

    assert sum(p.market_value for p in merged) == pytest.approx(sum(p.market_value for p in singles), abs=0.01)
    assert sum(p.quantity * p.avg_cost for p in merged) == pytest.approx(
        sum(p.quantity * p.avg_cost for p in singles), abs=0.01
    )


def test_one_portfolio_scope_is_exactly_the_single_portfolio_path():
    repo = _repo()

    assert repo.get_positions_multi([2, 2, 0], USER) == repo.get_positions(2, USER)
    one = repo.get_summary_multi([2], USER)
    identity = {"portfolio_id", "portfolio_ids"}
    assert one.model_dump(exclude=identity) == repo.get_summary(2, USER).model_dump(exclude=identity)
    # A list is always reported as an aggregate view, even of one portfolio.
    assert (one.portfolio_id, one.portfolio_ids) == (0, [2])
    assert repo.get_allocation_multi([1], USER) == repo.get_allocation(1, USER)


def test_single_portfolio_positions_keep_their_per_portfolio_avg_cost():
    p2 = {p.asset_id: p for p in _repo().get_positions(2, USER)}

    assert p2[10].quantity == 5.0
    assert p2[10].avg_cost == 80.0
    assert p2[10].weight == 100.0


def test_positions_multi_is_memoized_per_scope():
    repo = _repo()
    calls = []
    original = repo._compute_positions_multi

    def counting(ids, user_id, stale_days):
        calls.append(tuple(ids))
        return original(ids, user_id, stale_days)

    repo._compute_positions_multi = counting
    with repo.memoize_positions():
        repo.get_positions_multi([1, 2], USER)
        repo.get_positions_multi([2, 1], USER)
    assert len(calls) == 1


# --- Summary / allocation / performers --------------------------------------


def test_aggregated_summary_is_the_sum_of_the_single_summaries():
    repo = _repo()
    s1 = repo.get_summary(1, USER)
    s2 = repo.get_summary(2, USER)
    agg = repo.get_summary_multi([1, 2], USER)

    assert agg.base_currency == "EUR"
    assert agg.portfolio_id == 0
    assert agg.portfolio_ids == [1, 2]
    for field in ("market_value", "cost_basis", "unrealized_pl", "day_change", "cash_balance"):
        assert getattr(agg, field) == pytest.approx(getattr(s1, field) + getattr(s2, field), abs=0.02), field

    previous_value = agg.market_value - agg.day_change
    assert agg.day_change_pct == pytest.approx(agg.day_change / previous_value * 100, abs=0.01)
    assert agg.unrealized_pl_pct == pytest.approx(agg.unrealized_pl / agg.cost_basis * 100, abs=0.01)


def test_aggregated_cash_is_the_sum_of_the_balances():
    repo = _repo()

    assert repo.get_current_cash_balance_value(1, USER) == 1000.0
    assert repo.get_current_cash_balance_value(2, USER) == 512.0
    assert repo.get_current_cash_balance_value_multi([1, 2], USER) == 1512.0


def test_aggregated_allocation_weights_sum_to_100():
    allocation = _repo().get_allocation_multi([1, 2], USER)

    assert [a.asset_id for a in allocation] == [10, 20]
    assert sum(a.weight_pct for a in allocation) == pytest.approx(100.0, abs=0.02)


def test_aggregated_period_performers_list_each_asset_once():
    performers = _repo().get_period_performers_multi([1, 2], USER, 1)

    assert sorted(p.asset_id for p in performers) == [10, 20]


# --- Time series and performance inputs -------------------------------------


def test_aggregated_values_in_range_are_the_sum_of_the_single_series():
    repo = _repo()
    days = [D0 - timedelta(days=1), D0, D1, D2, D3, TODAY]
    v1 = repo.get_portfolio_values_in_range(1, USER, days)
    v2 = repo.get_portfolio_values_in_range(2, USER, days)
    agg = repo.get_portfolio_values_in_range_multi([1, 2], USER, days)

    assert agg == {d: round(v1[d] + v2[d], 2) for d in days}
    assert agg[D0] == 1500.0  # both deposits, nothing bought yet


def test_aggregated_daily_timeseries_is_the_sum_of_the_single_series():
    repo = _repo()
    t1 = repo.get_timeseries(1, "1y", "1d", USER)
    t2 = repo.get_timeseries(2, "1y", "1d", USER)
    agg = repo.get_timeseries_multi([1, 2], "1y", "1d", USER)

    assert [p.date for p in agg] == [p.date for p in t1]
    for a, x, y in zip(agg, t1, t2):
        assert a.market_value == pytest.approx(x.market_value + y.market_value, abs=0.01)
    assert agg[-1].market_value == 1620.0


@dataclass
class _Bar:
    ts: datetime
    close: float


class _FinanceClient:
    def get_intraday_bars(self, symbol, period="1d", interval="1h"):
        price = {"VWCE": 100.0, "BND": 24.0}[symbol]
        return [_Bar(datetime(2026, 9, 12, 10), price)]


def test_aggregated_intraday_value_combines_holdings_and_cash():
    repo = _repo()
    client = _FinanceClient()
    i1 = repo.get_intraday_timeseries(1, USER, client)
    i2 = repo.get_intraday_timeseries(2, USER, client)
    agg = repo.get_intraday_timeseries_multi([1, 2], USER, client)

    assert len(agg) == 1
    assert agg[0].market_value == pytest.approx(i1[0].market_value + i2[0].market_value, abs=0.01)
    assert agg[0].market_value == 1620.0 + 1512.0


def test_aggregated_cashflows_merge_in_date_order():
    repo = _repo()
    flows = repo.get_external_cashflows_multi([1, 2], USER, include_trades=False)

    assert [(f.date, f.side, f.amount) for f in flows] == [
        (D0.isoformat(), "deposit", 1000.0),
        (D0.isoformat(), "deposit", 500.0),
        (D3.isoformat(), "dividend", 12.0),
    ]

    by_portfolio = repo.get_external_cashflows_by_portfolio([1, 2], USER, start_date=D1, include_trades=True)
    assert [f.side for f in by_portfolio[1]] == ["buy", "buy"]
    assert [f.side for f in by_portfolio[2]] == ["buy", "buy", "sell", "dividend"]


def test_single_portfolio_cashflows_are_unchanged():
    flows = _repo().get_external_cashflows(2, USER, start_date=D2, include_trades=True)

    assert [(f.side, f.amount) for f in flows] == [("buy", 500.0), ("sell", -450.0), ("dividend", 12.0)]


def test_aggregated_inception_is_the_earliest_portfolio_start():
    repo = _repo()
    repo.engine.portfolios.append({
        "id": 5, "base_currency": "EUR", "cash_balance": 0.0,
        "owner_user_id": USER, "created_date": TODAY - timedelta(days=1),
    })

    assert repo.get_portfolio_inception_date(5, USER) == TODAY - timedelta(days=1)
    assert repo.get_portfolio_inception_date_multi([5, 2], USER) == D0
    with pytest.raises(ValueError, match="Portfolio non trovato"):
        repo.get_portfolio_inception_date_multi([1, 4], USER)
