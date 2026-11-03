"""TASK-53: daily bars job, session-based stale prices, repeated provider timestamps.

Production case: XAD1.DE (Xetra) stuck at the 30/10/2026 close with no error in
the logs, while every other asset had the 02/11 bar.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.repository._positions as positions_mod
import app.services.historical_service as hist_mod
import app.services.pricing_service as pricing_mod
from app import copilot_tools
from app.finance_client import ProviderDailyBar
from app.models import Position, PriceRefreshResponse
from app.price_validation import assess_price_freshness
from app.repository._base import PricingAsset
from app.scheduler import PriceRefreshScheduler
from app.services.historical_service import HistoricalIngestionService
from app.services.market_hours import (
    completed_sessions_after,
    is_trading_day,
    market_holidays,
)
from app.services.pricing_service import PriceIngestionService


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


# --- market calendar ------------------------------------------------------------


def test_holidays_cover_easter_christmas_and_nyse_days():
    eu = market_holidays("Europe/Berlin", 2026)
    # Easter 2026 is 5 April: Good Friday 3/4 and Easter Monday 6/4.
    assert {date(2026, 4, 3), date(2026, 4, 6), date(2026, 12, 24), date(2026, 12, 25)} <= eu
    us = market_holidays("America/New_York", 2026)
    assert date(2026, 11, 26) in us  # Thanksgiving
    assert date(2026, 7, 3) in us  # 4 July on Saturday -> Friday
    assert date(2026, 4, 3) in us  # Good Friday
    assert not is_trading_day("XAD1.DE", date(2026, 12, 25))
    assert not is_trading_day("XAD1.DE", date(2026, 10, 31))  # Saturday
    assert is_trading_day("XAD1.DE", date(2026, 11, 26))  # US holiday only
    assert is_trading_day("BTC-USD", date(2026, 12, 25))


@pytest.mark.parametrize(
    ("last_day", "now", "expected"),
    [
        # Friday bar: Monday morning nothing missed, Monday after the close one.
        (date(2026, 10, 30), "2026-11-02 08:00", 0),
        (date(2026, 10, 30), "2026-11-02 17:00", 1),
        # XAD1.DE on 03/11: at 13:16 UTC only Monday is closed; after 16:30 UTC two.
        (date(2026, 10, 30), "2026-11-03 13:16", 1),
        (date(2026, 10, 30), "2026-11-03 18:00", 2),
        # Over the weekend nothing new closes.
        (date(2026, 10, 30), "2026-11-01 20:00", 0),
        # Christmas: 24, 25, 26 (and the weekend) are not sessions.
        (date(2026, 12, 23), "2026-12-28 10:00", 0),
        (date(2026, 12, 23), "2026-12-28 20:00", 1),
    ],
)
def test_completed_sessions_after_follows_the_xetra_calendar(last_day, now, expected):
    assert completed_sessions_after("XAD1.DE", last_day, _utc(now)) == expected


# --- stale price -----------------------------------------------------------------


def test_price_is_stale_after_two_sessions_with_an_italian_reason(caplog):
    with caplog.at_level(logging.WARNING, logger="app.price_validation"):
        fresh = assess_price_freshness(
            asset_id=120, symbol="XAD1", market_symbol="XAD1.DE",
            price_date=date(2026, 10, 30), now=_utc("2026-11-03 13:16"),
        )
        stale = assess_price_freshness(
            asset_id=120, symbol="XAD1", market_symbol="XAD1.DE",
            price_date=date(2026, 10, 30), now=_utc("2026-11-03 18:00"),
        )

    assert (fresh.stale, fresh.missed_sessions, fresh.reason) == (False, 1, None)
    assert stale.stale and stale.missed_sessions == 2
    assert stale.reason == "ultima quotazione del 30/10, 2 sedute fa"
    assert "price_stale asset_id=120 symbol=XAD1 market_symbol=XAD1.DE" in caplog.text


def test_price_is_not_stale_over_a_weekend_or_holidays():
    # Friday close read on Sunday and on Monday morning.
    for now in ("2026-11-01 12:00", "2026-11-02 08:00"):
        result = assess_price_freshness(
            asset_id=1, symbol="VWCE", market_symbol="VWCE.MI", price_date=date(2026, 10, 30), now=_utc(now),
        )
        assert not result.stale
    # Wednesday 23/12 close read on Monday 28/12 evening: one session (28/12).
    result = assess_price_freshness(
        asset_id=1, symbol="VWCE", market_symbol="VWCE.MI", price_date=date(2026, 12, 23), now=_utc("2026-12-28 20:00"),
    )
    assert (result.stale, result.missed_sessions) == (False, 1)


def test_illiquid_asset_with_old_close_is_stale_and_missing_price_has_a_reason():
    old = assess_price_freshness(
        asset_id=2, symbol="ILLQ", market_symbol="ILLQ.MI", price_date=date(2025, 12, 1), now=_utc("2026-11-03 18:00"),
    )
    assert old.stale and old.reason.startswith("ultima quotazione del 01/12/2025, ")
    missing = assess_price_freshness(
        asset_id=3, symbol="NEW", market_symbol=None, price_date=None, now=_utc("2026-11-03 18:00"),
    )
    assert missing.stale and missing.reason == "nessuna quotazione giornaliera disponibile"


# --- get_positions (repository) --------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self.fetchone()


class _Conn:
    """Answers the get_positions queries for one EUR portfolio holding XAD1 and VWCE."""

    TICK_TS = _utc("2026-11-02 20:38")

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split()).lower()
        params = params or {}
        if "from portfolios" in sql:
            return _Result([{"id": 26, "base_currency": "EUR", "cash_balance": 0.0}])
        if "from transactions" in sql:
            return _Result([
                {"portfolio_id": 26, "asset_id": aid, "side": "buy",
                 "trade_at": datetime(2026, 1, 5, 12, tzinfo=UTC), "trade_date": date(2026, 1, 5),
                 "quantity": 1.0, "price": 100.0, "fees": 0.0, "taxes": 0.0, "trade_currency": "EUR"}
                for aid in (120, 7)
            ])
        if "asset_provider_symbols" in sql:
            return _Result([{"asset_id": 120, "provider_symbol": "XAD1.DE"}, {"asset_id": 7, "provider_symbol": "VWCE.MI"}])
        if "from assets" in sql:
            return _Result([
                {"id": 120, "symbol": "XAD1", "name": "Gold ETC", "asset_type": "etf", "quote_currency": "EUR"},
                {"id": 7, "symbol": "VWCE", "name": "All World", "asset_type": "etf", "quote_currency": "EUR"},
            ])
        if "from price_ticks" in sql:
            return _Result([{"asset_id": 120, "tick_ts": self.TICK_TS, "tick_date": self.TICK_TS.date(),
                             "last": 220.8, "previous_close": 220.1}])
        if "from etf_enrichment" in sql or "from fx_rates_1d" in sql:
            return _Result([])
        if "from price_bars_1d" in sql:
            if "rn = 2" in sql:
                return _Result([])
            return _Result([
                {"asset_id": 120, "price_date": date(2026, 10, 30), "close": 220.8},
                {"asset_id": 7, "price_date": date(2026, 11, 3), "close": 140.0},
            ])
        raise AssertionError(f"unexpected query: {sql}")


class _Engine:
    def begin(self):
        conn = _Conn()

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


def test_get_positions_marks_the_stuck_xetra_listing_stale(monkeypatch):
    from app.repository import PortfolioRepository

    monkeypatch.setattr(positions_mod, "_utcnow", lambda: _utc("2026-11-03 18:00"))
    positions = {p.symbol: p for p in PortfolioRepository(_Engine()).get_positions(26, "u")}

    xad1 = positions["XAD1"]
    assert xad1.price_stale is True
    assert xad1.price_date == date(2026, 10, 30)
    assert xad1.stale_reason == "ultima quotazione del 30/10, 2 sedute fa"
    assert xad1.last_price_at == _Conn.TICK_TS
    vwce = positions["VWCE"]
    assert (vwce.price_stale, vwce.stale_reason, vwce.last_price_at) == (False, None, None)


# --- copilot / MCP outputs -------------------------------------------------------


def _pos(symbol: str, change: float, *, stale: bool = False, reason: str | None = None) -> Position:
    return Position(
        asset_id=abs(hash(symbol)) % 1000, symbol=symbol, name=symbol, quantity=1, avg_cost=100,
        market_price=100, market_value=100, unrealized_pl=0, unrealized_pl_pct=0, weight=50,
        day_change_pct=change, previous_close_available=True, price_stale=stale,
        price_date=date(2026, 10, 30) if stale else date(2026, 11, 3), stale_reason=reason,
        last_price_at=_utc("2026-11-02 20:38") if stale else None,
    )


REASON = "ultima quotazione del 30/10, 2 sedute fa"


def test_get_positions_tool_shows_stale_reason_and_note():
    repo = MagicMock()
    repo.get_positions.return_value = [_pos("XAD1", 0.3, stale=True, reason=REASON), _pos("VWCE", 1.0)]

    out = copilot_tools._get_positions({}, repo, MagicMock(), 26, "u")

    rows = {r["symbol"]: r for r in out["positions"]}
    assert rows["XAD1"]["price_stale"] is True
    assert rows["XAD1"]["stale_reason"] == REASON
    assert rows["XAD1"]["price_date"] == "2026-10-30"
    assert rows["XAD1"]["last_price_at"] == "2026-11-02T20:38:00+00:00"
    assert rows["VWCE"]["stale_reason"] is None
    assert "Quotazione ferma per XAD1" in out["data_quality_note"]


def test_get_day_movers_lists_the_stale_positions_with_their_reason():
    repo = MagicMock()
    repo.get_positions.return_value = [_pos("XAD1", 9.0, stale=True, reason=REASON), _pos("VWCE", 1.0)]

    out = copilot_tools._get_day_movers({}, repo, MagicMock(), 26, "u")

    assert out["best"]["symbol"] == "VWCE"
    assert out["excluded_stale"] == 1
    assert out["stale_positions"] == [{"symbol": "XAD1", "price_date": "2026-10-30", "stale_reason": REASON}]


def test_summary_flags_list_stale_price_symbols():
    out = copilot_tools.summary_data_flags(SimpleNamespace(
        fx_missing_currencies=[], price_fallback_symbols=[], stale_price_symbols=["XAD1"],
    ))
    assert out["stale_price_symbols"] == ["XAD1"]
    assert "Quotazione ferma per XAD1" in out["data_quality_note"]
    assert copilot_tools.summary_data_flags(SimpleNamespace())["stale_price_symbols"] == []


# --- daily bars job ----------------------------------------------------------------


class _BarsRepo:
    def __init__(self, assets, latest):
        self.assets = assets
        self.latest = latest
        self.writes: dict[int, list[dict]] = {}
        self.calls: list[str] = []

    def get_held_assets_for_daily_bars(self, provider):
        self.calls.append(f"held:{provider}")
        return self.assets

    def get_latest_daily_bars(self, asset_ids):
        self.calls.append("latest")
        return {aid: v for aid, v in self.latest.items() if aid in asset_ids}

    def batch_upsert_price_bars_1d(self, *, asset_id, provider, rows):
        self.writes[asset_id] = rows

    def get_asset(self, asset_id):  # ISIN fallback lookup: no ISIN here
        return SimpleNamespace(isin=None)


class _BarsClient:
    def __init__(self, bars_by_symbol):
        self.bars_by_symbol = bars_by_symbol
        self.requests: list[tuple] = []

    def get_daily_bars(self, symbol, outputsize=365, *, start_date=None, end_date=None, **_kw):
        self.requests.append((symbol, start_date, end_date))
        bars = self.bars_by_symbol[symbol]
        if isinstance(bars, Exception):
            raise bars
        return bars


def _bar(day: date, close: float) -> ProviderDailyBar:
    return ProviderDailyBar(day=day, open=close, high=close, low=close, close=close, volume=1000.0)


def _days(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def _settings(**overrides):
    values = dict(
        finance_provider="yfinance", price_backfill_max_workers=4,
        price_validation_max_daily_change_pct=50.0, price_validation_max_ohlc_spread_pct=100.0,
        price_validation_ohlc_range_tolerance_pct=2.0,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_daily_bars_job_backfills_held_assets_with_the_lookback_window(monkeypatch, caplog):
    now = _utc("2026-11-03 22:30")
    window = list(_days(date(2026, 10, 25), date(2026, 11, 3)))
    assets = [
        PricingAsset(asset_id=7, symbol="VWCE", provider_symbol="VWCE.MI", market_symbol="VWCE.MI"),
        PricingAsset(asset_id=120, symbol="XAD1", provider_symbol="XAD1.DE", market_symbol="XAD1.DE"),
        PricingAsset(asset_id=9, symbol="AAPL", provider_symbol="AAPL", market_symbol="AAPL"),
    ]
    client = _BarsClient({
        "VWCE.MI": [_bar(d, 140.0) for d in window],
        # Provider history stuck on 30/10 (the XAD1.DE case).
        "XAD1.DE": [_bar(d, 220.8) for d in window if d <= date(2026, 10, 30)],
        "AAPL": ValueError("boom"),
    })
    monkeypatch.setattr(hist_mod, "make_finance_client", lambda _s: client)
    repo = _BarsRepo(assets, {7: (date(2026, 11, 2), 139.0), 120: (date(2026, 10, 30), 220.8), 9: (date(2026, 11, 2), 270.0)})

    with caplog.at_level(logging.INFO):
        result = HistoricalIngestionService(_settings(), repo).refresh_recent_daily_bars(days=10, now=now)

    assert repo.calls[:2] == ["held:yfinance", "latest"]
    # Today's close is included: Yahoo's end bound is exclusive, so tomorrow is asked.
    assert {r[1:] for r in client.requests} == {("2026-10-25", "2026-11-04")}
    assert max(r["price_date"] for r in repo.writes[7]) == date(2026, 11, 3)
    assert (result.requested, result.updated, result.lagging, result.failed) == (3, ["VWCE.MI"], ["XAD1.DE"], ["AAPL"])
    assert "daily_bars_no_new_bar context=daily_job asset_id=120 symbol=XAD1 provider_symbol=XAD1.DE last_bar=2026-10-30 missed_sessions=2" in caplog.text
    assert "daily_bars_failed context=daily_job asset_id=9 symbol=AAPL" in caplog.text


def test_daily_bars_job_on_a_holiday_does_not_report_lagging(monkeypatch, caplog):
    # Friday 25/12/2026: Xetra closed, the 24/12 is a holiday too, last bar 23/12.
    now = _utc("2026-12-25 22:30")
    assets = [PricingAsset(asset_id=120, symbol="XAD1", provider_symbol="XAD1.DE", market_symbol="XAD1.DE")]
    window = [d for d in _days(date(2026, 12, 16), date(2026, 12, 23))]
    client = _BarsClient({"XAD1.DE": [_bar(d, 220.0) for d in window]})
    monkeypatch.setattr(hist_mod, "make_finance_client", lambda _s: client)
    repo = _BarsRepo(assets, {120: (date(2026, 12, 23), 220.0)})

    with caplog.at_level(logging.WARNING):
        result = HistoricalIngestionService(_settings(), repo).refresh_recent_daily_bars(days=10, now=now)

    assert (result.updated, result.no_new_bar, result.lagging) == ([], ["XAD1.DE"], [])
    assert "daily_bars_no_new_bar" not in caplog.text


def test_scheduler_registers_the_daily_bars_job_mon_fri_and_runs_it(caplog):
    historical = MagicMock()
    historical.refresh_recent_daily_bars.return_value = hist_mod.DailyBarsJobResult(
        requested=2, updated=["VWCE.MI"], lagging=["XAD1.DE"],
    )
    settings = SimpleNamespace(
        price_scheduler_enabled=False, price_scheduler_interval_seconds=60, price_scheduler_portfolio_id=None,
        pac_scheduler_enabled=False, pac_execution_hour=8,
        daily_bars_scheduler_enabled=True, daily_bars_scheduler_hour=22, daily_bars_scheduler_minute=30,
        daily_bars_lookback_days=10,
    )
    scheduler = PriceRefreshScheduler(settings, MagicMock(), None, historical, MagicMock())
    scheduler.start()
    try:
        job = scheduler._scheduler.get_job("daily_bars")
        assert job is not None
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert (fields["day_of_week"], fields["hour"], fields["minute"]) == ("mon-fri", "22", "30")
    finally:
        scheduler.shutdown()

    with caplog.at_level(logging.INFO, logger="app.scheduler"):
        scheduler._run_daily_bars()
    historical.refresh_recent_daily_bars.assert_called_once_with(days=10)
    assert "Daily bars job completed lookback_days=10 requested=2 updated=1" in caplog.text
    assert "lagging_symbols=XAD1.DE" in caplog.text


def test_daily_bars_job_follows_the_price_scheduler_when_unset():
    settings = SimpleNamespace(price_scheduler_enabled=False, daily_bars_scheduler_enabled=None)
    assert PriceRefreshScheduler(settings, MagicMock())._daily_bars_enabled() is False
    settings.price_scheduler_enabled = True
    assert PriceRefreshScheduler(settings, MagicMock())._daily_bars_enabled() is True
    settings.daily_bars_scheduler_enabled = False
    assert PriceRefreshScheduler(settings, MagicMock())._daily_bars_enabled() is False


def test_backfill_daily_logs_assets_without_new_bars(monkeypatch, caplog):
    # The manual backfill (after each refresh) stored nothing new for XAD1.DE
    # and logged nothing: now it says so, with the symbol.
    asset = PricingAsset(asset_id=120, symbol="XAD1", provider_symbol="XAD1.DE", market_symbol="XAD1.DE")
    repo = MagicMock()
    repo.get_assets_for_price_refresh.return_value = [asset]
    repo.get_portfolio_base_currency.return_value = "EUR"
    repo.get_quote_currencies_for_assets.return_value = {120: "EUR"}
    repo.get_latest_daily_bars.return_value = {120: (date(2026, 10, 30), 220.8)}
    repo.get_latest_close_price.return_value = 220.8
    today = date.today()
    stuck = [_bar(d, 220.8) for d in _days(today - timedelta(days=60), today - timedelta(days=5))]
    monkeypatch.setattr(hist_mod, "make_finance_client", lambda _s: _BarsClient({"XAD1.DE": stuck}))
    repo.get_latest_daily_bars.return_value = {120: (stuck[-1].day, 220.8)}

    with caplog.at_level(logging.WARNING):
        HistoricalIngestionService(_settings(), repo).backfill_daily(portfolio_id=26, days=60, asset_scope="all")

    assert "daily_bars_no_new_bar context=backfill_daily asset_id=120 symbol=XAD1 provider_symbol=XAD1.DE" in caplog.text


# --- repeated provider timestamp ---------------------------------------------------


class _TickRepo:
    def __init__(self, stored_ts):
        self.stored_ts = stored_ts
        self.saved = []

    def get_assets_for_price_refresh(self, **_kw):
        return [PricingAsset(asset_id=120, symbol="XAD1", provider_symbol="XAD1.DE", market_symbol="XAD1.DE")]

    def get_latest_tick_ts(self, asset_ids, provider):
        return {120: self.stored_ts}

    def save_price_ticks(self, ticks):
        self.saved.extend(ticks)


class _QuoteClient:
    def __init__(self, ts):
        self.ts = ts

    def get_quote(self, symbol):
        return SimpleNamespace(price=220.8, ts=self.ts, bid=None, ask=None, volume=None, previous_close=220.1,
                               source="history_close", is_realtime=False, is_fallback=True, stale=True, warning=None)


def _pricing_settings(**overrides):
    values = dict(finance_provider="yfinance", finance_symbol_request_delay_seconds=0.0, finance_quote_concurrency=1,
                  price_validation_min_price=0.0001, price_scheduler_after_close_grace_minutes=30,
                  price_unchanged_ts_warn_after=3)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_repeated_provider_ts_with_open_market_is_counted_and_warned_once_per_day(monkeypatch, caplog):
    stuck_ts = _utc("2026-10-29 23:00")  # midnight Berlin of the 30/10 bar
    monkeypatch.setattr(pricing_mod, "make_finance_client", lambda _s: _QuoteClient(stuck_ts))
    repo = _TickRepo(stuck_ts)
    service = PriceIngestionService(_pricing_settings(), repo)
    market_open = _utc("2026-11-03 13:16")

    with caplog.at_level(logging.WARNING, logger="app.services.pricing_service"):
        first = service.refresh_prices(market_hours_at=market_open)
        second = service.refresh_prices(market_hours_at=market_open + timedelta(minutes=1))

    assert first.unchanged_ts_symbols == ["XAD1.DE"] and second.unchanged_ts_symbols == ["XAD1.DE"]
    assert caplog.text.count("price_unchanged_ts asset_id=120 symbol=XAD1.DE") == 1
    assert "ts=2026-10-29T23:00:00+00:00" in caplog.text
    # The upsert itself is unchanged: the tick is still written.
    assert len(repo.saved) == 2


def test_repeated_ts_with_closed_market_needs_k_consecutive_refreshes(monkeypatch):
    stuck_ts = _utc("2026-10-30 16:30")
    monkeypatch.setattr(pricing_mod, "make_finance_client", lambda _s: _QuoteClient(stuck_ts))
    service = PriceIngestionService(_pricing_settings(), _TickRepo(stuck_ts))
    evening = _utc("2026-11-03 21:00")  # Xetra closed: manual refreshes

    monkeypatch.setattr(pricing_mod, "_utcnow", lambda: evening)
    results = [service.refresh_prices().unchanged_ts_symbols for _ in range(3)]

    assert results == [[], [], ["XAD1.DE"]]


def test_new_provider_ts_resets_the_streak(monkeypatch):
    stored = _utc("2026-11-03 13:00")
    newer = _utc("2026-11-03 13:16")
    monkeypatch.setattr(pricing_mod, "make_finance_client", lambda _s: _QuoteClient(newer))
    response = PriceIngestionService(_pricing_settings(), _TickRepo(stored)).refresh_prices(
        market_hours_at=_utc("2026-11-03 13:16"),
    )
    assert response.unchanged_ts_symbols == []
    assert isinstance(response, PriceRefreshResponse)
