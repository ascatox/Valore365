from datetime import date, datetime

from app.repository._base import BaseRepositoryMixin, PortfolioData
from app.repository._portfolio_crud import PortfolioCrudMixin
from app.repository._utilities import UtilitiesMixin


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
    def __init__(self, portfolios: list[dict], transactions: list[dict], fx: list[dict]) -> None:
        self.portfolios = portfolios
        self.transactions = transactions
        self.fx = fx
        self.queries: list[str] = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.queries.append(sql)
        params = params or {}

        if "from portfolios" in sql:
            if "owner_user_id = :user_id" in sql and "select id, name" in sql:
                return _Result(self.portfolios)
            return _Result([p for p in self.portfolios if p["id"] == params.get("id")])

        if "from transactions" in sql:
            ids = set(params.get("portfolio_ids") or [])
            return _Result([t for t in self.transactions if t["portfolio_id"] in ids])

        if "from fx_rates_1d" in sql:
            froms = set(params.get("from_ccy") or [])
            tos = params.get("to_ccy")
            tos = set(tos) if isinstance(tos, list) else {tos}
            cutoff = params.get("max_trade_day")
            return _Result([
                r for r in self.fx
                if r["from_ccy"] in froms and r["to_ccy"] in tos and r["price_date"] <= cutoff
            ])

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
        self.begin_count = 0

    def begin(self):
        self.begin_count += 1
        return _BeginContext(self.conn)


class _Repo(PortfolioCrudMixin, UtilitiesMixin, BaseRepositoryMixin):
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn
        self.engine = _Engine(conn)


def _portfolio(pid: int, base: str, opening: float) -> dict:
    return {
        "id": pid,
        "name": f"P{pid}",
        "base_currency": base,
        "timezone": "Europe/Rome",
        "target_notional": None,
        "cash_balance": opening,
        "created_at": datetime(2025, 1, 1),
        "owner_user_id": "u",
    }


def _movement(pid: int, side: str, amount: float, ccy: str, day: date) -> dict:
    return {
        "portfolio_id": pid,
        "side": side,
        "trade_date": day,
        "quantity": 1.0,
        "price": amount,
        "fees": 0.0,
        "taxes": 0.0,
        "trade_currency": ccy,
    }


def _fixture() -> _Conn:
    # Two portfolios on different base currencies, both with a cross-currency
    # leg, so the batched FX fetch has to keep the two bases apart.
    return _Conn(
        portfolios=[_portfolio(1, "EUR", 100.0), _portfolio(2, "USD", 50.0)],
        transactions=[
            _movement(1, "deposit", 1000.0, "EUR", date(2025, 3, 1)),
            _movement(1, "deposit", 200.0, "USD", date(2025, 4, 1)),
            _movement(1, "withdrawal", 150.0, "EUR", date(2025, 5, 1)),
            _movement(2, "deposit", 500.0, "USD", date(2025, 3, 1)),
            _movement(2, "dividend", 80.0, "EUR", date(2025, 4, 1)),
            _movement(2, "fee", 10.0, "USD", date(2025, 6, 1)),
        ],
        fx=[
            {"from_ccy": "USD", "to_ccy": "EUR", "price_date": date(2025, 1, 1), "rate": 0.90},
            {"from_ccy": "EUR", "to_ccy": "USD", "price_date": date(2025, 1, 1), "rate": 1.10},
        ],
    )


def test_list_portfolios_takes_one_connection_for_all_portfolios():
    repo = _Repo(_fixture())

    listed = repo.list_portfolios("u")

    assert len(listed) == 2
    assert repo.engine.begin_count == 1, "one checkout, not one per portfolio"


def test_list_portfolios_matches_the_single_portfolio_calculation():
    listed = _Repo(_fixture()).list_portfolios("u")
    by_id = {p.id: p.current_cash_balance for p in listed}

    # Same numbers the per-portfolio path produces, each on its own repo so the
    # batched fold is compared against an independent single-portfolio fold.
    for pid in (1, 2):
        single = _Repo(_fixture()).get_current_cash_balance_value(pid, "u")
        assert by_id[pid] == single


def test_list_portfolios_converts_each_portfolio_into_its_own_base():
    listed = _Repo(_fixture()).list_portfolios("u")
    by_id = {p.id: p.current_cash_balance for p in listed}

    # Portfolio 1 (EUR): 100 opening + 1000 EUR + 200 USD x 0.90 - 150 EUR.
    assert by_id[1] == 1130.0
    # Portfolio 2 (USD): 50 opening + 500 USD + 80 EUR x 1.10 - 10 USD.
    assert by_id[2] == 628.0


def test_list_portfolios_keeps_the_stored_opening_balance_separate():
    listed = _Repo(_fixture()).list_portfolios("u")
    by_id = {p.id: p for p in listed}

    # cash_balance stays the stored column; only current_cash_balance is folded.
    assert by_id[1].cash_balance == 100.0
    assert by_id[2].cash_balance == 50.0


def test_list_portfolios_without_any_portfolio_runs_no_extra_query():
    conn = _Conn(portfolios=[], transactions=[], fx=[])
    repo = _Repo(conn)

    assert repo.list_portfolios("u") == []
    assert not any("from transactions" in q for q in conn.queries)
