import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .config import Settings

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "UTC"
DEFAULT_ORDER = "asc"


@dataclass
class ProviderQuote:
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    volume: float | None
    ts: datetime


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
            raise ValueError(f"Prezzo non disponibile per {symbol}")

        ts = datetime.now(UTC)
        return ProviderQuote(
            symbol=symbol,
            price=price,
            bid=_parse_float(payload, ['bid']),
            ask=_parse_float(payload, ['ask']),
            volume=_parse_float(payload, ['volume']),
            ts=ts,
        )

    def get_market_quote(self, symbol: str) -> ProviderMarketQuote:
        try:
            quote = self.get_quote(symbol)
            return ProviderMarketQuote(
                symbol=symbol,
                price=quote.price,
                previous_close=None,
                ts=quote.ts,
            )
        except Exception:
            return ProviderMarketQuote(
                symbol=symbol,
                price=None,
                previous_close=None,
                ts=datetime.now(UTC),
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
            raise ValueError(f"Serie storica non disponibile per {symbol}")

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
            raise ValueError(f"Serie FX non disponibile per {pair}")

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
            raise ValueError('FINANCE_API_KEY non configurata')

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
                    raise ValueError(f"Provider error per {symbol}: {message}")

                if not isinstance(payload, dict):
                    raise ValueError(f"Payload non valido per {symbol}")
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
            raise ValueError(f"Errore provider per {symbol}: {last_error}") from last_error
        raise ValueError(f"Errore provider per {symbol}")


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


class YahooFinanceClient:
    """Client Yahoo Finance tramite la libreria yfinance (gratuito, no API key)."""

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
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        try:
            price = ticker.fast_info.last_price
        except Exception:
            price = None

        if price is None or not math.isfinite(float(price)):
            hist = ticker.history(period='5d')
            if hist.empty:
                raise ValueError(f"Nessuna quotazione disponibile per {symbol}")
            close_col = hist['Close']
            close_col = close_col.dropna()
            if close_col.empty:
                raise ValueError(f"Nessuna quotazione disponibile per {symbol}")
            price = float(close_col.iloc[-1])

        return ProviderQuote(
            symbol=symbol,
            price=float(price),
            bid=None,
            ask=None,
            volume=None,
            ts=datetime.now(UTC),
        )

    def get_market_quote(self, symbol: str) -> ProviderMarketQuote:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        price: float | None = None
        previous_close: float | None = None
        try:
            price = ticker.fast_info.last_price
            previous_close = ticker.fast_info.previous_close
        except Exception:
            pass

        if price is None or not math.isfinite(float(price)):
            try:
                hist = ticker.history(period='5d')
                if not hist.empty:
                    close_col = hist['Close'].dropna()
                    if not close_col.empty:
                        price = float(close_col.iloc[-1])
                        if len(close_col) >= 2:
                            previous_close = float(close_col.iloc[-2])
            except Exception:
                pass

        if price is not None and not math.isfinite(float(price)):
            price = None
        if previous_close is not None and not math.isfinite(float(previous_close)):
            previous_close = None

        return ProviderMarketQuote(
            symbol=symbol,
            price=float(price) if price is not None else None,
            previous_close=float(previous_close) if previous_close is not None else None,
            ts=datetime.now(UTC),
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
        import pandas as pd
        import yfinance as yf

        df = yf.download(
            symbol,
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        if df.empty:
            raise ValueError(f"Nessun dato storico per {symbol}")

        bars: list[ProviderDailyBar] = []
        for ts, row in df.iterrows():
            try:
                bars.append(ProviderDailyBar(
                    day=ts.date() if hasattr(ts, 'date') else _parse_date(str(ts)),
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=float(row['Volume']) if 'Volume' in row and pd.notna(row['Volume']) else None,
                ))
            except Exception:
                continue

        bars.sort(key=lambda x: x.day)
        if order == 'desc':
            bars.reverse()
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
        import pandas as pd
        import yfinance as yf

        # Yahoo: EURUSD=X = quanti USD per 1 EUR
        pair = f"{from_currency}{to_currency}=X"
        df = yf.download(
            pair,
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        if df.empty:
            raise ValueError(f"Nessun dato FX per {pair}")

        rates: list[ProviderFxRate] = []
        for ts, row in df.iterrows():
            try:
                close = row['Close']
                if not pd.notna(close):
                    continue
                rates.append(ProviderFxRate(
                    day=ts.date() if hasattr(ts, 'date') else _parse_date(str(ts)),
                    rate=float(close),
                ))
            except Exception:
                continue

        rates.sort(key=lambda x: x.day)
        if order == 'desc':
            rates.reverse()
        return rates


def make_finance_client(settings: 'Settings') -> TwelveDataClient | YahooFinanceClient:
    """Factory: restituisce il client giusto in base a FINANCE_PROVIDER."""
    provider = settings.finance_provider.strip().lower()
    if provider == 'yfinance':
        return YahooFinanceClient()
    # fallback: TwelveData
    return TwelveDataClient(
        base_url=settings.finance_api_base_url,
        api_key=settings.finance_api_key,
        timeout_seconds=settings.finance_request_timeout_seconds,
        max_retries=settings.finance_max_retries,
        retry_backoff_seconds=settings.finance_retry_backoff_seconds,
    )
