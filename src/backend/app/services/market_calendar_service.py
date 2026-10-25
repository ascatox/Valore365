"""Upcoming market events for the Markets tab: central banks, big earnings, macro data.

Central bank decisions come from the static calendar in constants/market_calendar;
earnings and economic releases come from Yahoo's calendars through yfinance. A
provider failure keeps the rows of the last successful fetch for the same window
or, failing that, drops its own category with a warning. When the earnings
calendar fails, Big Tech earnings dates are looked up one symbol at a time.
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
    BIG_TECH_COMPANIES,
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

# Provider rows are fetched once for the widest window the outlook offers and
# shared by every shorter one.
MAX_TRADING_DAYS = 5
CACHE_TTL_SECONDS = 1800.0
# After a provider failure, retry on the next request past this delay rather
# than on every request, which would keep a Yahoo rate limit going.
RETRY_AFTER_FAILURE_SECONDS = 300.0
# Earnings dates rarely move, so the per-symbol Big Tech lookups last longer.
WATCHLIST_CACHE_TTL_SECONDS = 12 * 3600.0

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


_watchlist_cache: dict[str, tuple[float, EarningsRow | None]] = {}
_watchlist_cache_lock = threading.Lock()


def fetch_yahoo_watchlist_earnings(start: date, end: date) -> list[EarningsRow]:
    """Big Tech earnings dates one symbol at a time, through Yahoo's quoteSummary
    (the endpoint behind asset details) rather than its earnings calendar."""
    import yfinance as yf

    def fetch_one(symbol: str) -> EarningsRow | None:
        with _watchlist_cache_lock:
            cached = _watchlist_cache.get(symbol)
        if cached is not None and cached[0] > _time.monotonic():
            return cached[1]
        calendar = yf.Ticker(symbol).calendar
        if not calendar:
            # yfinance logs Yahoo errors (e.g. 401 Invalid Crumb) and returns an
            # empty calendar: a failure, not a company without a date.
            raise RuntimeError(f"no calendar data for {symbol}")
        row = watchlist_row_from_calendar(symbol, BIG_TECH_COMPANIES[symbol], calendar)
        with _watchlist_cache_lock:
            _watchlist_cache[symbol] = (_time.monotonic() + WATCHLIST_CACHE_TTL_SECONDS, row)
        return row

    # One symbol first: when Yahoo rejects the session (no crumb) every lookup
    # fails the same way, and sending all of them only feeds the rate limit.
    probe, *others = BIG_TECH_COMPANIES
    found = [fetch_one(probe)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {symbol: executor.submit(fetch_one, symbol) for symbol in others}
    for symbol, future in futures.items():
        try:
            found.append(future.result())
        except Exception as exc:
            logger.debug("Earnings date unavailable for %s: %s", symbol, exc)
    return [row for row in found if row is not None and start <= row.starts_at.date() <= end]


def watchlist_row_from_calendar(symbol: str, company: str, calendar: dict | None) -> EarningsRow | None:
    """Row for a ``yf.Ticker.calendar`` dict, or None without a single announced
    date: two dates are Yahoo's estimated window, not the actual day."""
    calendar = calendar or {}
    days = {
        value.date() if isinstance(value, datetime) else value
        for value in calendar.get("Earnings Date") or []
        if isinstance(value, date)
    }
    if len(days) != 1:
        return None
    [day] = days
    return EarningsRow(
        symbol=symbol,
        company=company,
        market_cap=None,
        # Midnight UTC marks a bare date, as in Yahoo's earnings calendar.
        starts_at=datetime.combine(day, time(0, 0), tzinfo=UTC),
        timing=None,
        eps_estimate=_clean_float(calendar.get("Earnings Average")),
        eps_actual=None,
    )


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

@dataclass(frozen=True)
class _ProviderRows:
    expires_at: float
    # None when the category could not be fetched.
    earnings: list[EarningsRow] | None
    # False when the earnings come from the Big Tech lookups only.
    earnings_complete: bool
    economic: list[EconomicRow] | None


class MarketCalendarService:
    def __init__(
        self,
        earnings_fetcher: EarningsFetcher = fetch_yahoo_earnings,
        economic_fetcher: EconomicFetcher = fetch_yahoo_economic_events,
        fallback_earnings_fetcher: EarningsFetcher = fetch_yahoo_watchlist_earnings,
        clock: Callable[[], float] = _time.monotonic,
    ) -> None:
        self._earnings_fetcher = earnings_fetcher
        self._economic_fetcher = economic_fetcher
        self._fallback_earnings_fetcher = fallback_earnings_fetcher
        self._clock = clock
        self._rows: dict[date, _ProviderRows] = {}
        self._rows_lock = threading.Lock()

    def get_calendar(self, trading_days: int, today: date | None = None) -> MarketCalendarResponse:
        today = today or datetime.now(CALENDAR_TZ).date()
        window = upcoming_trading_days(today, max(trading_days, MAX_TRADING_DAYS))
        rows = self._provider_rows(today, window)
        return self._build(window[:trading_days], rows)

    def _provider_rows(self, today: date, window: list[date]) -> _ProviderRows:
        with self._rows_lock:
            cached = self._rows.get(today)
        if cached is not None and cached.expires_at > self._clock():
            return cached

        start, end = window[0], window[-1]
        with ThreadPoolExecutor(max_workers=2) as executor:
            earnings_future = executor.submit(self._fetch_earnings, start, end)
            economic_future = executor.submit(self._fetch_economic, start, end)
        earnings, earnings_complete = earnings_future.result()
        economic = economic_future.result()
        fresh = earnings_complete and economic is not None
        logger.info(
            "Market calendar fetched %s..%s: earnings=%s (%s) economic=%s",
            start,
            end,
            "unavailable" if earnings is None else len(earnings),
            "full calendar" if earnings_complete else "Big Tech only",
            "unavailable" if economic is None else len(economic),
        )

        # A failed refresh keeps what an earlier fetch of the same window got.
        if cached is not None:
            if not earnings_complete and cached.earnings_complete:
                earnings, earnings_complete = cached.earnings, True
            elif earnings is None:
                earnings = cached.earnings
            if economic is None:
                economic = cached.economic

        entry = _ProviderRows(
            expires_at=self._clock() + (CACHE_TTL_SECONDS if fresh else RETRY_AFTER_FAILURE_SECONDS),
            earnings=earnings,
            earnings_complete=earnings_complete,
            economic=economic,
        )
        with self._rows_lock:
            # Earlier days are never asked for again.
            self._rows = {today: entry}
        return entry

    def _fetch_earnings(self, start: date, end: date) -> tuple[list[EarningsRow] | None, bool]:
        try:
            return self._earnings_fetcher(start, end), True
        except Exception as exc:
            logger.warning("Earnings calendar unavailable for %s..%s: %s", start, end, exc)
        try:
            return self._fallback_earnings_fetcher(start, end), False
        except Exception as exc:
            logger.warning("Big Tech earnings dates unavailable for %s..%s: %s", start, end, exc)
            return None, False

    def _fetch_economic(self, start: date, end: date) -> list[EconomicRow] | None:
        try:
            return self._economic_fetcher(start, end)
        except Exception as exc:
            logger.warning("Economic calendar unavailable for %s..%s: %s", start, end, exc)
            return None

    def _build(self, days: list[date], rows: _ProviderRows) -> MarketCalendarResponse:
        warnings: list[str] = []
        events = central_bank_events(days)
        uncovered_years = sorted({d.year for d in days} - CENTRAL_BANK_CALENDAR_YEARS)
        if uncovered_years:
            years = ", ".join(str(year) for year in uncovered_years)
            warnings.append(f"Calendario delle riunioni Fed e BCE non ancora disponibile per il {years}.")

        if rows.earnings is None:
            warnings.append("Calendario delle trimestrali momentaneamente non disponibile.")
        else:
            events.extend(earnings_events(rows.earnings, days))
            if not rows.earnings_complete:
                warnings.append("Calendario completo delle trimestrali non disponibile: sono mostrate solo le Big Tech.")
        if rows.economic is None:
            warnings.append("Calendario dei dati macroeconomici momentaneamente non disponibile.")
        else:
            events.extend(macro_events(rows.economic, days))

        by_day: dict[date, list[MarketCalendarEvent]] = {d: [] for d in days}
        for event in events:
            by_day[event.day].append(event)
        return MarketCalendarResponse(
            start_date=days[0],
            end_date=days[-1],
            timezone=CALENDAR_TZ_NAME,
            days=[MarketCalendarDay(day=d, events=sorted(by_day[d], key=_sort_key)) for d in days],
            warnings=warnings,
            generated_at=datetime.now(UTC),
        )
