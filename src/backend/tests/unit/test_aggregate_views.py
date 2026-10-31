"""Vista aggregata (TASK-26): repository and Doctor pieces behind the aggregate routes."""

from datetime import datetime, timezone

import pytest

from app.models import Position
from app.repository import PortfolioRepository
from app.repository._scope import MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE, PortfolioScope
from app.services.portfolio_doctor import run_monte_carlo_projection, run_stress_test
from app.services.portfolio_doctor._holdings import (
    AnalyzedHolding,
    _load_aggregate_holdings,
    _load_holdings,
    _merge_holdings_by_asset,
    resolve_doctor_scope,
)

USER = "u"
PORTFOLIOS = [
    {"id": 1, "name": "Pensione", "base_currency": "EUR", "cash_balance": 0.0, "owner_user_id": USER},
    {"id": 2, "name": "Trading", "base_currency": "EUR", "cash_balance": 0.0, "owner_user_id": USER},
    {"id": 3, "name": "Dollari", "base_currency": "USD", "cash_balance": 0.0, "owner_user_id": USER},
]
TRANSACTIONS = [
    {"id": 1, "portfolio_id": 1, "trade_at": datetime(2026, 1, 5, tzinfo=timezone.utc)},
    {"id": 2, "portfolio_id": 2, "trade_at": datetime(2026, 3, 1, tzinfo=timezone.utc)},
    {"id": 3, "portfolio_id": 1, "trade_at": datetime(2026, 3, 1, tzinfo=timezone.utc)},
    {"id": 4, "portfolio_id": 3, "trade_at": datetime(2026, 4, 1, tzinfo=timezone.utc)},
]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self):
        self.statements: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        params = params or {}
        sql = " ".join(str(statement).split())
        self.statements.append((sql, params))
        if "from transactions t" in sql:
            ids = set(params["portfolio_ids"])
            names = {p["id"]: p["name"] for p in PORTFOLIOS}
            rows = [
                {
                    "id": t["id"], "portfolio_id": t["portfolio_id"], "portfolio_name": names[t["portfolio_id"]],
                    "asset_id": 10, "side": "buy", "trade_at": t["trade_at"], "quantity": 1.0, "price": 10.0,
                    "fees": 0.0, "taxes": 0.0, "trade_currency": "EUR", "notes": None, "symbol": "VWCE",
                    "asset_name": "Vanguard All-World",
                }
                for t in TRANSACTIONS
                if t["portfolio_id"] in ids
            ]
            rows.sort(key=lambda r: (r["trade_at"], r["id"]), reverse=True)
            return _Result(rows)
        if "from portfolios" in sql:
            ids = set(params.get("portfolio_ids") or [params.get("id")])
            return _Result([
                {"id": p["id"], "base_currency": p["base_currency"], "cash_balance": p["cash_balance"]}
                for p in PORTFOLIOS
                if p["id"] in ids and p["owner_user_id"] == params["user_id"]
            ])
        if "portfolio_target_allocations" in sql:
            return _Result([
                {"asset_id": 10, "symbol": "VWCE", "name": "Vanguard All-World", "bar_count": 252,
                 "first_bar": None, "last_bar": None},
            ])
        return _Result([])


class _Begin:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


class _Engine:
    def __init__(self):
        self.conn = _Conn()

    def begin(self):
        return _Begin(self.conn)


def _repo() -> PortfolioRepository:
    return PortfolioRepository(_Engine())


# --- Aggregated transactions -------------------------------------------------------


def test_aggregated_transactions_are_newest_first_and_name_their_portfolio():
    rows = _repo().list_transactions_multi([1, 2], USER)

    assert [(r.id, r.portfolio_id, r.portfolio_name) for r in rows] == [
        (3, 1, "Pensione"),
        (2, 2, "Trading"),
        (1, 1, "Pensione"),
    ]
    assert rows[0].symbol == "VWCE"


def test_aggregated_transactions_validate_the_scope():
    with pytest.raises(ValueError, match=MIXED_CURRENCY_MESSAGE):
        _repo().list_transactions_multi([1, 3], USER)
    with pytest.raises(ValueError, match=NOT_FOUND_MESSAGE):
        _repo().list_transactions_multi([1, 42], "someone-else")


def test_aggregated_transactions_query_reads_the_portfolio_name():
    repo = _repo()
    repo.list_transactions_multi([2, 1], USER)

    sql, params = repo.engine.conn.statements[-1]
    assert "p.name as portfolio_name" in sql
    assert "order by t.trade_at desc, t.id desc" in sql
    assert params == {"portfolio_ids": [2, 1]}


def test_aggregated_price_coverage_lists_each_targeted_asset_once():
    repo = _repo()

    items = repo.get_price_coverage_multi([1, 2], USER, days=365)

    sql, params = repo.engine.conn.statements[-1]
    assert "select distinct asset_id from portfolio_target_allocations" in sql
    assert params == {"portfolio_ids": [1, 2], "days": 365}
    assert items[0]["expected_bars"] == 252
    assert items[0]["coverage_pct"] == 100.0


# --- Doctor: merged holdings ----------------------------------------------------------


def _position(asset_id: int, symbol: str, value: float, weight: float) -> Position:
    return Position(
        asset_id=asset_id, symbol=symbol, name=f"{symbol} ETF", quantity=1, avg_cost=value, market_price=value,
        market_value=value, unrealized_pl=0, unrealized_pl_pct=0, weight=weight,
    )


class _DoctorRepo:
    """Positions per portfolio; get_positions_multi lists them without merging."""

    def __init__(self):
        self.engine = _Engine()
        self.positions = {
            1: [_position(10, "VWCE", 600, 60), _position(11, "AGGH", 400, 40)],
            2: [_position(10, "VWCE", 300, 75), _position(12, "SGLD", 100, 25)],
        }
        self.multi_calls = []

    def resolve_portfolio_scope(self, ids, user_id):
        ids = [i for i in dict.fromkeys(ids) if i > 0]
        if any(i not in self.positions for i in ids):
            raise ValueError(NOT_FOUND_MESSAGE)
        return PortfolioScope(portfolio_ids=tuple(ids), base_currency="EUR")

    def get_positions(self, portfolio_id, user_id):
        if portfolio_id not in self.positions:
            raise ValueError(NOT_FOUND_MESSAGE)
        return self.positions[portfolio_id]

    def get_positions_multi(self, ids, user_id):
        self.multi_calls.append(list(ids))
        return [p for pid in ids for p in self.positions[pid]]


def test_aggregate_doctor_holdings_merge_the_same_asset_across_portfolios():
    repo = _DoctorRepo()

    holdings = _load_aggregate_holdings(repo, [1, 2], USER)

    by_asset = {h.asset_id: h for h in holdings}
    assert len(holdings) == 3
    assert by_asset[10].market_value == pytest.approx(900)
    assert by_asset[10].weight_pct == pytest.approx(900 / 1400 * 100)
    assert sum(h.weight_pct for h in holdings) == pytest.approx(100)
    assert repo.multi_calls == [[1, 2]]


def test_single_portfolio_doctor_holdings_are_unchanged():
    holdings = _load_holdings(_DoctorRepo(), 1, USER)

    assert [(h.asset_id, h.market_value, h.weight_pct) for h in holdings] == [(10, 600, 60), (11, 400, 40)]


def test_merge_holdings_keeps_first_occurrence_and_sums_values():
    a = AnalyzedHolding(10, "VWCE", "VWCE ETF", "etf", "EUR", 100, 10)
    b = AnalyzedHolding(11, "AGGH", "AGGH ETF", "etf", "EUR", 50, 5)
    c = AnalyzedHolding(10, "VWCE", "VWCE ETF", "etf", "EUR", 30, 3)

    merged = _merge_holdings_by_asset([a, b, c])

    assert [(h.asset_id, h.market_value, h.weight_pct) for h in merged] == [(10, 130, 13), (11, 50, 5)]
    assert a.market_value == 100  # inputs are not mutated


def test_doctor_scope_identity():
    repo = _DoctorRepo()

    assert resolve_doctor_scope(repo, 2, USER) == (2, {"portfolio_id": 2, "portfolio_ids": None})
    assert resolve_doctor_scope(repo, [2, 1, 2], USER) == ([2, 1], {"portfolio_id": 0, "portfolio_ids": [2, 1]})
    with pytest.raises(ValueError, match=NOT_FOUND_MESSAGE):
        resolve_doctor_scope(repo, [1, 7], USER)


def test_doctor_services_mark_aggregate_responses():
    repo = _DoctorRepo()

    # No price history in the fake engine: both return their empty shape,
    # marked as an aggregate of the selected portfolios.
    monte_carlo = run_monte_carlo_projection(repo, [1, 2], USER)
    assert (monte_carlo.portfolio_id, monte_carlo.portfolio_ids) == (0, [1, 2])

    stress = run_stress_test(repo, [1, 2], USER)
    assert (stress.portfolio_id, stress.portfolio_ids) == (0, [1, 2])
    assert {s.scenario_id for s in stress.scenarios}  # shock scenarios still run on merged holdings

    single = run_monte_carlo_projection(repo, 1, USER)
    assert (single.portfolio_id, single.portfolio_ids) == (1, None)
