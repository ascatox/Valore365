"""Upcoming market events for the Markets tab: central banks, big earnings, macro data.

Central bank decisions come from the static calendar in constants/market_calendar;
earnings and economic releases come from Yahoo's calendars through yfinance. A
provider failure only drops its own category and is reported as a warning.
"""

import logging
import re
import threading
import time as _time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..constants.market_calendar import (
    BIG_TECH_SYMBOLS,
    CENTRAL_BANK_CALENDAR_YEARS,
    CENTRAL_BANKS,
    EARNINGS_HIGH_IMPACT_MARKET_CAP_USD,
    EARNINGS_MIN_MARKET_CAP_USD,
    EURO_AREA_REGIONS,
    MACRO_EVENT_RULES,
)
from ..models import MarketCalendarDay, MarketCalendarEvent, MarketCalendarResponse

logger = logging.getLogger(__name__)

CALENDAR_TZ_NAME = "Europe/Rome"
CALENDAR_TZ = ZoneInfo(CALENDAR_TZ_NAME)
_NEW_YORK_TZ = ZoneInfo("America/New_York")

CACHE_TTL_SECONDS = 1800.0
# A response missing a category is retried sooner.
DEGRADED_CACHE_TTL_SECONDS = 120.0

# Yahoo caps a calendar page at 100 rows. Economic releases cover every country
# and come newest first, so a busy week takes several pages to reach today.
_YAHOO_PAGE_SIZE = 100
_ECONOMIC_MAX_PAGES = 10

_EARNINGS_TIMING_HINTS = {
    "BMO": "Prima dell'apertura USA",
    "AMC": "Dopo la chiusura USA",
}
_BIG_TECH_DESCRIPTION = (
    "Tra i pesi massimi di S&P 500 e Nasdaq, e quindi degli ETF azionari globali: "
    "i conti possono muovere l'intero mercato."
)
_COMPANY_SUFFIX_RE = re.compile(
    r",?\s+(inc\.?|corporation|corp\.?|company|co\.?|n\.v\.|se|plc|ltd\.?|limited|s\.a\.|ag)$",
    re.IGNORECASE,
)
_IMPORTANCE_RANK = {"high": 0, "medium": 1}


@dataclass(frozen=True)
class EarningsRow:
    symbol: str
    company: str | None
    market_cap: float | None
    starts_at: datetime | None
    timing: str | None
    eps_estimate: float | None
    eps_actual: float | None


@dataclass(frozen=True)
class EconomicRow:
    name: str
    region: str | None
    starts_at: datetime | None
    period: str | None
    expected: float | None
    previous: float | None
    actual: float | None


EarningsFetcher = Callable[[date, date], list[EarningsRow]]
EconomicFetcher = Callable[[date, date], list[EconomicRow]]


def upcoming_trading_days(today: date, count: int) -> list[date]:
    """The next ``count`` weekdays, today included. Exchange holidays are not skipped."""
    days: list[date] = []
    current = today
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def central_bank_events(days: list[date]) -> list[MarketCalendarEvent]:
    wanted = set(days)
    events: list[MarketCalendarEvent] = []
    for bank_key, bank in CENTRAL_BANKS.items():
        hour, minute = bank["decision_time"]
        for decision_day, has_projections in bank["decision_days"].items():
            if decision_day not in wanted:
                continue
            starts_at = datetime.combine(decision_day, time(hour, minute), tzinfo=ZoneInfo(bank["tz"]))
            description = bank["description"]
            tags: list[str] = []
            if has_projections:
                description = f"{description} {bank['projections_note']}"
                tags.append(bank["projections_tag"])
            events.append(MarketCalendarEvent(
                id=f"{bank_key}-{decision_day.isoformat()}",
                category="central_bank",
                importance="high",
                title=bank["title"],
                description=description,
                day=decision_day,
                starts_at=starts_at.astimezone(UTC),
                region=bank["region"],
                tags=tags,
            ))
    return events


def earnings_events(rows: list[EarningsRow], days: list[date]) -> list[MarketCalendarEvent]:
    wanted = set(days)
    seen: set[tuple[str, date]] = set()
    events: list[MarketCalendarEvent] = []
    # Largest first, so the share class kept for a company is the one Yahoo ranks highest.
    for row in sorted(rows, key=lambda r: -(r.market_cap or 0.0)):
        if row.starts_at is None:
            continue
        is_big_tech = row.symbol in BIG_TECH_SYMBOLS
        if not is_big_tech and (row.market_cap or 0.0) < EARNINGS_MIN_MARKET_CAP_USD:
            continue
        starts_at: datetime | None = row.starts_at
        if starts_at.astimezone(UTC).time() == time(0, 0):
            # Midnight UTC is how Yahoo stores a bare date: keep the day, drop the time.
            day = starts_at.astimezone(UTC).date()
            starts_at = None
        else:
            day = starts_at.astimezone(_NEW_YORK_TZ).date()
        if day not in wanted:
            continue
        company = _short_company_name(row.company) or row.symbol
        dedupe_key = (company.lower(), day)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        high_impact = is_big_tech or (row.market_cap or 0.0) >= EARNINGS_HIGH_IMPACT_MARKET_CAP_USD
        events.append(MarketCalendarEvent(
            id=f"earnings-{row.symbol}-{day.isoformat()}",
            category="earnings",
            importance="high" if high_impact else "medium",
            title=f"Trimestrale {company}",
            description=_BIG_TECH_DESCRIPTION if is_big_tech else None,
            day=day,
            starts_at=starts_at,
            time_hint=_EARNINGS_TIMING_HINTS.get((row.timing or "").upper()),
            region="US",
            tags=["Big Tech"] if is_big_tech else [],
            symbol=row.symbol,
            company=row.company,
            market_cap=row.market_cap,
            eps_estimate=row.eps_estimate,
            eps_actual=row.eps_actual,
        ))
    return events


def macro_events(rows: list[EconomicRow], days: list[date]) -> list[MarketCalendarEvent]:
    wanted = set(days)
    rules = [(rule, re.compile(rule["pattern"], re.IGNORECASE)) for rule in MACRO_EVENT_RULES]
    # One event per (rule, day): a release usually comes in several variants
    # (headline/core, m/m and y/y) and only the headline one is kept.
    picked: dict[tuple[str, date], tuple[tuple[int, int], EconomicRow, dict]] = {}
    for row in rows:
        if row.starts_at is None:
            continue
        region = (row.region or "").upper()
        rule = next((r for r, pattern in rules if region in r["regions"] and pattern.search(row.name)), None)
        if rule is None:
            continue
        day = row.starts_at.astimezone(CALENDAR_TZ).date()
        if day not in wanted:
            continue
        key = (rule["key"], day)
        rank = _release_rank(row.name)
        if key not in picked or rank < picked[key][0]:
            picked[key] = (rank, row, rule)

    events: list[MarketCalendarEvent] = []
    for (rule_key, day), (_rank, row, rule) in picked.items():
        region = (row.region or "").upper()
        events.append(MarketCalendarEvent(
            id=f"macro-{rule_key}-{day.isoformat()}",
            category="macro",
            importance=rule["importance"],
            title=rule["title"],
            description=rule["description"],
            day=day,
            starts_at=row.starts_at.astimezone(UTC),
            region="EU" if region in EURO_AREA_REGIONS else region or None,
            source_name=row.name,
            period=row.period,
            expected=row.expected,
            previous=row.previous,
            actual=row.actual,
        ))
    return events


def _release_rank(name: str) -> tuple[int, int]:
    lowered = name.lower()
    is_secondary = any(word in lowered for word in ("core", "deflator", "price index"))
    is_yearly = any(word in lowered for word in ("yy", "y/y", "yoy", "annual"))
    return (1 if is_secondary else 0, 0 if is_yearly else 1)


def _short_company_name(name: str | None) -> str | None:
    if not name:
        return None
    short = name.strip()
    while True:
        trimmed = _COMPANY_SUFFIX_RE.sub("", short).strip().rstrip(",")
        if trimmed == short or not trimmed:
            return short
        short = trimmed


def _sort_key(event: MarketCalendarEvent) -> tuple:
    starts_at = event.starts_at or datetime.max.replace(tzinfo=UTC)
    return (_IMPORTANCE_RANK[event.importance], starts_at, event.title)


# ---------------------------------------------------------------------------
# Yahoo calendars (yfinance)
# ---------------------------------------------------------------------------

def _yahoo_calendars(start: date, end: date):
    import yfinance as yf

    if not hasattr(yf, "Calendars"):
        raise RuntimeError("installed yfinance has no Calendars API")
    # Yahoo filters with startdatetime <= end, so the last day needs the next midnight.
    return yf.Calendars(start=start, end=end + timedelta(days=1))


def fetch_yahoo_earnings(start: date, end: date) -> list[EarningsRow]:
    frame = _yahoo_calendars(start, end).get_earnings_calendar(
        market_cap=EARNINGS_MIN_MARKET_CAP_USD,
        filter_most_active=False,
        limit=_YAHOO_PAGE_SIZE,
    )
    return earnings_rows_from_frame(frame)


def fetch_yahoo_economic_events(start: date, end: date) -> list[EconomicRow]:
    calendars = _yahoo_calendars(start, end)
    rows: list[EconomicRow] = []
    for page in range(_ECONOMIC_MAX_PAGES):
        frame = calendars.get_economic_events_calendar(limit=_YAHOO_PAGE_SIZE, offset=page * _YAHOO_PAGE_SIZE)
        rows.extend(economic_rows_from_frame(frame))
        if frame is None or len(frame) < _YAHOO_PAGE_SIZE:
            break
    else:
        logger.warning("Economic calendar for %s..%s truncated at %d releases", start, end, len(rows))
    return rows


def earnings_rows_from_frame(frame: pd.DataFrame | None) -> list[EarningsRow]:
    """Rows of ``yf.Calendars.get_earnings_calendar`` (indexed by symbol)."""
    if frame is None or frame.empty:
        return []
    rows: list[EarningsRow] = []
    for symbol, record in frame.iterrows():
        clean_symbol = _clean_str(symbol)
        if not clean_symbol:
            continue
        rows.append(EarningsRow(
            symbol=clean_symbol.upper(),
            company=_clean_str(record.get("Company")),
            market_cap=_clean_float(record.get("Marketcap")),
            starts_at=_clean_datetime(record.get("Event Start Date")),
            timing=_clean_str(record.get("Timing")),
            eps_estimate=_clean_float(record.get("EPS Estimate")),
            eps_actual=_clean_float(record.get("Reported EPS")),
        ))
    return rows


def economic_rows_from_frame(frame: pd.DataFrame | None) -> list[EconomicRow]:
    """Rows of ``yf.Calendars.get_economic_events_calendar`` (indexed by event name)."""
    if frame is None or frame.empty:
        return []
    rows: list[EconomicRow] = []
    for name, record in frame.iterrows():
        clean_name = _clean_str(name)
        if not clean_name:
            continue
        rows.append(EconomicRow(
            name=clean_name,
            region=_clean_str(record.get("Region")),
            starts_at=_clean_datetime(record.get("Event Time")),
            period=_clean_str(record.get("For")) or _clean_str(record.get("Period")),
            expected=_clean_float(record.get("Expected")),
            previous=_clean_float(record.get("Last")),
            actual=_clean_float(record.get("Actual")),
        ))
    return rows


def _clean_str(value: Any) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _clean_datetime(value: Any) -> datetime | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime().astimezone(UTC)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MarketCalendarService:
    def __init__(
        self,
        earnings_fetcher: EarningsFetcher = fetch_yahoo_earnings,
        economic_fetcher: EconomicFetcher = fetch_yahoo_economic_events,
        clock: Callable[[], float] = _time.monotonic,
    ) -> None:
        self._earnings_fetcher = earnings_fetcher
        self._economic_fetcher = economic_fetcher
        self._clock = clock
        self._cache: dict[tuple[date, int], tuple[float, MarketCalendarResponse]] = {}
        self._cache_lock = threading.Lock()

    def get_calendar(self, trading_days: int, today: date | None = None) -> MarketCalendarResponse:
        today = today or datetime.now(CALENDAR_TZ).date()
        key = (today, trading_days)
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] > self._clock():
                return cached[1]

        response, complete = self._build(today, trading_days)
        ttl = CACHE_TTL_SECONDS if complete else DEGRADED_CACHE_TTL_SECONDS
        now = self._clock()
        with self._cache_lock:
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            self._cache[key] = (now + ttl, response)
        return response

    def _build(self, today: date, trading_days: int) -> tuple[MarketCalendarResponse, bool]:
        days = upcoming_trading_days(today, trading_days)
        start, end = days[0], days[-1]
        warnings: list[str] = []
        complete = True

        events = central_bank_events(days)
        uncovered_years = sorted({d.year for d in days} - CENTRAL_BANK_CALENDAR_YEARS)
        if uncovered_years:
            years = ", ".join(str(year) for year in uncovered_years)
            warnings.append(f"Calendario delle riunioni Fed e BCE non ancora disponibile per il {years}.")

        with ThreadPoolExecutor(max_workers=2) as executor:
            earnings_future = executor.submit(self._earnings_fetcher, start, end)
            economic_future = executor.submit(self._economic_fetcher, start, end)

        try:
            events.extend(earnings_events(earnings_future.result(), days))
        except Exception as exc:
            logger.warning("Earnings calendar unavailable for %s..%s: %s", start, end, exc)
            warnings.append("Calendario delle trimestrali momentaneamente non disponibile.")
            complete = False
        try:
            events.extend(macro_events(economic_future.result(), days))
        except Exception as exc:
            logger.warning("Economic calendar unavailable for %s..%s: %s", start, end, exc)
            warnings.append("Calendario dei dati macroeconomici momentaneamente non disponibile.")
            complete = False

        by_day: dict[date, list[MarketCalendarEvent]] = {d: [] for d in days}
        for event in events:
            by_day[event.day].append(event)
        response = MarketCalendarResponse(
            start_date=start,
            end_date=end,
            timezone=CALENDAR_TZ_NAME,
            days=[MarketCalendarDay(day=d, events=sorted(by_day[d], key=_sort_key)) for d in days],
            warnings=warnings,
            generated_at=datetime.now(UTC),
        )
        return response, complete
