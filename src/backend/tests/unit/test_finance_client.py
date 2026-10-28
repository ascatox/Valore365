import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import finance_client
from app.errors import ProviderError
from app.finance_client import YahooFinanceClient, normalize_expense_ratio_pct


def test_normalize_expense_ratio_pct_handles_percent_and_fraction_inputs():
    assert normalize_expense_ratio_pct(0.13) == 0.13
    assert normalize_expense_ratio_pct(0.0013) == 0.13
    assert normalize_expense_ratio_pct(0.22) == 0.22
    assert normalize_expense_ratio_pct(None) is None


def test_yfinance_asset_info_marks_missing_metadata(monkeypatch):
    class _Ticker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        @property
        def info(self):
            raise RuntimeError("provider down")

    fake_module = types.SimpleNamespace(Ticker=lambda symbol: _Ticker(symbol))
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    client = YahooFinanceClient(max_retries=1)
    info = client.get_asset_info("VWCE")

    assert info.metadata_status == "missing"
    assert info.current_price_source is None
    assert info.warnings


# --- Yahoo v8 chart -----------------------------------------------------------


def _epoch(local: str, tz: str) -> int:
    return int(datetime.fromisoformat(local).replace(tzinfo=ZoneInfo(tz)).timestamp())


def _chart(
    symbol: str,
    rows: list[tuple],
    *,
    tz: str = "America/New_York",
    gmtoffset: int = -14400,
    adjclose: bool = True,
    granularity: str = "1d",
    range_: str = "5d",
    **meta_overrides,
) -> dict:
    """Yahoo /v8/finance/chart payload. rows: (epoch, open, high, low, close, volume[, adjclose])."""
    meta = {
        "currency": "USD",
        "symbol": symbol,
        "exchangeName": "NMS",
        "fullExchangeName": "NasdaqGS",
        "instrumentType": "EQUITY",
        "firstTradeDate": 345479400,
        "regularMarketTime": rows[-1][0] + 23400 if rows else 1792785600,
        "hasPrePostMarketData": True,
        "gmtoffset": gmtoffset,
        "timezone": "EDT",
        "exchangeTimezoneName": tz,
        "regularMarketPrice": rows[-1][4] if rows else None,
        "fiftyTwoWeekHigh": 270.0,
        "fiftyTwoWeekLow": 169.21,
        "longName": "Apple Inc.",
        "shortName": "Apple Inc.",
        "chartPreviousClose": 250.0,
        "priceHint": 2,
        "dataGranularity": granularity,
        "range": range_,
        "validRanges": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"],
    }
    meta.update(meta_overrides)
    meta = {k: v for k, v in meta.items() if v is not None}
    result: dict = {"meta": meta}
    if rows:
        result["timestamp"] = [r[0] for r in rows]
        result["indicators"] = {
            "quote": [
                {
                    "open": [r[1] for r in rows],
                    "high": [r[2] for r in rows],
                    "low": [r[3] for r in rows],
                    "close": [r[4] for r in rows],
                    "volume": [r[5] for r in rows],
                }
            ]
        }
        if adjclose:
            result["indicators"]["adjclose"] = [{"adjclose": [r[6] if len(r) > 6 else r[4] for r in rows]}]
    else:
        # Simbolo valido ma nessuna barra nel periodo.
        result["indicators"] = {"quote": [{}]}
    return {"chart": {"result": [result], "error": None}}


_NOT_FOUND = {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"}}}

# AAPL, last 5 sessions (daily bars stamped at the 09:30 New York open).
_AAPL_ROWS = [
    (_epoch("2026-10-21 09:30", "America/New_York"), 262.5, 264.0, 261.0, 262.77, 46695900),
    (_epoch("2026-10-22 09:30", "America/New_York"), 262.6, 262.85, 255.43, 258.45, 45015300),
    (_epoch("2026-10-23 09:30", "America/New_York"), 259.0, 260.62, 258.0, 259.58, 32754900),
    (_epoch("2026-10-26 09:30", "America/New_York"), 264.88, 269.12, 264.65, 268.81, 44888200),
    (_epoch("2026-10-27 09:30", "America/New_York"), 268.99, 269.89, 266.0, 269.0, 41534759),
]


class _Recorder:
    """MockTransport handler: serves the queued responses and records the requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self._lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.requests.append(request)
            item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json=item)


def _client(handler, **kwargs) -> YahooFinanceClient:
    kwargs.setdefault("max_retries", 3)
    kwargs.setdefault("retry_backoff_seconds", 0.5)
    return YahooFinanceClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(finance_client.time, "sleep", lambda seconds: calls.append(seconds))
    return calls


def test_quote_reads_price_and_previous_close_with_one_light_request():
    handler = _Recorder(_chart("AAPL", _AAPL_ROWS))
    before = datetime.now(UTC)

    quote = _client(handler).get_quote("AAPL")

    assert quote.price == 269.0
    # Penultima chiusura giornaliera, come fast_info.previous_close.
    assert quote.previous_close == 268.81
    assert quote.source == "fast_info"
    assert (quote.is_realtime, quote.is_fallback, quote.stale, quote.warning) == (True, False, False, None)
    # ts = ora del refresh, come prima (price_ticks / day change).
    assert before <= quote.ts <= datetime.now(UTC)

    assert len(handler.requests) == 1
    request = handler.requests[0]
    assert request.url.host == "query1.finance.yahoo.com"
    assert request.url.path == "/v8/finance/chart/AAPL"
    assert request.url.params["range"] == "5d"
    assert request.url.params["interval"] == "1d"
    assert request.headers["User-Agent"].startswith("Mozilla/5.0")


def test_quote_previous_close_ignores_the_live_row_and_null_rows():
    rows = [
        _AAPL_ROWS[2],
        # Holiday-like row: Yahoo returns the timestamp with null values.
        (_epoch("2026-10-26 09:30", "America/New_York"), None, None, None, None, None),
        _AAPL_ROWS[4],
        # Live row Yahoo appends during the session: same day as the previous one.
        (_epoch("2026-10-27 14:47", "America/New_York"), None, None, None, 270.4, 1000),
    ]
    handler = _Recorder(_chart("AAPL", rows, regularMarketPrice=270.4))

    quote = _client(handler).get_quote("AAPL")

    assert quote.price == 270.4
    # Not 269.0 (the duplicated 27/10 bar) and not the null 26/10 row.
    assert quote.previous_close == 259.58


def test_quote_previous_close_falls_back_to_chart_previous_close_with_a_single_bar():
    handler = _Recorder(_chart("XYZ.MI", _AAPL_ROWS[-1:], tz="Europe/Rome", gmtoffset=3600, chartPreviousClose=265.1))

    quote = _client(handler).get_quote("XYZ.MI")

    assert quote.previous_close == 265.1


def test_quote_falls_back_to_last_close_without_regular_market_price():
    handler = _Recorder(_chart("VWCE.DE", _AAPL_ROWS[-2:], tz="Europe/Berlin", gmtoffset=3600, regularMarketPrice=None))

    quote = _client(handler).get_quote("VWCE.DE")

    assert quote.price == 269.0
    assert quote.previous_close == 268.81
    assert quote.source == "history_close"
    assert (quote.is_realtime, quote.is_fallback, quote.stale) == (False, True, True)
    assert quote.warning == "realtime quote unavailable; using last close"
    # Mezzanotte locale del giorno della barra, come l'indice di yfinance.
    assert quote.ts == datetime(2026, 10, 27, tzinfo=ZoneInfo("Europe/Berlin"))


def test_quote_without_price_nor_bars_raises_no_data():
    handler = _Recorder(_chart("DEAD", [], regularMarketPrice=None))

    with pytest.raises(ProviderError) as exc:
        _client(handler).get_quote("DEAD")

    assert exc.value.reason == "no_data"


def test_quote_of_unknown_symbol_raises_no_data_without_retrying(sleeps):
    handler = _Recorder(httpx.Response(404, json=_NOT_FOUND))

    with pytest.raises(ProviderError) as exc:
        _client(handler).get_quote("NOPE")

    assert exc.value.reason == "no_data"
    assert exc.value.provider == "yfinance"
    assert exc.value.message == "Nessuna quotazione disponibile per NOPE"
    assert len(handler.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, text="<html><body>Not Found</body></html>"),
        httpx.Response(200, json=_NOT_FOUND),
    ],
)
def test_yahoo_error_shapes_map_to_no_data(response):
    with pytest.raises(ProviderError) as exc:
        _client(_Recorder(response)).get_daily_bars("NOPE", start_date="2026-10-01", end_date="2026-10-28")

    assert exc.value.reason == "no_data"


def test_unauthorized_is_a_provider_error_not_missing_data():
    payload = {"chart": {"result": None, "error": {"code": "Unauthorized", "description": "Invalid Crumb"}}}
    handler = _Recorder(httpx.Response(401, json=payload))

    with pytest.raises(ProviderError) as exc:
        _client(handler).get_quote("AAPL")

    assert exc.value.reason == "provider_error"


def test_quote_retries_429_honoring_retry_after(sleeps):
    handler = _Recorder(
        httpx.Response(429, headers={"Retry-After": "2"}, text="Too Many Requests"),
        _chart("AAPL", _AAPL_ROWS),
    )

    quote = _client(handler).get_quote("AAPL")

    assert quote.price == 269.0
    assert len(handler.requests) == 2
    assert sleeps == [2.0]


def test_quote_gives_up_after_max_attempts_with_exponential_backoff(sleeps):
    handler = _Recorder(httpx.Response(429, text="Too Many Requests"))

    with pytest.raises(ProviderError) as exc:
        _client(handler, max_retries=3).get_quote("AAPL")

    assert exc.value.reason == "rate_limited"
    assert exc.value.retryable is True
    assert len(handler.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_retry_after_longer_than_the_cap_is_not_waited(sleeps):
    handler = _Recorder(httpx.Response(429, headers={"Retry-After": "120"}))

    with pytest.raises(ProviderError) as exc:
        _client(handler, max_retries=3).get_quote("AAPL")

    assert exc.value.reason == "rate_limited"
    assert len(handler.requests) == 1
    assert sleeps == []


def test_network_errors_are_retried_then_reported(sleeps):
    handler = _Recorder(httpx.ConnectTimeout("timed out"))

    with pytest.raises(ProviderError) as exc:
        _client(handler, max_retries=2).get_quote("AAPL")

    assert exc.value.reason == "timeout"
    assert len(handler.requests) == 2


def test_market_quote_reads_last_trade_time_from_chart_metadata():
    handler = _Recorder(_chart("^GSPC", _AAPL_ROWS, regularMarketPrice=6850.2, regularMarketTime=1792785600))

    quote = _client(handler).get_market_quote("^GSPC")

    assert quote.price == 6850.2
    assert quote.previous_close == 268.81
    assert quote.ts == datetime(2026, 10, 23, 20, 0, tzinfo=UTC)
    assert quote.source == "fast_info"
    assert quote.is_realtime is True
    assert len(handler.requests) == 1
    assert handler.requests[0].url.raw_path.split(b"?")[0] == b"/v8/finance/chart/%5EGSPC"


def test_market_quote_never_raises(sleeps):
    handler = _Recorder(httpx.ConnectError("connection refused"))

    quote = _client(handler, max_retries=1).get_market_quote("^GSPC")

    assert quote.price is None
    assert quote.previous_close is None
    assert quote.ts is not None
    assert quote.warning == "market quote unavailable"
    assert (quote.is_realtime, quote.is_fallback, quote.stale) == (False, True, True)


def test_daily_bars_are_adjusted_for_splits_and_dividends_and_windowed():
    rows = [
        # Before start_date: Yahoo gets a wider window, the client trims it.
        (_epoch("2026-10-20 09:30", "America/New_York"), 50.0, 51.0, 49.0, 50.0, 100, 49.0),
        (_epoch("2026-10-21 09:30", "America/New_York"), 100.0, 110.0, 90.0, 105.0, 1200, 84.0),
        (_epoch("2026-10-22 09:30", "America/New_York"), 106.0, 108.0, 104.0, 107.0, 900, 107.0),
        # end_date is exclusive, as with yfinance.
        (_epoch("2026-10-23 09:30", "America/New_York"), 108.0, 109.0, 107.0, 108.5, 800, 108.5),
    ]
    handler = _Recorder(_chart("AAPL", rows, range_=None))

    bars = _client(handler).get_daily_bars("AAPL", start_date="2026-10-21", end_date="2026-10-23")

    assert [b.day for b in bars] == [date(2026, 10, 21), date(2026, 10, 22)]
    first = bars[0]
    ratio = 84.0 / 105.0
    assert first.open == pytest.approx(100.0 * ratio)
    assert first.high == pytest.approx(110.0 * ratio)
    assert first.low == pytest.approx(90.0 * ratio)
    assert first.close == 84.0
    assert first.volume == 1200.0
    assert (bars[1].open, bars[1].close) == (106.0, 107.0)

    params = handler.requests[0].url.params
    assert params["interval"] == "1d"
    assert "range" not in params
    start_utc = int(datetime(2026, 10, 21, tzinfo=UTC).timestamp())
    end_utc = int(datetime(2026, 10, 23, tzinfo=UTC).timestamp())
    assert int(params["period1"]) <= start_utc
    assert int(params["period2"]) >= end_utc


def test_daily_bars_honor_desc_order():
    handler = _Recorder(_chart("AAPL", _AAPL_ROWS))

    bars = _client(handler).get_daily_bars("AAPL", start_date="2026-10-01", end_date="2026-10-28", order="desc")

    assert [b.day for b in bars] == [
        date(2026, 10, 27), date(2026, 10, 26), date(2026, 10, 23), date(2026, 10, 22), date(2026, 10, 21),
    ]


def test_daily_bars_are_dated_in_the_exchange_timezone():
    # ^N225: Yahoo stamps each session at Tokyo midnight, i.e. 15:00 UTC of the
    # previous day. Dating in UTC would shift every bar one day back.
    rows = [
        (_epoch("2026-10-26 00:00", "Asia/Tokyo"), 49100.0, 49500.0, 48900.0, 49299.65, 0),
        (_epoch("2026-10-27 00:00", "Asia/Tokyo"), 49400.0, 50600.0, 49300.0, 50512.32, 0),
    ]
    assert datetime.fromtimestamp(rows[0][0], tz=UTC).date() == date(2026, 10, 25)
    handler = _Recorder(_chart("^N225", rows, tz="Asia/Tokyo", gmtoffset=32400, currency="JPY", instrumentType="INDEX"))

    bars = _client(handler).get_daily_bars("^N225", start_date="2026-10-26", end_date="2026-10-28")

    assert [(b.day, b.close) for b in bars] == [(date(2026, 10, 26), 49299.65), (date(2026, 10, 27), 50512.32)]


def test_daily_bars_skip_null_rows_and_default_missing_volume_to_zero():
    rows = [
        (_epoch("2026-10-21 09:30", "America/New_York"), 100.0, 101.0, 99.0, 100.5, None),
        (_epoch("2026-10-22 09:30", "America/New_York"), None, None, None, None, None),
        (_epoch("2026-10-23 09:30", "America/New_York"), 101.0, None, 100.0, 101.5, 10),
        (_epoch("2026-10-26 09:30", "America/New_York"), 102.0, 103.0, 101.0, 102.5, 20),
    ]
    handler = _Recorder(_chart("AAPL", rows))

    bars = _client(handler).get_daily_bars("AAPL", start_date="2026-10-21", end_date="2026-10-27")

    assert [b.day for b in bars] == [date(2026, 10, 21), date(2026, 10, 26)]
    # yfinance: Volume.fillna(0).
    assert bars[0].volume == 0.0


def test_daily_bars_without_adjclose_use_raw_values():
    handler = _Recorder(_chart("EUNL.DE", _AAPL_ROWS[:2], tz="Europe/Berlin", gmtoffset=7200, adjclose=False))

    bars = _client(handler).get_daily_bars("EUNL.DE", start_date="2026-10-21", end_date="2026-10-23")

    assert [(b.open, b.close) for b in bars] == [(262.5, 262.77), (262.6, 258.45)]


def test_daily_bars_keep_the_last_row_of_a_repeated_day():
    rows = [
        _AAPL_ROWS[3],
        _AAPL_ROWS[4],
        (_epoch("2026-10-27 15:10", "America/New_York"), 268.99, 270.5, 266.0, 270.1, 45000000),
    ]
    handler = _Recorder(_chart("AAPL", rows))

    bars = _client(handler).get_daily_bars("AAPL", start_date="2026-10-26", end_date="2026-10-28")

    assert [(b.day, b.close) for b in bars] == [(date(2026, 10, 26), 268.81), (date(2026, 10, 27), 270.1)]


def test_daily_bars_without_rows_raise_no_data():
    handler = _Recorder(_chart("AAPL", []))

    with pytest.raises(ProviderError) as exc:
        _client(handler).get_daily_bars("AAPL", start_date="2026-10-01", end_date="2026-10-28")

    assert exc.value.reason == "no_data"
    assert exc.value.message == "Nessun dato storico per AAPL"


def test_daily_bars_of_unknown_symbol_raise_no_data():
    handler = _Recorder(httpx.Response(404, json=_NOT_FOUND))

    with pytest.raises(ProviderError) as exc:
        _client(handler).get_daily_bars("NOPE", start_date="2026-10-01", end_date="2026-10-28")

    assert exc.value.reason == "no_data"


def test_bar_day_moves_a_pre_midnight_stamp_to_the_next_day():
    # yfinance fix_Yahoo_dst_issue: a daily bar at 23:00 local is that day's midnight.
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    assert finance_client._bar_day(datetime(2022, 1, 9, 23, 0, tzinfo=sao_paulo)) == date(2022, 1, 10)
    assert finance_client._bar_day(datetime(2022, 1, 10, 10, 0, tzinfo=sao_paulo)) == date(2022, 1, 10)


def test_fx_rates_use_the_yahoo_pair_symbol_and_london_dates():
    # EURUSD=X: daily bars at London midnight (23:00 UTC during BST).
    rows = [
        (_epoch("2026-10-22 00:00", "Europe/London"), 1.1601, 1.1625, 1.1590, 1.1603, 0),
        (_epoch("2026-10-23 00:00", "Europe/London"), 1.1610, 1.1630, 1.1580, 1.1612, 0),
    ]
    handler = _Recorder(_chart("EURUSD=X", rows, tz="Europe/London", gmtoffset=3600, currency="USD", instrumentType="CURRENCY"))

    rates = _client(handler).get_daily_fx_rates("EUR", "USD", start_date="2026-10-22", end_date="2026-10-24")

    assert handler.requests[0].url.path == "/v8/finance/chart/EURUSD=X"
    assert [(r.day, r.rate) for r in rates] == [(date(2026, 10, 22), 1.1603), (date(2026, 10, 23), 1.1612)]


def test_fx_rates_without_data_raise_no_data():
    handler = _Recorder(httpx.Response(404, json=_NOT_FOUND))

    with pytest.raises(ProviderError) as exc:
        _client(handler).get_daily_fx_rates("EUR", "XXX", start_date="2026-10-22", end_date="2026-10-24")

    assert exc.value.reason == "no_data"
    assert exc.value.symbol == "EURXXX=X"


def test_intraday_bars_stay_in_exchange_time_and_merge_the_live_row():
    ny = "America/New_York"
    rows = [
        (_epoch("2026-10-27 09:30", ny), 268.99, 269.5, 268.5, 269.2, 9000000),
        (_epoch("2026-10-27 10:30", ny), 269.2, 269.9, 268.9, 269.6, 5000000),
        (_epoch("2026-10-27 11:30", ny), None, None, None, None, None),
        (_epoch("2026-10-27 12:30", ny), 269.6, 270.0, 269.1, 269.8, 4000000),
        # Live row inside the 12:30 interval: merged into that bar.
        (_epoch("2026-10-27 12:47", ny), 269.8, 269.8, 269.8, 270.05, 0),
    ]
    handler = _Recorder(_chart("AAPL", rows, granularity="1h", range_="1d"))

    bars = _client(handler).get_intraday_bars("AAPL", period="1d", interval="1h")

    params = handler.requests[0].url.params
    assert (params["range"], params["interval"]) == ("1d", "1h")
    assert [b.ts.strftime("%d/%m %H:%M") for b in bars] == ["27/10 09:30", "27/10 10:30", "27/10 12:30"]
    assert [b.close for b in bars] == [269.2, 269.6, 270.05]
    assert all(b.ts.utcoffset() is not None for b in bars)


def test_intraday_bars_of_unknown_symbol_are_empty():
    handler = _Recorder(httpx.Response(404, json=_NOT_FOUND))

    assert _client(handler).get_intraday_bars("NOPE") == []


def test_isin_symbols_are_resolved_with_yahoo_search_like_yf_ticker(monkeypatch):
    searches = []

    class _Search:
        def __init__(self, query, max_results=8):
            searches.append(query)
            self.quotes = [{"symbol": "VWCE.DE"}]

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Search=_Search))
    monkeypatch.setattr(finance_client, "_isin_ticker_cache", {})
    handler = _Recorder(_chart("VWCE.DE", _AAPL_ROWS, tz="Europe/Berlin", gmtoffset=3600))
    client = _client(handler)

    client.get_quote("IE00BK5BQT80")
    client.get_quote("IE00BK5BQT80")

    assert [r.url.path for r in handler.requests] == ["/v8/finance/chart/VWCE.DE"] * 2
    assert searches == ["IE00BK5BQT80"]


def test_clients_share_one_http_connection_pool(monkeypatch):
    monkeypatch.setattr(finance_client, "_yahoo_http_client", None)
    settings = types.SimpleNamespace(
        finance_provider="yfinance",
        finance_request_timeout_seconds=10.0,
        finance_max_retries=3,
        finance_retry_backoff_seconds=0.5,
    )

    first = finance_client.make_finance_client(settings)
    second = finance_client.make_finance_client(settings)

    assert first is not second
    assert first._http_client is None and second._http_client is None
    assert finance_client._shared_yahoo_http_client() is finance_client._shared_yahoo_http_client()


def test_one_client_serves_concurrent_quotes_from_a_thread_pool():
    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.path.rsplit("/", 1)[-1]
        price = float(len(symbol))
        return httpx.Response(200, json=_chart(symbol, _AAPL_ROWS, regularMarketPrice=price))

    client = YahooFinanceClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    symbols = ["A", "BB", "CCC", "DDDD", "EEEEE", "FFFFFF"] * 4

    with ThreadPoolExecutor(max_workers=4) as executor:
        quotes = list(executor.map(client.get_quote, symbols))

    assert [q.price for q in quotes] == [float(len(s)) for s in symbols]

