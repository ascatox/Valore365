"""Interest rates of the Markets tab: Euribor and IRS (Eurirs).

Euribor comes from the ECB data portal, which publishes the monthly average of
each tenor (the daily fixings are licensed by EMMI). IRS has no free official
feed: the rates are read from a public web page (``irs_rates_url``) that lists
rows such as "IRS 10 anni 2,74". A failed fetch keeps the rates of the last
successful one; without any, the items carry the error and no rate.
"""

import csv
import html
import io
import logging
import re
import threading
import time as _time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from ..models import MarketQuoteItem

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 6 * 3600.0
# After a failure, retry on the next request past this delay rather than on
# the request of every user.
RETRY_AFTER_FAILURE_SECONDS = 300.0

# (symbol, ECB series code, name)
EURIBOR_TENORS: list[tuple[str, str, str]] = [
    ("EURIBOR1M", "EURIBOR1MD_", "Euribor 1 mese"),
    ("EURIBOR3M", "EURIBOR3MD_", "Euribor 3 mesi"),
    ("EURIBOR6M", "EURIBOR6MD_", "Euribor 6 mesi"),
    ("EURIBOR12M", "EURIBOR1YD_", "Euribor 12 mesi"),
]
# (symbol, years, name)
IRS_TENORS: list[tuple[str, int, str]] = [
    ("IRS5Y", 5, "IRS 5 anni"),
    ("IRS10Y", 10, "IRS 10 anni"),
    ("IRS20Y", 20, "IRS 20 anni"),
    ("IRS30Y", 30, "IRS 30 anni"),
]

_MONTHS_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
# "IRS 10 anni 2,74", "Eurirs 10 anni: 2.740%", "IRS 10A | 2,74 %"
_IRS_ROW_RE = re.compile(
    r"\b(?:irs|eurirs)\s*(\d{1,2})\s*(?:anni|a|y)\b[^0-9+\-]{0,40}([+\-]?\d{1,2}[.,]\d{1,4})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b")
_TAG_RE = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class RateObservation:
    value: float
    previous: float | None
    # Human readable period of the value, e.g. "Media di settembre 2026".
    period_label: str | None


RatesFetcher = Callable[[], dict[str, RateObservation]]


def _parse_rate(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def euribor_from_ecb_csv(text: str) -> dict[str, RateObservation]:
    """Latest and previous monthly average of each Euribor tenor, by symbol."""
    by_series: dict[str, list[tuple[str, float]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        series = (row.get("PROVIDER_FM_ID") or "").strip()
        period = (row.get("TIME_PERIOD") or "").strip()
        value = _parse_rate((row.get("OBS_VALUE") or "").strip())
        if series and period and value is not None:
            by_series.setdefault(series, []).append((period, value))

    rates: dict[str, RateObservation] = {}
    for symbol, series, _name in EURIBOR_TENORS:
        observations = sorted(by_series.get(series, []))
        if not observations:
            continue
        period, value = observations[-1]
        previous = observations[-2][1] if len(observations) > 1 else None
        rates[symbol] = RateObservation(value=value, previous=previous, period_label=_monthly_label(period))
    return rates


def _monthly_label(period: str) -> str:
    try:
        year, month = (int(part) for part in period.split("-")[:2])
        return f"Media di {_MONTHS_IT[month - 1]} {year}"
    except (ValueError, IndexError):
        return f"Media {period}"


def irs_from_html(page: str) -> dict[str, RateObservation]:
    """IRS rates of a page listing them as "IRS <years> anni <rate>".

    The first rate found for a tenor is the latest; a second one, as in a table
    of past days, is taken as the previous value.
    """
    text = html.unescape(_TAG_RE.sub(" ", page))
    text = re.sub(r"\s+", " ", text)
    found: dict[int, list[float]] = {}
    for match in _IRS_ROW_RE.finditer(text):
        value = _parse_rate(match.group(2))
        if value is None or not -5 < value < 20:
            continue
        found.setdefault(int(match.group(1)), []).append(value)

    as_of = _latest_date(text)
    period_label = f"Rilevazione del {as_of.strftime('%d/%m/%Y')}" if as_of else None
    rates: dict[str, RateObservation] = {}
    for symbol, years, _name in IRS_TENORS:
        values = found.get(years)
        if values:
            rates[symbol] = RateObservation(
                value=values[0],
                previous=values[1] if len(values) > 1 else None,
                period_label=period_label,
            )
    return rates


def _latest_date(text: str) -> date | None:
    dates: list[date] = []
    for day, month, year in _DATE_RE.findall(text):
        try:
            dates.append(date(int(year), int(month), int(day)))
        except ValueError:
            continue
    today = date.today()
    dates = [d for d in dates if d <= today]
    return max(dates) if dates else None


def fetch_ecb_euribor() -> dict[str, RateObservation]:
    settings = get_settings()
    series = "+".join(code for _symbol, code, _name in EURIBOR_TENORS)
    response = httpx.get(
        f"{settings.ecb_data_api_base_url.rstrip('/')}/data/FM/M.U2.EUR.RT.MM.{series}.HSTA",
        params={"lastNObservations": 2, "format": "csvdata"},
        timeout=settings.rates_timeout_seconds,
        follow_redirects=True,
    )
    if response.status_code != 200:
        raise RuntimeError(f"ECB HTTP {response.status_code}")
    rates = euribor_from_ecb_csv(response.text)
    if not rates:
        raise RuntimeError("ECB returned no Euribor observations")
    return rates


def fetch_web_irs() -> dict[str, RateObservation]:
    settings = get_settings()
    if not settings.irs_rates_url.strip():
        raise RuntimeError("IRS source not configured")
    response = httpx.get(
        settings.irs_rates_url.strip(),
        headers={"User-Agent": "Mozilla/5.0 (compatible; Valore365)"},
        timeout=settings.rates_timeout_seconds,
        follow_redirects=True,
    )
    if response.status_code != 200:
        raise RuntimeError(f"IRS page HTTP {response.status_code}")
    rates = irs_from_html(response.text)
    if not rates:
        raise RuntimeError("no IRS rate found on the page")
    return rates


def _irs_source_label() -> str | None:
    host = urlparse(get_settings().irs_rates_url.strip()).hostname
    return host.removeprefix("www.") if host else None


class _CachedRates:
    def __init__(self, fetcher: RatesFetcher, name: str) -> None:
        self._fetcher = fetcher
        self._name = name
        self._lock = threading.Lock()
        self._rates: dict[str, RateObservation] = {}
        self._error: str | None = None
        self._next_fetch_at = 0.0

    def get(self) -> tuple[dict[str, RateObservation], str | None]:
        with self._lock:
            now = _time.monotonic()
            if now >= self._next_fetch_at:
                try:
                    self._rates = self._fetcher()
                    self._error = None
                    self._next_fetch_at = now + CACHE_TTL_SECONDS
                except Exception as exc:
                    logger.warning("%s rates fetch failed: %s", self._name, exc)
                    self._error = f"{self._name} non disponibile"
                    self._next_fetch_at = now + RETRY_AFTER_FAILURE_SECONDS
            return self._rates, self._error


class RatesService:
    def __init__(
        self,
        euribor_fetcher: RatesFetcher = fetch_ecb_euribor,
        irs_fetcher: RatesFetcher = fetch_web_irs,
        irs_source_label: Callable[[], str | None] = _irs_source_label,
    ) -> None:
        self._euribor = _CachedRates(euribor_fetcher, "Euribor")
        self._irs = _CachedRates(irs_fetcher, "IRS")
        self._irs_source_label = irs_source_label

    def get_items(self) -> list[MarketQuoteItem]:
        euribor, euribor_error = self._euribor.get()
        irs, irs_error = self._irs.get()
        items = [
            _rate_item(symbol, name, euribor.get(symbol), euribor_error, "BCE")
            for symbol, _code, name in EURIBOR_TENORS
        ]
        irs_source = self._irs_source_label()
        items += [_rate_item(symbol, name, irs.get(symbol), irs_error, irs_source) for symbol, _years, name in IRS_TENORS]
        return items


def _rate_item(
    symbol: str,
    name: str,
    observation: RateObservation | None,
    fetch_error: str | None,
    source: str | None,
) -> MarketQuoteItem:
    if observation is None:
        return MarketQuoteItem(
            symbol=symbol,
            name=name,
            kind="rate",
            error=fetch_error or "Tasso non disponibile",
            price_source=source,
            is_realtime=False,
        )
    change = round(observation.value - observation.previous, 4) if observation.previous is not None else None
    return MarketQuoteItem(
        symbol=symbol,
        name=name,
        kind="rate",
        price=observation.value,
        previous_close=observation.previous,
        change=change,
        price_source=source,
        is_realtime=False,
        # The last good rates are still served while the source is failing.
        warning=" · ".join(part for part in (observation.period_label, fetch_error and "dato non aggiornato") if part) or None,
    )
