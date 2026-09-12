from datetime import UTC, datetime

from app.repository._search_pricing import SearchPricingMixin


class _Conn:
    def __init__(self) -> None:
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return None


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


class _Repo(SearchPricingMixin):
    def __init__(self) -> None:
        self.conn = _Conn()
        self.engine = _Engine(self.conn)


def _tick(asset_id: int, **overrides) -> dict:
    tick = {
        "asset_id": asset_id,
        "provider": "YFinance",
        "ts": datetime.now(UTC),
        "last": 10.0 + asset_id,
        "bid": None,
        "ask": None,
        "volume": None,
        "previous_close": None,
    }
    tick.update(overrides)
    return tick


def test_save_price_ticks_uses_one_transaction_for_the_whole_batch():
    repo = _Repo()

    repo.save_price_ticks([_tick(i) for i in range(1, 34)])

    assert repo.engine.begin_count == 1
    assert isinstance(repo.conn.params, list)
    assert len(repo.conn.params) == 33


def test_save_price_ticks_upserts_so_a_repeated_market_timestamp_is_not_fatal():
    # yfinance reports the market timestamp, so an unmoved quote repeats the
    # (asset_id, provider, ts) primary key on the next poll.
    repo = _Repo()

    repo.save_price_ticks([_tick(1)])

    sql = " ".join(str(repo.conn.statement).split())
    assert "on conflict (asset_id, provider, ts)" in sql
    assert "do update set" in sql


def test_save_price_ticks_normalizes_the_provider():
    repo = _Repo()

    repo.save_price_ticks([_tick(1, provider="  YFinance  ")])

    assert repo.conn.params[0]["provider"] == "yfinance"


def test_save_price_ticks_with_no_ticks_takes_no_connection():
    repo = _Repo()

    repo.save_price_ticks([])

    assert repo.engine.begin_count == 0


def test_save_price_tick_still_writes_a_single_tick():
    repo = _Repo()
    ts = datetime.now(UTC)

    repo.save_price_tick(
        asset_id=7, provider="yfinance", ts=ts, last=42.0,
        bid=41.0, ask=43.0, volume=100.0, previous_close=40.0,
    )

    assert repo.engine.begin_count == 1
    assert repo.conn.params == [{
        "asset_id": 7, "provider": "yfinance", "ts": ts, "last": 42.0,
        "bid": 41.0, "ask": 43.0, "volume": 100.0, "previous_close": 40.0,
    }]
