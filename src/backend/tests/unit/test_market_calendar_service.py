from datetime import UTC, date, datetime

import pandas as pd
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_markets import register_markets_routes
from app.services.market_calendar_service import (
    EarningsRow,
    EconomicRow,
    MarketCalendarService,
    central_bank_events,
    earnings_events,
    earnings_rows_from_frame,
    economic_rows_from_frame,
    fetch_yahoo_earnings,
    fetch_yahoo_economic_events,
    macro_events,
    upcoming_trading_days,
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


def test_service_groups_by_day_and_caches():
    calls = []

    def earnings_fetcher(start, end):
        calls.append((start, end))
        return [_earnings("META", "Meta Platforms, Inc.", 1.8e12, datetime(2026, 10, 28, 20, 5, tzinfo=UTC), "AMC")]

    def economic_fetcher(start, end):
        return [_release("GDP Advance", "US", datetime(2026, 10, 28, 12, 30, tzinfo=UTC))]

    clock = _Clock()
    service = MarketCalendarService(earnings_fetcher, economic_fetcher, clock=clock)

    response = service.get_calendar(3, today=SUNDAY)

    assert (response.start_date, response.end_date) == (WINDOW[0], WINDOW[-1])
    assert [day.day for day in response.days] == WINDOW
    assert response.days[0].events == []
    titles = [event.title for event in response.days[2].events]
    # High importance first, then by time: Fed at 18:00 UTC, Meta after the close, then GDP (medium).
    assert titles == ["Fed: decisione sui tassi", "Trimestrale Meta Platforms", "PIL USA"]
    assert response.warnings == []
    assert calls == [(WINDOW[0], WINDOW[-1])]

    service.get_calendar(3, today=SUNDAY)
    assert len(calls) == 1
    clock.now += 1801
    service.get_calendar(3, today=SUNDAY)
    assert len(calls) == 2


def test_service_reports_provider_failure_and_retries_sooner():
    calls = []

    def failing_fetcher(start, end):
        calls.append(start)
        raise RuntimeError("Too Many Requests")

    clock = _Clock()
    service = MarketCalendarService(failing_fetcher, lambda start, end: [], clock=clock)

    response = service.get_calendar(3, today=SUNDAY)

    assert response.warnings == ["Calendario delle trimestrali momentaneamente non disponibile."]
    assert [event.id for event in response.days[2].events] == ["fed-2026-10-28"]
    clock.now += 121
    service.get_calendar(3, today=SUNDAY)
    assert len(calls) == 2


def test_service_warns_when_central_bank_calendar_is_missing_a_year():
    service = MarketCalendarService(lambda start, end: [], lambda start, end: [])

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


def test_calendar_route_validates_days():
    class _FakeService:
        def __init__(self):
            self.calls = []

        def get_calendar(self, trading_days):
            self.calls.append(trading_days)
            return MarketCalendarService(lambda s, e: [], lambda s, e: []).get_calendar(trading_days, today=SUNDAY)

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
