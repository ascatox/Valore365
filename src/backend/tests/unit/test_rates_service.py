from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_markets import register_markets_routes
from app.services import rates_service
from app.services.rates_service import RateObservation, RatesService, euribor_from_ecb_csv, irs_from_html

ECB_CSV = """KEY,FREQ,REF_AREA,CURRENCY,PROVIDER_FM,INSTRUMENT_FM,PROVIDER_FM_ID,DATA_TYPE_FM,TIME_PERIOD,OBS_VALUE,OBS_STATUS
FM.M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA,M,U2,EUR,RT,MM,EURIBOR3MD_,HSTA,2026-08,2.031,A
FM.M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA,M,U2,EUR,RT,MM,EURIBOR3MD_,HSTA,2026-09,2.012,A
FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA,M,U2,EUR,RT,MM,EURIBOR1YD_,HSTA,2026-09,2.205,A
FM.M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA,M,U2,EUR,RT,MM,EURIBOR6MD_,HSTA,2026-09,,A
"""

IRS_PAGE = """
<html><head><style>.x{color:red}</style></head><body>
<h2>IRS oggi, aggiornato al 23/10/2026</h2>
<table>
<tr><th>Durata</th><th>23/10/2026</th></tr>
<tr><td>IRS 5 anni</td><td>2,31&nbsp;%</td></tr>
<tr><td>IRS 10 anni</td><td>2,74%</td></tr>
<tr><td>Eurirs 20 anni</td><td>2.95</td></tr>
</table>
<p>Storico: IRS 10 anni 2,70 il 22/10/2026</p>
</body></html>
"""


def test_euribor_from_ecb_csv_takes_latest_and_previous_month():
    rates = euribor_from_ecb_csv(ECB_CSV)

    assert rates["EURIBOR3M"] == RateObservation(value=2.012, previous=2.031, period_label="Media di settembre 2026")
    assert rates["EURIBOR12M"].previous is None
    # Tenors without an observation value are left out.
    assert "EURIBOR6M" not in rates
    assert "EURIBOR1M" not in rates


def test_irs_from_html_reads_rows_and_previous_values():
    rates = irs_from_html(IRS_PAGE)

    assert rates["IRS5Y"] == RateObservation(value=2.31, previous=None, period_label="Rilevazione del 23/10/2026")
    assert rates["IRS10Y"].value == 2.74
    assert rates["IRS10Y"].previous == 2.70
    assert rates["IRS20Y"].value == 2.95
    assert "IRS30Y" not in rates


def test_irs_from_html_without_rates():
    assert irs_from_html("<p>Pagina in manutenzione</p>") == {}


def test_rates_service_builds_rate_items_in_percentage_points():
    service = RatesService(
        euribor_fetcher=lambda: {"EURIBOR3M": RateObservation(2.012, 2.031, "Media di settembre 2026")},
        irs_fetcher=lambda: {"IRS10Y": RateObservation(2.74, None, None)},
        irs_source_label=lambda: "example.it",
    )

    items = {item.symbol: item for item in service.get_items()}

    assert [item.symbol for item in service.get_items()] == [
        "EURIBOR1M", "EURIBOR3M", "EURIBOR6M", "EURIBOR12M", "IRS5Y", "IRS10Y", "IRS20Y", "IRS30Y",
    ]
    euribor = items["EURIBOR3M"]
    assert euribor.kind == "rate"
    assert euribor.price == 2.012
    assert euribor.change == -0.019
    assert euribor.change_pct is None
    assert euribor.price_source == "BCE"
    assert euribor.warning == "Media di settembre 2026"
    assert items["IRS10Y"].price_source == "example.it"
    assert items["IRS10Y"].change is None
    assert items["EURIBOR1M"].price is None
    assert items["EURIBOR1M"].error == "Tasso non disponibile"


def test_rates_service_keeps_last_rates_after_a_failure(monkeypatch):
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(rates_service._time, "monotonic", lambda: clock.now)
    calls = {"euribor": 0, "irs": 0}

    def euribor():
        calls["euribor"] += 1
        if calls["euribor"] > 1:
            raise RuntimeError("ECB HTTP 503")
        return {"EURIBOR3M": RateObservation(2.0, None, "Media di settembre 2026")}

    def irs():
        calls["irs"] += 1
        raise RuntimeError("no IRS rate found on the page")

    service = RatesService(euribor_fetcher=euribor, irs_fetcher=irs, irs_source_label=lambda: None)

    items = {item.symbol: item for item in service.get_items()}
    assert items["EURIBOR3M"].price == 2.0
    assert items["IRS10Y"].error == "IRS non disponibile"

    # Cached: no new fetch of Euribor, and IRS waits for the retry delay.
    service.get_items()
    assert calls == {"euribor": 1, "irs": 1}

    clock.now += rates_service.CACHE_TTL_SECONDS + 1
    items = {item.symbol: item for item in service.get_items()}
    assert calls == {"euribor": 2, "irs": 2}
    assert items["EURIBOR3M"].price == 2.0
    assert items["EURIBOR3M"].warning == "Media di settembre 2026 · dato non aggiornato"


def test_market_quotes_route_appends_rates_category():
    class _Finance:
        def get_market_quote(self, symbol):
            return SimpleNamespace(price=10.0, previous_close=9.0, ts=datetime(2026, 10, 23, tzinfo=UTC))

        def get_intraday_bars(self, symbol):
            return []

    service = RatesService(
        euribor_fetcher=lambda: {"EURIBOR3M": RateObservation(2.012, 2.031, None)},
        irs_fetcher=lambda: {},
        irs_source_label=lambda: None,
    )
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_markets_routes(router, repo=object(), finance_client=_Finance(), rates_service=service)
    app.include_router(router)

    payload = TestClient(app).get("/api/markets/quotes").json()

    rates = payload["categories"][-1]
    assert rates["category"] == "rates"
    assert rates["label"] == "Tassi"
    euribor = next(item for item in rates["items"] if item["symbol"] == "EURIBOR3M")
    assert euribor["kind"] == "rate"
    assert euribor["price"] == 2.012
    assert payload["categories"][0]["items"][0]["kind"] == "price"
