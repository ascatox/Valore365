import calendar
import logging
import math
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import TYPE_CHECKING
from urllib.parse import quote as url_quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .errors import ProviderError

if TYPE_CHECKING:
    from .config import Settings

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "UTC"
DEFAULT_ORDER = "asc"


def normalize_expense_ratio_pct(value: float | None) -> float | None:
    """Normalize provider expense ratios to percentage points.

    Providers are inconsistent: some return ``0.13`` for ``0.13%``, while
    others return ``0.0013`` for the same value. We treat tiny values as
    fractions and convert them to percentage points; larger values are assumed
    to already be percentages.
    """
    if value is None or not math.isfinite(value):
        return None
    if value < 0:
        return None
    if value <= 0.01:
        return value * 100
    return value


@dataclass
class ProviderQuote:
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    volume: float | None
    ts: datetime
    source: str = "provider"
    is_realtime: bool = True
    is_fallback: bool = False
    stale: bool = False
    warning: str | None = None
    previous_close: float | None = None


@dataclass
class ProviderDailyBar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@dataclass
class ProviderFxRate:
    day: date
    rate: float


@dataclass
class ProviderSymbol:
    symbol: str
    instrument_name: str | None
    exchange: str | None
    country: str | None


@dataclass
class ProviderMarketQuote:
    symbol: str
    price: float | None
    previous_close: float | None
    ts: datetime
    source: str = "provider"
    is_realtime: bool = True
    is_fallback: bool = False
    stale: bool = False
    warning: str | None = None


@dataclass
class ProviderIntradayBar:
    ts: datetime
    close: float


QUOTE_TYPE_MAP: dict[str, str] = {
    "EQUITY": "stock",
    "ETF": "etf",
    "MUTUALFUND": "fund",
    "BOND": "bond",
    "CRYPTOCURRENCY": "crypto",
    "MONEYMARKET": "cash",
    "INDEX": "etf",
    "COMMODITY": "etf",
}


@dataclass
class ProviderAssetInfo:
    symbol: str
    name: str | None
    sector: str | None
    industry: str | None
    country: str | None
    market_cap: float | None
    trailing_pe: float | None
    forward_pe: float | None
    # Percentage points (6.34 = 6.34%): Yahoo's dividendYield, already a percentage.
    dividend_yield: float | None
    beta: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    avg_volume: float | None
    currency: str | None
    current_price: float | None
    previous_close: float | None
    description: str | None
    quote_type: str | None = None
    # ETF/Fund specific
    expense_ratio: float | None = None
    fund_family: str | None = None
    total_assets: float | None = None
    category: str | None = None
    # Additional stock fields
    dividend_rate: float | None = None
    profit_margins: float | None = None
    return_on_equity: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    website: str | None = None
    logo_url: str | None = None
    # Full raw info dict
    raw_info: dict | None = None
    current_price_source: str | None = None
    metadata_status: str = "complete"
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProviderEtfHolding:
    symbol: str
    name: str
    weight: float  # 0-1 fraction


class TwelveDataClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def search_symbols(self, query: str) -> list[ProviderSymbol]:
        payload = self._request_json(
            '/symbol_search',
            {'symbol': query, 'apikey': self.api_key},
            symbol=query,
        )
        results = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []

        symbols: list[ProviderSymbol] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            symbols.append(
                ProviderSymbol(
                    symbol=item.get('symbol'),
                    instrument_name=item.get('instrument_name'),
                    exchange=item.get('exchange'),
                    country=item.get('country'),
                )
            )
        return symbols

    def get_quote(self, symbol: str) -> ProviderQuote:
        payload = self._request_json('/quote', {'symbol': symbol, 'apikey': self.api_key}, symbol=symbol)
        price = _parse_float(payload, ['price', 'close', 'last'])
        if price is None:
            raise ProviderError(
                provider='twelvedata',
                operation='quote',
                symbol=symbol,
                reason='no_data',
                message=f"Prezzo non disponibile per {symbol}",
            )

        ts = datetime.now(UTC)
        return ProviderQuote(
            symbol=symbol,
            price=price,
            bid=_parse_float(payload, ['bid']),
            ask=_parse_float(payload, ['ask']),
            volume=_parse_float(payload, ['volume']),
            ts=ts,
            source='quote',
        )

    def get_market_quote(self, symbol: str) -> ProviderMarketQuote:
        try:
            quote = self.get_quote(symbol)
            return ProviderMarketQuote(
                symbol=symbol,
                price=quote.price,
                previous_close=None,
                ts=quote.ts,
                source=quote.source,
                is_realtime=quote.is_realtime,
                is_fallback=quote.is_fallback,
                stale=quote.stale,
                warning=quote.warning,
            )
        except Exception:
            return ProviderMarketQuote(
                symbol=symbol,
                price=None,
                previous_close=None,
                ts=datetime.now(UTC),
                source='quote',
                is_realtime=False,
                is_fallback=True,
                stale=True,
                warning='market quote unavailable',
            )

    def get_daily_bars(
        self,
        symbol: str,
        outputsize: int = 365,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        order: str = DEFAULT_ORDER,
    ) -> list[ProviderDailyBar]:
        params: dict[str, object] = {
            'symbol': symbol,
            'interval': '1day',
            'apikey': self.api_key,
            'outputsize': max(1, min(outputsize, 5000)),
            'timezone': timezone,
            'order': order,
        }
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        payload = self._request_json(
            '/time_series',
            params,
            symbol=symbol,
        )
        values = payload.get('values') if isinstance(payload, dict) else None
        if not isinstance(values, list):
            raise ProviderError(
                provider='twelvedata',
                operation='daily_bars',
                symbol=symbol,
                reason='no_data',
                message=f"Serie storica non disponibile per {symbol}",
            )

        bars: list[ProviderDailyBar] = []
        for row in values:
            if not isinstance(row, dict):
                continue
            day = _parse_date(row.get('datetime'))
            if day is None:
                continue
            o = _parse_float(row, ['open'])
            h = _parse_float(row, ['high'])
            l = _parse_float(row, ['low'])
            c = _parse_float(row, ['close'])
            if o is None or h is None or l is None or c is None:
                continue
            bars.append(
                ProviderDailyBar(
                    day=day,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=_parse_float(row, ['volume']),
                )
            )

        bars.sort(key=lambda x: x.day)
        return bars

    def get_daily_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        outputsize: int = 365,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        order: str = DEFAULT_ORDER,
    ) -> list[ProviderFxRate]:
        pair = f"{from_currency}/{to_currency}"
        params: dict[str, object] = {
            'symbol': pair,
            'interval': '1day',
            'apikey': self.api_key,
            'outputsize': max(1, min(outputsize, 5000)),
            'timezone': timezone,
            'order': order,
        }
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        payload = self._request_json(
            '/time_series',
            params,
            symbol=pair,
        )
        values = payload.get('values') if isinstance(payload, dict) else None
        if not isinstance(values, list):
            raise ProviderError(
                provider='twelvedata',
                operation='daily_fx_rates',
                symbol=pair,
                reason='no_data',
                message=f"Serie FX non disponibile per {pair}",
            )

        rates: list[ProviderFxRate] = []
        for row in values:
            if not isinstance(row, dict):
                continue
            day = _parse_date(row.get('datetime'))
            if day is None:
                continue
            close = _parse_float(row, ['close'])
            if close is None:
                continue
            rates.append(ProviderFxRate(day=day, rate=close))

        rates.sort(key=lambda x: x.day)
        return rates

    def _request_json(self, path: str, params: dict, *, symbol: str) -> dict:
        if not self.api_key:
            raise ProviderError(
                provider='twelvedata',
                operation=path.strip('/'),
                symbol=symbol,
                reason='misconfigured',
                message='FINANCE_API_KEY non configurata',
            )

        url = f"{self.base_url}{path}"
        attempt = 0
        last_error: Exception | None = None

        while attempt <= self.max_retries:
            attempt += 1
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(url, params=params)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Retryable status code {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                response.raise_for_status()
                payload = response.json()

                if isinstance(payload, dict) and payload.get('code'):
                    message = payload.get('message', 'Errore provider')
                    raise ProviderError(
                        provider='twelvedata',
                        operation=path.strip('/'),
                        symbol=symbol,
                        reason='provider_error',
                        message=f"Provider error per {symbol}: {message}",
                    )

                if not isinstance(payload, dict):
                    raise ProviderError(
                        provider='twelvedata',
                        operation=path.strip('/'),
                        symbol=symbol,
                        reason='invalid_payload',
                        message=f"Payload non valido per {symbol}",
                    )
                return payload
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt > self.max_retries:
                    break

                delay = _compute_retry_delay(exc, attempt=attempt, backoff_seconds=self.retry_backoff_seconds)
                logger.warning(
                    'Retry provider request symbol=%s attempt=%s/%s delay=%.2fs reason=%s',
                    symbol,
                    attempt,
                    self.max_retries + 1,
                    delay,
                    exc,
                )
                if delay > 0:
                    time.sleep(delay)

        if last_error is not None:
            raise _provider_error('twelvedata', path.strip('/'), symbol, last_error) from last_error
        raise ProviderError(
            provider='twelvedata',
            operation=path.strip('/'),
            symbol=symbol,
            reason='provider_error',
            message=f"Errore provider per {symbol}",
        )


def _parse_float(payload: dict, keys: list[str]) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ''):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _to_utc_datetime(value: object) -> datetime | None:
    """Epoch seconds or a (pandas) datetime, as an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), tz=UTC)
    to_pydatetime = getattr(value, 'to_pydatetime', None)
    moment = to_pydatetime() if to_pydatetime is not None else value
    if not isinstance(moment, datetime):
        return None
    return moment.astimezone(UTC) if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    if len(raw) >= 10:
        raw = raw[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _compute_retry_delay(exc: Exception, *, attempt: int, backoff_seconds: float) -> float:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        retry_after = exc.response.headers.get('Retry-After')
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
    return backoff_seconds * (2 ** max(0, attempt - 1))


_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')


def is_unpriceable_on_yahoo(provider: str, symbol: str) -> bool:
    """True for bare ISINs (e.g. Italian BTPs) that yfinance cannot price.

    yfinance only fails on them ("Invalid ISIN number"), so callers skip the
    request instead of making one that is guaranteed to error out.
    """
    return provider == 'yfinance' and bool(_ISIN_RE.match(symbol.strip().upper())) and symbol.strip()[-1].isdigit()
_OPENFIGI_URL = 'https://api.openfigi.com/v3/mapping'

# Mappa exchCode OpenFIGI (codici Bloomberg 2 lettere) → suffisso Yahoo Finance
_EXCHCODE_TO_YAHOO: dict[str, str] = {
    'GS':  '.DE',   # Xetra / Frankfurt
    'GR':  '.DE',   # Frankfurt Borsa (variante Xetra)
    'GF':  '.F',    # Frankfurt Stock Exchange
    'IM':  '.MI',   # Borsa Italiana
    'FP':  '.PA',   # Euronext Paris
    'NA':  '.AS',   # Euronext Amsterdam
    'LN':  '.L',    # London Stock Exchange
    'SE':  '.SW',   # SIX Swiss Exchange
    'SW':  '.SW',   # SIX Swiss Exchange (variante)
    'SM':  '.MC',   # Madrid
    'FH':  '.HE',   # Helsinki
    'NO':  '.OL',   # Oslo
    'SS':  '.ST',   # Stockholm
    'DC':  '.CO',   # Copenhagen
    'AV':  '.VI',   # Vienna
    'PL':  '.LS',   # Lisbon
    'GA':  '.AT',   # Atene
    'PW':  '.WA',   # Varsavia
    'BB':  '.BR',   # Bruxelles
    'ID':  '.IR',   # Dublino (Euronext)
    'SQ':  '.SG',   # Singapore
    'AU':  '.AX',   # Australia (ASX)
    'JP':  '.T',    # Tokyo
    # US: nessun suffisso (empty string già il default)
    'UN':  '',      # NYSE
    'UW':  '',      # NASDAQ
    'UA':  '',      # NYSE American
    'UR':  '',      # NYSE Arca
    'UF':  '',      # OTC Bulletin Board
}

_YAHOO_SUFFIX_PRIORITY: dict[str, int] = {
    '.AS': 0,
    '.MI': 1,
    '.DE': 2,
    '.PA': 3,
    '.SW': 4,
    '.L': 5,
    '': 6,
}


def _resolve_isin(isin: str) -> list[ProviderSymbol]:
    """Chiama OpenFIGI per risolvere un codice ISIN in simboli Yahoo Finance."""
    try:
        with httpx.Client(timeout=6) as client:
            resp = client.post(
                _OPENFIGI_URL,
                json=[{'idType': 'ID_ISIN', 'idValue': isin}],
                headers={'Content-Type': 'application/json'},
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results: list[ProviderSymbol] = []
        seen: set[str] = set()
        for mapping in data:
            for item in mapping.get('data', []):
                ticker = (item.get('ticker') or '').strip()
                exch = (item.get('exchCode') or '').strip()
                name = item.get('name') or item.get('securityDescription')
                if not ticker:
                    continue
                # Includi solo exchange noti; per US (empty string) va bene comunque
                if exch and exch not in _EXCHCODE_TO_YAHOO:
                    continue
                suffix = _EXCHCODE_TO_YAHOO.get(exch, '')
                yahoo_symbol = f"{ticker}{suffix}"
                if yahoo_symbol in seen:
                    continue
                seen.add(yahoo_symbol)
                label = f"{name} [{exch}]" if name and exch else (name or yahoo_symbol)
                results.append(ProviderSymbol(
                    symbol=yahoo_symbol,
                    instrument_name=label,
                    exchange=exch or None,
                    country=None,
                ))
        return results
    except Exception:
        return []


def resolve_provider_symbol_candidates(symbol: str, isin: str | None) -> list[str]:
    """Return Yahoo symbols for an ISIN ordered by how likely they match the requested symbol."""
    preferred_symbol = symbol.strip().upper()
    normalized_isin = (isin or "").strip().upper()
    if not preferred_symbol or not _ISIN_RE.match(normalized_isin):
        return []

    def _suffix_rank(candidate_symbol: str) -> int:
        if "." not in candidate_symbol:
            return _YAHOO_SUFFIX_PRIORITY[""]
        return _YAHOO_SUFFIX_PRIORITY.get(candidate_symbol[candidate_symbol.index("."):], len(_YAHOO_SUFFIX_PRIORITY) + 1)

    ranked: list[tuple[tuple[int, int, int], str]] = []
    for item in _resolve_isin(normalized_isin):
        candidate = (item.symbol or "").strip().upper()
        if not candidate:
            continue
        candidate_base = candidate.split(".", 1)[0]
        exact_match = 0 if candidate == preferred_symbol else 1
        base_match = 0 if candidate_base == preferred_symbol else 1
        ranked.append(((base_match, exact_match, _suffix_rank(candidate)), candidate))

    ranked.sort(key=lambda item: item[0])

    ordered: list[str] = []
    seen: set[str] = set()
    for _, candidate in ranked:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


YAHOO_CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart'
# Senza un User-Agent da browser Yahoo risponde 429 a prescindere dal traffico.
_YAHOO_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'en-US,en;q=0.9',
}
# Un Retry-After più lungo di così non vale un thread fermo (scheduler o
# threadpool delle route): si rinuncia subito e si riprova al giro successivo.
_YAHOO_MAX_RETRY_DELAY_SECONDS = 10.0
# Stessa regex di yfinance.utils.is_isin: yf.Ticker accettava un ISIN e lo
# risolveva con la ricerca Yahoo prima di chiedere i prezzi.
_YF_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$')
_INTRADAY_INTERVAL_RE = re.compile(r'^(\d+)(m|h)$')

# make_finance_client crea un client per richiesta (pricing_service,
# historical_service, ...): il pool di connessioni sta a livello di modulo così
# sopravvive tra un refresh e l'altro. httpx.Client è thread-safe.
_yahoo_http_client: httpx.Client | None = None
_yahoo_http_client_lock = threading.Lock()
_isin_ticker_cache: dict[str, str] = {}
_isin_ticker_cache_lock = threading.Lock()


def _shared_yahoo_http_client() -> httpx.Client:
    global _yahoo_http_client
    with _yahoo_http_client_lock:
        if _yahoo_http_client is None:
            _yahoo_http_client = httpx.Client(follow_redirects=True)
        return _yahoo_http_client


@dataclass
class _ChartRow:
    """Una riga di chart.result[0], con il timestamp nel fuso della borsa."""

    ts: datetime
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjclose: float | None
    volume: float | None


@dataclass
class _QuoteSnapshot:
    price: float | None
    market_ts: datetime | None
    last_close: float | None
    last_close_ts: datetime | None
    previous_close: float | None


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _exchange_timezone(meta: dict) -> tzinfo:
    name = meta.get('exchangeTimezoneName')
    if isinstance(name, str) and name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    offset = meta.get('gmtoffset')
    if isinstance(offset, int) and not isinstance(offset, bool):
        return timezone(timedelta(seconds=offset))
    return UTC


def _chart_rows(result: dict) -> list[_ChartRow]:
    """Righe del chart ordinate per timestamp; i null di Yahoo diventano None."""
    tz = _exchange_timezone(result.get('meta') or {})
    timestamps = result.get('timestamp') or []
    indicators = result.get('indicators') or {}
    quotes = indicators.get('quote')
    quote = quotes[0] if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict) else {}
    adjclose_list = indicators.get('adjclose')
    adjcloses = None
    if isinstance(adjclose_list, list) and adjclose_list and isinstance(adjclose_list[0], dict):
        adjcloses = adjclose_list[0].get('adjclose')

    def _value(values: object, index: int) -> float | None:
        if not isinstance(values, list) or index >= len(values):
            return None
        return _finite_float(values[index])

    rows: list[_ChartRow] = []
    for index, raw_ts in enumerate(timestamps):
        if isinstance(raw_ts, bool) or not isinstance(raw_ts, (int, float)):
            continue
        close = _value(quote.get('close'), index)
        rows.append(_ChartRow(
            ts=datetime.fromtimestamp(int(raw_ts), tz=tz),
            open=_value(quote.get('open'), index),
            high=_value(quote.get('high'), index),
            low=_value(quote.get('low'), index),
            close=close,
            # Come yfinance: senza la serie adjclose si usano i valori grezzi.
            adjclose=_value(adjcloses, index) if adjcloses is not None else close,
            volume=_value(quote.get('volume'), index),
        ))
    rows.sort(key=lambda row: row.ts)
    return rows


def _bar_day(ts: datetime) -> date:
    """Data di una barra giornaliera nel fuso della borsa (come yfinance).

    Yahoo a volte stampa la mezzanotte locale come 22:00/23:00 del giorno prima
    (problema di ora legale): yfinance (fix_Yahoo_dst_issue) la riporta al giorno dopo.
    """
    if ts.minute == 0 and ts.hour in (22, 23):
        return (ts + timedelta(hours=24 - ts.hour)).date()
    return ts.date()


def _utc_midnight_epoch(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


def _one_month_before(day: date) -> date:
    year, month = (day.year, day.month - 1) if day.month > 1 else (day.year - 1, 12)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _parse_bound_date(value: str | None, *, symbol: str, operation: str) -> date | None:
    if not value:
        return None
    parsed = _parse_date(value)
    if parsed is None:
        raise ProviderError(
            provider='yfinance',
            operation=operation,
            symbol=symbol,
            reason='provider_error',
            message=f"Data non valida per {symbol}: {value}",
        )
    return parsed


def _chart_result(response: httpx.Response, *, symbol: str, operation: str, no_data_message: str) -> dict:
    """chart.result[0] di una risposta Yahoo, oppure ProviderError."""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    chart = payload.get('chart') if isinstance(payload, dict) else None
    error = chart.get('error') if isinstance(chart, dict) else None
    error_code = error.get('code') if isinstance(error, dict) else None
    if response.status_code in (401, 403) or error_code in ('Unauthorized', 'Forbidden'):
        # Yahoo ha rifiutato il client (crumb, blocco IP): non è "nessun dato".
        raise ProviderError(
            provider='yfinance',
            operation=operation,
            symbol=symbol,
            reason='provider_error',
            message=f"yfinance {operation} failed for {symbol}: HTTP {response.status_code} {error_code or ''}".rstrip(),
        )
    if error or response.status_code == 404:
        # {"chart":{"result":null,"error":{"code":"Not Found",...}}}: simbolo
        # sconosciuto/delistato o nessun dato nel periodo. yfinance lo trattava
        # come serie vuota, cioè no_data.
        logger.debug('Yahoo chart error symbol=%s status=%s error=%s', symbol, response.status_code, error)
        raise ProviderError(
            provider='yfinance',
            operation=operation,
            symbol=symbol,
            reason='no_data',
            message=no_data_message,
        )
    if response.status_code >= 400:
        raise ProviderError(
            provider='yfinance',
            operation=operation,
            symbol=symbol,
            reason='provider_error',
            message=f"yfinance {operation} failed for {symbol}: HTTP {response.status_code}",
        )
    if not isinstance(chart, dict):
        raise ProviderError(
            provider='yfinance',
            operation=operation,
            symbol=symbol,
            reason='invalid_payload',
            message=f"Payload non valido per {symbol}",
        )
    results = chart.get('result')
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise ProviderError(
            provider='yfinance',
            operation=operation,
            symbol=symbol,
            reason='no_data',
            message=no_data_message,
        )
    return results[0]


class YahooFinanceClient:
    """Client Yahoo Finance (gratuito, no API key).

    Prezzi e storico (le chiamate frequenti) passano da una sola GET
    all'endpoint chart v8 via httpx; yfinance resta solo per ricerca simboli,
    .info e top holdings ETF, chiamate rare.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.5,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        # Tentativi totali per richiesta (non retry aggiuntivi, a differenza di TwelveDataClient).
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        # Iniettabile nei test (httpx.MockTransport); altrimenti il client condiviso.
        self._http_client = http_client

    def search_symbols(self, query: str) -> list[ProviderSymbol]:
        q = query.strip().upper()
        # Se la query sembra un ISIN, usa OpenFIGI per la risoluzione
        if _ISIN_RE.match(q):
            isin_results = _resolve_isin(q)
            if isin_results:
                return isin_results
        try:
            import yfinance as yf
            results = yf.Search(query, max_results=20).quotes
            return [
                ProviderSymbol(
                    symbol=r.get('symbol', ''),
                    instrument_name=r.get('shortname') or r.get('longname'),
                    exchange=r.get('exchange'),
                    country=None,
                )
                for r in results
                if r.get('symbol')
            ]
        except Exception:
            return []

    def get_quote(self, symbol: str) -> ProviderQuote:
        snapshot = self._quote_snapshot(symbol)
        # 'fast_info' / 'history_close' sono le etichette storiche dell'epoca
        # yfinance: il frontend (dataQuality.ts) le traduce, quindi restano.
        if snapshot.price is None:
            if snapshot.last_close is None:
                raise ProviderError(
                    provider='yfinance',
                    operation='quote',
                    symbol=symbol,
                    reason='no_data',
                    message=f"Nessuna quotazione disponibile per {symbol}",
                )
            return ProviderQuote(
                symbol=symbol,
                price=snapshot.last_close,
                bid=None,
                ask=None,
                volume=None,
                ts=snapshot.last_close_ts or datetime.now(UTC),
                source='history_close',
                is_realtime=False,
                is_fallback=True,
                stale=True,
                warning='realtime quote unavailable; using last close',
                previous_close=snapshot.previous_close,
            )

        return ProviderQuote(
            symbol=symbol,
            price=snapshot.price,
            bid=None,
            ask=None,
            volume=None,
            # Ora del refresh, come con fast_info: price_ticks e il day change
            # (ts::date) si basano su questo valore.
            ts=datetime.now(UTC),
            source='fast_info',
            is_realtime=True,
            is_fallback=False,
            stale=False,
            warning=None,
            previous_close=snapshot.previous_close,
        )

    def get_market_quote(self, symbol: str) -> ProviderMarketQuote:
        try:
            snapshot = self._quote_snapshot(symbol)
        except Exception as exc:
            # Come prima: la quotazione mercati non solleva mai, segnala solo.
            logger.debug('Market quote unavailable symbol=%s error=%s', symbol, exc)
            snapshot = None

        if snapshot is not None and snapshot.price is not None:
            return ProviderMarketQuote(
                symbol=symbol,
                price=snapshot.price,
                previous_close=snapshot.previous_close,
                # Ora dell'ultimo scambio (meta.regularMarketTime), non del refresh.
                ts=snapshot.market_ts or datetime.now(UTC),
                source='fast_info',
                is_realtime=True,
                is_fallback=False,
                stale=False,
                warning=None,
            )
        if snapshot is not None and snapshot.last_close is not None:
            return ProviderMarketQuote(
                symbol=symbol,
                price=snapshot.last_close,
                previous_close=snapshot.previous_close,
                ts=snapshot.market_ts or snapshot.last_close_ts or datetime.now(UTC),
                source='history_close',
                is_realtime=False,
                is_fallback=True,
                stale=True,
                warning='realtime quote unavailable; using last close',
            )
        return ProviderMarketQuote(
            symbol=symbol,
            price=None,
            previous_close=None,
            ts=datetime.now(UTC),
            source='history_close',
            is_realtime=False,
            is_fallback=True,
            stale=True,
            warning='market quote unavailable',
        )

    def get_daily_bars(
        self,
        symbol: str,
        outputsize: int = 365,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        order: str = DEFAULT_ORDER,
    ) -> list[ProviderDailyBar]:
        # outputsize e timezone ignorati, come con yfinance: contano start/end.
        rows = self._daily_rows(
            symbol,
            start_date=start_date,
            end_date=end_date,
            operation='daily_bars',
            no_data_message=f"Nessun dato storico per {symbol}",
        )
        bars_by_day: dict[date, ProviderDailyBar] = {}
        for day, row in rows:
            o, h, l, c, adj = row.open, row.high, row.low, row.close, row.adjclose
            if o is None or h is None or l is None or c is None or adj is None or c == 0:
                continue
            # auto_adjust=True di yfinance: OHLC rettificati per split e
            # dividendi con il rapporto adjclose/close, volume invariato.
            ratio = adj / c
            o, h, l = o * ratio, h * ratio, l * ratio
            if not (math.isfinite(o) and math.isfinite(h) and math.isfinite(l)):
                continue
            # Riga successiva con la stessa data (riga "live" che Yahoo aggiunge
            # a mercato aperto) sostituisce la precedente, come fa yfinance.
            bars_by_day[day] = ProviderDailyBar(
                day=day,
                open=o,
                high=h,
                low=l,
                close=adj,
                # yfinance: Volume.fillna(0).astype(int64).
                volume=float(int(row.volume)) if row.volume is not None else 0.0,
            )
        if not bars_by_day:
            raise ProviderError(
                provider='yfinance',
                operation='daily_bars',
                symbol=symbol,
                reason='no_data',
                message=f"Nessun dato storico per {symbol}",
            )

        bars = sorted(bars_by_day.values(), key=lambda x: x.day)
        if order == 'desc':
            bars.reverse()
        return bars

    def get_asset_info(self, symbol: str) -> ProviderAssetInfo:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        warnings: list[str] = []
        try:
            info = self._ticker_info(ticker, symbol)
        except ProviderError as exc:
            info = {}
            warnings.append(exc.message)

        def _num(key: str) -> float | None:
            v = info.get(key)
            if v is None:
                return None
            try:
                f = float(v)
                return f if math.isfinite(f) else None
            except (TypeError, ValueError):
                return None

        # Build a sanitized copy of raw info (remove non-serializable values)
        raw_clean: dict = {}
        for k, v in info.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                raw_clean[k] = v
            elif isinstance(v, (list, dict)):
                try:
                    import json
                    json.dumps(v)
                    raw_clean[k] = v
                except (TypeError, ValueError):
                    pass

        current_price_source = None
        if _num('currentPrice') is not None:
            current_price_source = 'currentPrice'
        elif _num('regularMarketPrice') is not None:
            current_price_source = 'regularMarketPrice'

        metadata_status = "complete"
        if not info:
            metadata_status = "missing"
        elif not (info.get('longName') or info.get('shortName')) or info.get('quoteType') is None:
            metadata_status = "partial"

        return ProviderAssetInfo(
            symbol=symbol,
            name=info.get('longName') or info.get('shortName'),
            sector=info.get('sector'),
            industry=info.get('industry'),
            country=info.get('country'),
            market_cap=_num('marketCap'),
            trailing_pe=_num('trailingPE'),
            forward_pe=_num('forwardPE'),
            dividend_yield=_num('dividendYield'),
            beta=_num('beta'),
            fifty_two_week_high=_num('fiftyTwoWeekHigh'),
            fifty_two_week_low=_num('fiftyTwoWeekLow'),
            avg_volume=_num('averageVolume'),
            currency=info.get('currency'),
            current_price=_num('currentPrice') or _num('regularMarketPrice'),
            previous_close=_num('previousClose') or _num('regularMarketPreviousClose'),
            description=info.get('longBusinessSummary'),
            quote_type=info.get('quoteType'),
            expense_ratio=normalize_expense_ratio_pct(_num('netExpenseRatio') or _num('expenseRatio')),
            fund_family=info.get('fundFamily'),
            total_assets=_num('totalAssets'),
            category=info.get('category'),
            dividend_rate=_num('dividendRate'),
            profit_margins=_num('profitMargins'),
            return_on_equity=_num('returnOnEquity'),
            revenue_growth=_num('revenueGrowth'),
            earnings_growth=_num('earningsQuarterlyGrowth'),
            website=info.get('website'),
            logo_url=info.get('logo_url'),
            raw_info=raw_clean if raw_clean else None,
            current_price_source=current_price_source,
            metadata_status=metadata_status,
            warnings=warnings,
        )

    def get_etf_top_holdings(self, symbol: str) -> list[ProviderEtfHolding]:
        import yfinance as yf
        try:
            ticker = yf.Ticker(symbol)
            holdings = ticker.funds_data.top_holdings
            if holdings is None or holdings.empty:
                return []
            result = []
            for sym, row in holdings.iterrows():
                weight = row.get("Holding Percent")
                if weight is None:
                    continue
                name = row.get("Name", str(sym))
                result.append(ProviderEtfHolding(
                    symbol=str(sym),
                    name=str(name) if name else str(sym),
                    weight=float(weight),
                ))
            return result
        except Exception:
            logger.debug("Failed to fetch ETF holdings for %s", symbol)
            return []

    def get_intraday_bars(self, symbol: str, period: str = '5d', interval: str = '1h') -> list[ProviderIntradayBar]:
        try:
            result = self._fetch_chart(
                symbol,
                {'range': period, 'interval': interval, 'includePrePost': 'false'},
                operation='intraday_bars',
                no_data_message=f"Nessun dato intraday per {symbol}",
            )
        except ProviderError as exc:
            if exc.reason == 'no_data':
                # Come yfinance: simbolo senza dati = serie vuota, non errore.
                return []
            raise

        # Timestamp nel fuso della borsa (tz-aware), come l'indice di yfinance:
        # routes_markets e _summary li formattano in ora locale.
        bars: list[ProviderIntradayBar] = []
        for row in _chart_rows(result):
            if row.close is None:
                continue
            if bars and bars[-1].ts == row.ts:
                continue
            bars.append(ProviderIntradayBar(ts=row.ts, close=row.close))

        # A mercato aperto Yahoo aggiunge l'ultimo prezzo come riga separata
        # dentro l'intervallo in corso: yfinance la fonde nella barra di quell'intervallo.
        match = _INTRADAY_INTERVAL_RE.match(interval.strip().lower())
        if match and len(bars) >= 2:
            amount, unit = int(match.group(1)), match.group(2)
            step = timedelta(minutes=amount) if unit == 'm' else timedelta(hours=amount)
            if bars[-1].ts - bars[-2].ts < step:
                bars[-2] = ProviderIntradayBar(ts=bars[-2].ts, close=bars[-1].close)
                bars.pop()
        return bars

    def get_daily_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        outputsize: int = 365,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
        order: str = DEFAULT_ORDER,
    ) -> list[ProviderFxRate]:
        # Yahoo: EURUSD=X = quanti USD per 1 EUR
        pair = f"{from_currency}{to_currency}=X"
        rows = self._daily_rows(
            pair,
            start_date=start_date,
            end_date=end_date,
            operation='daily_fx_rates',
            no_data_message=f"Nessun dato FX per {pair}",
        )
        rates_by_day: dict[date, ProviderFxRate] = {}
        for day, row in rows:
            # Chiusura rettificata, come yf.download(auto_adjust=True); per i cambi coincide con close.
            if row.adjclose is None:
                continue
            rates_by_day[day] = ProviderFxRate(day=day, rate=row.adjclose)
        if not rates_by_day:
            raise ProviderError(
                provider='yfinance',
                operation='daily_fx_rates',
                symbol=pair,
                reason='no_data',
                message=f"Nessun dato FX per {pair}",
            )

        rates = sorted(rates_by_day.values(), key=lambda x: x.day)
        if order == 'desc':
            rates.reverse()
        return rates

    def _quote_snapshot(self, symbol: str) -> _QuoteSnapshot:
        """Prezzo, ora dell'ultimo scambio e chiusure da una sola richiesta (5 giorni, barre giornaliere)."""
        result = self._fetch_chart(
            symbol,
            {'range': '5d', 'interval': '1d', 'includePrePost': 'false'},
            operation='quote',
            no_data_message=f"Nessuna quotazione disponibile per {symbol}",
        )
        meta = result.get('meta') or {}
        tz = _exchange_timezone(meta)
        # Chiusure grezze (non rettificate) per giorno di borsa; la riga "live"
        # dello stesso giorno sostituisce la precedente.
        closes: dict[date, float] = {}
        for row in _chart_rows(result):
            if row.close is not None:
                closes[_bar_day(row.ts)] = row.close
        days = sorted(closes)

        # previous_close = penultima chiusura giornaliera, come fast_info;
        # chartPreviousClose (chiusura prima del primo giorno del grafico) solo
        # se le barre non bastano.
        if len(days) >= 2:
            previous_close = closes[days[-2]]
        else:
            previous_close = _finite_float(meta.get('chartPreviousClose'))
        last_day = days[-1] if days else None
        return _QuoteSnapshot(
            price=_finite_float(meta.get('regularMarketPrice')),
            market_ts=_to_utc_datetime(_finite_float(meta.get('regularMarketTime'))),
            last_close=closes[last_day] if last_day else None,
            # Mezzanotte locale del giorno della barra, come l'indice di yfinance.
            last_close_ts=datetime(last_day.year, last_day.month, last_day.day, tzinfo=tz) if last_day else None,
            previous_close=previous_close,
        )

    def _daily_rows(
        self,
        symbol: str,
        *,
        start_date: str | None,
        end_date: str | None,
        operation: str,
        no_data_message: str,
    ) -> list[tuple[date, _ChartRow]]:
        """Barre giornaliere di [start_date, end_date) datate nel fuso della borsa.

        Stessa semantica di yfinance history(start, end): start incluso, end
        escluso, date di borsa; solo end = un mese prima di end; nessuna data = 1 mese.
        yfinance calcolava la mezzanotte locale con una richiesta in più per il
        fuso: qui si chiede un giorno in più per lato e si filtra dopo.
        """
        start = _parse_bound_date(start_date, symbol=symbol, operation=operation)
        end = _parse_bound_date(end_date, symbol=symbol, operation=operation)
        params: dict[str, object] = {
            'interval': '1d',
            'includePrePost': 'false',
            'events': 'div,splits,capitalGains',
        }
        if start is None and end is None:
            params['range'] = '1mo'
        else:
            if start is None:
                start = _one_month_before(end)
            params['period1'] = _utc_midnight_epoch(start) - 86400
            params['period2'] = _utc_midnight_epoch(end) + 86400 if end is not None else int(time.time())

        result = self._fetch_chart(symbol, params, operation=operation, no_data_message=no_data_message)
        rows: list[tuple[date, _ChartRow]] = []
        for row in _chart_rows(result):
            day = _bar_day(row.ts)
            if start is not None and day < start:
                continue
            if end is not None and day >= end:
                continue
            rows.append((day, row))
        return rows

    def _fetch_chart(self, symbol: str, params: dict[str, object], *, operation: str, no_data_message: str) -> dict:
        """Una GET a v8/finance/chart con retry su 429/5xx e rete; restituisce chart.result[0]."""
        yahoo_symbol = self._resolve_yahoo_symbol(symbol, operation=operation)
        url = f"{YAHOO_CHART_URL}/{url_quote(yahoo_symbol, safe='=')}"
        client = self._http_client or _shared_yahoo_http_client()
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = client.get(url, params=params, headers=_YAHOO_HEADERS, timeout=self.timeout_seconds)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Retryable status code {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                return _chart_result(response, symbol=symbol, operation=operation, no_data_message=no_data_message)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                delay = _compute_retry_delay(exc, attempt=attempt, backoff_seconds=self.retry_backoff_seconds)
                if delay > _YAHOO_MAX_RETRY_DELAY_SECONDS:
                    logger.warning(
                        'Yahoo chart request not retried symbol=%s retry_after=%.0fs reason=%s',
                        symbol,
                        delay,
                        exc,
                    )
                    break
                logger.warning(
                    'Retry Yahoo chart request symbol=%s attempt=%s/%s delay=%.2fs reason=%s',
                    symbol,
                    attempt,
                    self.max_retries,
                    delay,
                    exc,
                )
                if delay > 0:
                    time.sleep(delay)

        assert last_error is not None
        raise _provider_error('yfinance', operation, symbol, last_error) from last_error

    def _resolve_yahoo_symbol(self, symbol: str, *, operation: str) -> str:
        """Simbolo per l'URL del chart: maiuscolo, e un ISIN risolto con la ricerca Yahoo come faceva yf.Ticker."""
        normalized = symbol.strip().upper()
        if not _YF_ISIN_RE.match(normalized):
            return normalized
        with _isin_ticker_cache_lock:
            cached = _isin_ticker_cache.get(normalized)
        if cached:
            return cached
        try:
            import yfinance as yf
            quotes = yf.Search(normalized, max_results=1).quotes
        except Exception:
            quotes = []
        ticker = str((quotes[0] or {}).get('symbol') or '').strip().upper() if quotes else ''
        if not ticker:
            raise ProviderError(
                provider='yfinance',
                operation=operation,
                symbol=symbol,
                reason='no_data',
                message=f"Invalid ISIN number: {normalized}",
            )
        with _isin_ticker_cache_lock:
            _isin_ticker_cache[normalized] = ticker
        return ticker

    def _ticker_info(self, ticker, symbol: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                info = ticker.info
                return info if isinstance(info, dict) else {}
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * attempt)
        assert last_error is not None
        raise _provider_error('yfinance', 'info', symbol, last_error)


def make_finance_client(settings: 'Settings') -> TwelveDataClient | YahooFinanceClient:
    """Factory: restituisce il client giusto in base a FINANCE_PROVIDER."""
    provider = settings.finance_provider.strip().lower()
    if provider == 'yfinance':
        return YahooFinanceClient(
            timeout_seconds=settings.finance_request_timeout_seconds,
            max_retries=settings.finance_max_retries,
            retry_backoff_seconds=settings.finance_retry_backoff_seconds,
        )
    # fallback: TwelveData
    return TwelveDataClient(
        base_url=settings.finance_api_base_url,
        api_key=settings.finance_api_key,
        timeout_seconds=settings.finance_request_timeout_seconds,
        max_retries=settings.finance_max_retries,
        retry_backoff_seconds=settings.finance_retry_backoff_seconds,
    )


def _provider_error(provider: str, operation: str, symbol: str, exc: Exception) -> ProviderError:
    raw = str(exc).lower()
    reason = 'provider_error'
    retryable = False
    if isinstance(exc, httpx.TimeoutException) or 'timeout' in raw:
        reason = 'timeout'
        retryable = True
    elif '429' in raw or 'rate limit' in raw or 'too many requests' in raw:
        reason = 'rate_limited'
        retryable = True
    elif 'not found' in raw or 'no data' in raw or 'empty' in raw:
        reason = 'no_data'
    elif 'json' in raw or 'parse' in raw:
        reason = 'invalid_payload'

    return ProviderError(
        provider=provider,
        operation=operation,
        symbol=symbol,
        reason=reason,
        message=f"{provider} {operation} failed for {symbol}: {exc}",
        retryable=retryable,
    )
