from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_markets import register_markets_routes
from app.services import market_calendar_service
from app.services.market_calendar_service import (
    EarningsRow,
    EconomicRow,
    MarketCalendarService,
    central_bank_events,
    earnings_events,
    earnings_rows_from_frame,
    economic_rows_from_frame,
    fetch_yahoo_earnings,
    fetch_earnings,
    fetch_fmp_earnings,
    fetch_yahoo_economic_events,
    fetch_yahoo_watchlist_earnings,
    fmp_earnings_rows,
    macro_events,
    upcoming_trading_days,
    watchlist_row_from_calendar,
)

# Sunday: the outlook starts on the following Monday.
SUNDAY = date(2026, 10, 25)
WINDOW = [date(2026, 10, 26), date(2026, 10, 27), date(2026, 10, 28)]


def _earnings(symbol, company, market_cap, starts_at, timing=None, eps_estimate=None):
    return EarningsRow(
        symbol=symbol,
        company=company,
        market_cap=market_cap,
        starts_at=starts_at,
        timing=timing,
        eps_estimate=eps_estimate,
        eps_actual=None,
    )


def _release(name, region, starts_at, expected=None, previous=None):
    return EconomicRow(
        name=name,
        region=region,
        starts_at=starts_at,
        period=None,
        expected=expected,
        previous=previous,
        actual=None,
    )


def test_upcoming_trading_days_skips_weekends():
    assert upcoming_trading_days(SUNDAY, 3) == WINDOW
    assert upcoming_trading_days(date(2026, 10, 30), 3) == [
        date(2026, 10, 30),
        date(2026, 11, 2),
        date(2026, 11, 3),
    ]


def test_central_bank_events_use_decision_time_in_bank_timezone():
    events = central_bank_events([date(2026, 10, 28), date(2026, 10, 29)])

    by_id = {event.id: event for event in events}
    # 14:00 in New York (EDT until 1 November) and 14:15 in Frankfurt (CET from 25 October).
    assert by_id["fed-2026-10-28"].starts_at == datetime(2026, 10, 28, 18, 0, tzinfo=UTC)
    assert by_id["ecb-2026-10-29"].starts_at == datetime(2026, 10, 29, 13, 15, tzinfo=UTC)
    assert all(event.importance == "high" and event.category == "central_bank" for event in events)
    assert by_id["fed-2026-10-28"].tags == []


def test_central_bank_events_tag_projection_meetings():
    [fed] = central_bank_events([date(2026, 12, 9)])

    assert fed.tags == ["Proiezioni e dot plot"]
    assert "dot plot" in fed.description


def test_earnings_events_keep_large_caps_once_per_company():
    after_close = datetime(2026, 10, 28, 20, 5, tzinfo=UTC)
    rows = [
        _earnings("GOOG", "Alphabet Inc.", 2.1e12, after_close, timing="AMC"),
        _earnings("GOOGL", "Alphabet Inc.", 2.2e12, after_close, timing="AMC", eps_estimate=2.3),
        _earnings("V", "Visa Inc.", 6.0e11, datetime(2026, 10, 27, 20, 5, tzinfo=UTC), timing="AMC"),
        _earnings("XOM", "Exxon Mobil Corporation", 1.5e11, datetime(2026, 10, 27, 11, 0, tzinfo=UTC), timing="BMO"),
        _earnings("SMALL", "Small Co.", 5.0e10, after_close),
        _earnings("MSFT", "Microsoft Corporation", 3.5e12, datetime(2026, 10, 30, 20, 5, tzinfo=UTC)),
    ]

    events = {event.symbol: event for event in earnings_events(rows, WINDOW)}

    assert set(events) == {"GOOGL", "V", "XOM"}
    alphabet = events["GOOGL"]
    assert alphabet.title == "Trimestrale Alphabet"
    assert alphabet.importance == "high"
    assert alphabet.tags == ["Big Tech"]
    assert alphabet.time_hint == "Dopo la chiusura USA"
    assert alphabet.eps_estimate == 2.3
    assert events["V"].importance == "high"
    assert events["V"].tags == []
    assert events["XOM"].importance == "medium"
    assert events["XOM"].title == "Trimestrale Exxon Mobil"
    assert events["XOM"].time_hint == "Prima dell'apertura USA"


def test_earnings_events_treat_midnight_utc_as_date_only():
    rows = [_earnings("AAPL", "Apple Inc.", 3.8e12, datetime(2026, 10, 27, 0, 0, tzinfo=UTC))]

    [event] = earnings_events(rows, WINDOW)

    # Read in New York time this would fall on the 26th.
    assert event.day == date(2026, 10, 27)
    assert event.starts_at is None


def test_macro_events_keep_one_headline_release_per_rule_and_day():
    at = datetime(2026, 10, 27, 12, 30, tzinfo=UTC)
    rows = [
        _release("Core CPI YY, NSA", "US", at, expected=3.1),
        _release("CPI MM, SA", "US", at, expected=0.3),
        _release("CPI YY, NSA", "US", at, expected=2.9, previous=3.0),
        _release("HICP Flash YY", "EZ", datetime(2026, 10, 28, 9, 0, tzinfo=UTC), expected=2.1),
        _release("CPI YY", "JP", at),
        _release("Fed Funds Tgt Rate", "US", at),
        _release("Initial Jobless Clm", "US", at),
    ]

    events = {event.id: event for event in macro_events(rows, WINDOW)}

    assert set(events) == {"macro-us_cpi-2026-10-27", "macro-ez_inflation-2026-10-28"}
    cpi = events["macro-us_cpi-2026-10-27"]
    assert cpi.source_name == "CPI YY, NSA"
    assert (cpi.expected, cpi.previous) == (2.9, 3.0)
    assert cpi.importance == "high"
    assert events["macro-ez_inflation-2026-10-28"].region == "EU"


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _failing(calls=None):
    def fetcher(start, end):
        if calls is not None:
            calls.append(start)
        raise RuntimeError("Too Many Requests")
    return fetcher


def test_service_groups_by_day_and_caches_one_fetch_for_every_range():
    calls = []

    def earnings_fetcher(start, end):
        calls.append((start, end))
        return [_earnings("META", "Meta Platforms, Inc.", 1.8e12, datetime(2026, 10, 28, 20, 5, tzinfo=UTC), "AMC")]

    def economic_fetcher(start, end):
        return [_release("GDP Advance", "US", datetime(2026, 10, 28, 12, 30, tzinfo=UTC))]

    clock = _Clock()
    service = MarketCalendarService(earnings_fetcher, economic_fetcher, _failing(), clock=clock)

    response = service.get_calendar(3, today=SUNDAY)

    assert (response.start_date, response.end_date) == (WINDOW[0], WINDOW[-1])
    assert [day.day for day in response.days] == WINDOW
    assert response.days[0].events == []
    titles = [event.title for event in response.days[2].events]
    # High importance first, then by time: Fed at 18:00 UTC, Meta after the close, then GDP (medium).
    assert titles == ["Fed: decisione sui tassi", "Trimestrale Meta Platforms", "PIL USA"]
    assert response.warnings == []
    # Fetched once for the five-day window, which the three-day view reuses.
    assert calls == [(WINDOW[0], date(2026, 10, 30))]

    assert service.get_calendar(5, today=SUNDAY).end_date == date(2026, 10, 30)
    assert len(calls) == 1
    clock.now += 1801
    service.get_calendar(3, today=SUNDAY)
    assert len(calls) == 2


def test_service_reports_provider_failure_and_waits_before_retrying():
    calls = []
    clock = _Clock()
    service = MarketCalendarService(_failing(calls), lambda start, end: [], _failing(), clock=clock)

    response = service.get_calendar(3, today=SUNDAY)

    assert response.warnings == ["Calendario delle trimestrali momentaneamente non disponibile."]
    assert [event.id for event in response.days[2].events] == ["fed-2026-10-28"]
    clock.now += 120
    service.get_calendar(3, today=SUNDAY)
    assert len(calls) == 1
    clock.now += 181
    service.get_calendar(3, today=SUNDAY)
    assert len(calls) == 2


def test_service_falls_back_to_big_tech_dates_when_the_earnings_calendar_fails():
    def fallback(start, end):
        return [_earnings("MSFT", "Microsoft", None, datetime(2026, 10, 28, tzinfo=UTC))]

    service = MarketCalendarService(_failing(), lambda start, end: [], fallback)

    response = service.get_calendar(3, today=SUNDAY)

    [microsoft] = [event for event in response.days[2].events if event.category == "earnings"]
    assert microsoft.title == "Trimestrale Microsoft"
    assert microsoft.importance == "high"
    assert microsoft.starts_at is None
    assert response.warnings == [
        "Calendario completo delle trimestrali non disponibile: sono mostrate solo le Big Tech.",
    ]


def test_service_keeps_the_last_good_rows_when_a_refresh_fails():
    state = {"fail": False}

    def earnings_fetcher(start, end):
        if state["fail"]:
            raise RuntimeError("Too Many Requests")
        return [_earnings("V", "Visa Inc.", 6.0e11, datetime(2026, 10, 27, 20, 5, tzinfo=UTC), "AMC")]

    def economic_fetcher(start, end):
        if state["fail"]:
            raise RuntimeError("Too Many Requests")
        return [_release("CPI YY, NSA", "US", datetime(2026, 10, 27, 12, 30, tzinfo=UTC))]

    clock = _Clock()
    service = MarketCalendarService(earnings_fetcher, economic_fetcher, _failing(), clock=clock)
    service.get_calendar(3, today=SUNDAY)

    state["fail"] = True
    clock.now += 1801
    response = service.get_calendar(3, today=SUNDAY)

    assert [event.title for event in response.days[1].events] == ["Inflazione USA (CPI)", "Trimestrale Visa"]
    assert response.warnings == []


def test_service_warns_when_central_bank_calendar_is_missing_a_year():
    service = MarketCalendarService(lambda start, end: [], lambda start, end: [], _failing())

    response = service.get_calendar(3, today=date(2028, 1, 3))

    assert response.warnings == ["Calendario delle riunioni Fed e BCE non ancora disponibile per il 2028."]


def test_rows_from_frames_parse_yfinance_columns():
    earnings = pd.DataFrame(
        {
            "Company": ["Microsoft Corporation"],
            "Marketcap": [3.5e12],
            "Event Name": ["Q1 2027 Earnings Release"],
            "Event Start Date": [pd.Timestamp("2026-10-28T20:05:00Z")],
            "Timing": ["AMC"],
            "EPS Estimate": [float("nan")],
            "Reported EPS": [float("nan")],
            "Surprise(%)": [float("nan")],
        },
        index=pd.Index(["MSFT"], name="Symbol"),
    )
    economic = pd.DataFrame(
        {
            "Region": ["US"],
            "Event Time": [pd.Timestamp("2026-10-27 12:30:00")],
            "For": ["Sep"],
            "Actual": [float("nan")],
            "Expected": [2.9],
            "Last": [3.0],
            "Revised": [float("nan")],
        },
        index=pd.Index(["CPI YY, NSA"], name="Event"),
    )

    [earnings_row] = earnings_rows_from_frame(earnings)
    [economic_row] = economic_rows_from_frame(economic)

    assert earnings_row == EarningsRow(
        symbol="MSFT",
        company="Microsoft Corporation",
        market_cap=3.5e12,
        starts_at=datetime(2026, 10, 28, 20, 5, tzinfo=UTC),
        timing="AMC",
        eps_estimate=None,
        eps_actual=None,
    )
    assert economic_row == EconomicRow(
        name="CPI YY, NSA",
        region="US",
        starts_at=datetime(2026, 10, 27, 12, 30, tzinfo=UTC),
        period="Sep",
        expected=2.9,
        previous=3.0,
        actual=None,
    )
    assert earnings_rows_from_frame(pd.DataFrame()) == []


def test_fetch_yahoo_earnings_parses_a_yahoo_payload(monkeypatch):
    yf_data = pytest.importorskip("yfinance.data")
    requests = []

    class _Response:
        def json(self):
            return {
                "finance": {
                    "result": [{
                        "documents": [{
                            "columns": [
                                {"label": "Symbol", "type": "STRING"},
                                {"label": "Company Name", "type": "STRING"},
                                {"label": "Market Cap (Intraday)", "type": "NUMBER"},
                                {"label": "Event Name", "type": "STRING"},
                                {"label": "Event Start Date", "type": "DATETIME"},
                                {"label": "Event Start Date", "type": "STRING"},
                                {"label": "EPS Estimate", "type": "NUMBER"},
                                {"label": "Reported EPS", "type": "NUMBER"},
                                {"label": "Surprise (%)", "type": "NUMBER"},
                            ],
                            "rows": [[
                                "MSFT", "Microsoft Corporation", 3.5e12, "Q1 2027 Earnings Release",
                                "2026-10-28T20:05:00.000Z", "AMC", 3.9, 0, 0,
                            ]],
                        }],
                    }],
                },
            }

    def fake_post(self, url, body=None, params=None, **kwargs):
        requests.append(body)
        return _Response()

    monkeypatch.setattr(yf_data.YfData, "post", fake_post)

    [row] = fetch_yahoo_earnings(WINDOW[0], WINDOW[-1])

    assert row.symbol == "MSFT"
    assert row.timing == "AMC"
    assert row.eps_estimate == 3.9
    assert row.eps_actual is None
    assert row.starts_at == datetime(2026, 10, 28, 20, 5, tzinfo=UTC)
    # One request (no "most active" screener call), up to the midnight after the last day.
    [body] = requests
    assert {"operator": "LTE", "operands": ["startdatetime", "2026-10-29"]} in body["query"]["operands"]


def test_fetch_yahoo_economic_events_parses_a_yahoo_payload(monkeypatch):
    yf_data = pytest.importorskip("yfinance.data")
    offsets = []

    class _Response:
        def json(self):
            return {
                "finance": {
                    "result": [{
                        "documents": [{
                            "columns": [
                                {"label": "Event", "type": "STRING"},
                                {"label": "Country Code", "type": "STRING"},
                                {"label": "Event Time", "type": "DATETIME"},
                                {"label": "For", "type": "STRING"},
                                {"label": "Actual", "type": "NUMBER"},
                                {"label": "Market Expectation", "type": "NUMBER"},
                                {"label": "Prior to This", "type": "NUMBER"},
                                {"label": "Revised from", "type": "NUMBER"},
                            ],
                            "rows": [["CPI YY, NSA", "US", "2026-10-27T12:30:00.000Z", "Sep", 0, 2.9, 3.0, 0]],
                        }],
                    }],
                },
            }

    def fake_post(self, url, body=None, params=None, **kwargs):
        offsets.append(body["offset"])
        return _Response()

    monkeypatch.setattr(yf_data.YfData, "post", fake_post)

    [row] = fetch_yahoo_economic_events(WINDOW[0], WINDOW[-1])

    assert row == EconomicRow(
        name="CPI YY, NSA",
        region="US",
        starts_at=datetime(2026, 10, 27, 12, 30, tzinfo=UTC),
        period="Sep",
        expected=2.9,
        previous=3.0,
        actual=None,
    )
    # A short page is the last one.
    assert offsets == [0]


def test_watchlist_row_needs_a_single_announced_date():
    announced = {"Earnings Date": [date(2026, 10, 28)], "Earnings Average": 3.9}
    estimated = {"Earnings Date": [date(2026, 10, 27), date(2026, 10, 31)]}

    row = watchlist_row_from_calendar("MSFT", "Microsoft", announced)

    assert row == EarningsRow(
        symbol="MSFT",
        company="Microsoft",
        market_cap=None,
        starts_at=datetime(2026, 10, 28, tzinfo=UTC),
        timing=None,
        eps_estimate=3.9,
        eps_actual=None,
    )
    assert watchlist_row_from_calendar("MSFT", "Microsoft", estimated) is None
    assert watchlist_row_from_calendar("MSFT", "Microsoft", {}) is None


def test_fetch_yahoo_watchlist_earnings_skips_failing_symbols(monkeypatch):
    yf = pytest.importorskip("yfinance")
    monkeypatch.setattr(market_calendar_service, "_watchlist_cache", {})
    requested = []

    class _Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        @property
        def calendar(self):
            requested.append(self.symbol)
            if self.symbol == "MSFT":
                return {"Earnings Date": [date(2026, 10, 28)]}
            if self.symbol == "AAPL":
                return {"Earnings Date": [date(2026, 11, 20)]}
            if self.symbol == "NVDA":
                # What yfinance returns after logging a Yahoo error.
                return {}
            raise RuntimeError("Too Many Requests")

    monkeypatch.setattr(yf, "Ticker", _Ticker)

    rows = fetch_yahoo_watchlist_earnings(WINDOW[0], WINDOW[-1])

    assert [row.symbol for row in rows] == ["MSFT"]
    # Answers are cached; failures, empty calendars included, are retried.
    requested.clear()
    fetch_yahoo_watchlist_earnings(WINDOW[0], WINDOW[-1])
    assert "MSFT" not in requested and "AAPL" not in requested
    assert "NVDA" in requested


def test_fetch_yahoo_watchlist_earnings_stops_when_yahoo_rejects_the_first_lookup(monkeypatch):
    yf = pytest.importorskip("yfinance")
    monkeypatch.setattr(market_calendar_service, "_watchlist_cache", {})
    requested = []

    class _Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        @property
        def calendar(self):
            # yfinance logs "HTTP Error 401 ... Invalid Crumb" and returns {}.
            requested.append(self.symbol)
            return {}

    monkeypatch.setattr(yf, "Ticker", _Ticker)

    with pytest.raises(RuntimeError):
        fetch_yahoo_watchlist_earnings(WINDOW[0], WINDOW[-1])
    assert requested == ["AAPL"]
    assert market_calendar_service._watchlist_cache == {}


FMP_KEY = "secret-fmp-key"


def _fmp_settings(monkeypatch, api_key=FMP_KEY):
    settings = SimpleNamespace(
        fmt_api_key=api_key,
        fmt_api_base_url="https://financialmodelingprep.com/stable/",
        fmt_timeout_seconds=5.0,
    )
    monkeypatch.setattr(market_calendar_service, "get_settings", lambda: settings)


def test_fmp_earnings_rows_keep_large_caps_named_from_the_static_list():
    payload = [
        {"symbol": "MSFT", "date": "2026-10-28", "epsEstimated": 3.9, "epsActual": None},
        {"symbol": "jnj", "date": "2026-10-27", "epsEstimated": 2.75},
        {"symbol": "ISP.MI", "date": "2026-10-28", "epsEstimated": 0.12},
        {"symbol": "TINY", "date": "2026-10-28"},
        {"symbol": "AAPL", "date": "not a date"},
        "garbage",
    ]

    rows = fmp_earnings_rows(payload)

    assert rows == [
        EarningsRow(
            symbol="MSFT",
            company="Microsoft",
            market_cap=None,
            starts_at=datetime(2026, 10, 28, tzinfo=UTC),
            timing=None,
            eps_estimate=3.9,
            eps_actual=None,
        ),
        EarningsRow(
            symbol="JNJ",
            company="Johnson & Johnson",
            market_cap=None,
            starts_at=datetime(2026, 10, 27, tzinfo=UTC),
            timing=None,
            eps_estimate=2.75,
            eps_actual=None,
        ),
    ]


def test_earnings_events_rate_rows_without_market_cap_from_the_static_lists():
    def row(symbol, company):
        return _earnings(symbol, company, None, datetime(2026, 10, 27, tzinfo=UTC))

    events = {event.symbol: event for event in earnings_events(
        [row("MSFT", "Microsoft"), row("JPM", "JPMorgan Chase"), row("JNJ", "Johnson & Johnson")],
        WINDOW,
    )}

    assert {symbol: event.importance for symbol, event in events.items()} == {
        "MSFT": "high",
        "JPM": "high",
        "JNJ": "medium",
    }
    assert events["JNJ"].starts_at is None
    assert events["JNJ"].time_hint is None


def test_fetch_fmp_earnings_calls_the_stable_calendar(monkeypatch):
    _fmp_settings(monkeypatch)
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params))
        return httpx.Response(200, json=[{"symbol": "META", "date": "2026-10-28", "epsEstimated": 7.1}])

    monkeypatch.setattr(market_calendar_service.httpx, "get", fake_get)

    [row] = fetch_fmp_earnings(WINDOW[0], WINDOW[-1])

    assert (row.symbol, row.company, row.eps_estimate) == ("META", "Meta Platforms", 7.1)
    assert calls == [(
        "https://financialmodelingprep.com/stable/earnings-calendar",
        {"from": "2026-10-26", "to": "2026-10-28", "apikey": FMP_KEY},
    )]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(402, text="Premium endpoint"),
        httpx.Response(200, json={"Error Message": "Limit Reach"}),
        httpx.Response(200, json=[]),
        httpx.ConnectTimeout(f"timed out: https://financialmodelingprep.com/stable/earnings-calendar?apikey={FMP_KEY}"),
    ],
)
def test_fetch_fmp_earnings_errors_never_carry_the_api_key(monkeypatch, response):
    _fmp_settings(monkeypatch)

    def fake_get(url, params, timeout):
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(market_calendar_service.httpx, "get", fake_get)

    with pytest.raises(RuntimeError) as excinfo:
        fetch_fmp_earnings(WINDOW[0], WINDOW[-1])
    assert FMP_KEY not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


def test_fetch_earnings_prefers_fmp_and_falls_back_to_yahoo(monkeypatch):
    _fmp_settings(monkeypatch)
    fmp_row = _earnings("MSFT", "Microsoft", None, datetime(2026, 10, 28, tzinfo=UTC))
    yahoo_row = _earnings("V", "Visa Inc.", 6.0e11, datetime(2026, 10, 27, 20, 5, tzinfo=UTC), "AMC")
    monkeypatch.setattr(market_calendar_service, "fetch_yahoo_earnings", lambda start, end: [yahoo_row])

    monkeypatch.setattr(market_calendar_service, "fetch_fmp_earnings", lambda start, end: [fmp_row])
    assert fetch_earnings(WINDOW[0], WINDOW[-1]) == [fmp_row]

    monkeypatch.setattr(market_calendar_service, "fetch_fmp_earnings", _failing())
    assert fetch_earnings(WINDOW[0], WINDOW[-1]) == [yahoo_row]


def test_fetch_earnings_uses_yahoo_without_an_fmp_key(monkeypatch):
    _fmp_settings(monkeypatch, api_key=" ")
    yahoo_row = _earnings("V", "Visa Inc.", 6.0e11, datetime(2026, 10, 27, 20, 5, tzinfo=UTC), "AMC")
    monkeypatch.setattr(market_calendar_service, "fetch_yahoo_earnings", lambda start, end: [yahoo_row])

    def unexpected_fmp_call(start, end):
        raise AssertionError("FMP must not be called without an API key")

    monkeypatch.setattr(market_calendar_service, "fetch_fmp_earnings", unexpected_fmp_call)

    assert fetch_earnings(WINDOW[0], WINDOW[-1]) == [yahoo_row]


def test_calendar_route_validates_days():
    class _FakeService:
        def __init__(self):
            self.calls = []

        def get_calendar(self, trading_days):
            self.calls.append(trading_days)
            service = MarketCalendarService(lambda s, e: [], lambda s, e: [], _failing())
            return service.get_calendar(trading_days, today=SUNDAY)

    service = _FakeService()
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_markets_routes(router, repo=object(), finance_client=object(), market_calendar_service=service)
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/markets/calendar")
    assert response.status_code == 200
    payload = response.json()
    assert payload["start_date"] == "2026-10-26"
    assert payload["days"][2]["events"][0]["id"] == "fed-2026-10-28"
    assert client.get("/api/markets/calendar?days=5").status_code == 200
    assert client.get("/api/markets/calendar?days=9").status_code == 422
    assert service.calls == [3, 5]
