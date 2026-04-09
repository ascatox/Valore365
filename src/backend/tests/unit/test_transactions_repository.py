from datetime import date

from sqlalchemy import Date

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
