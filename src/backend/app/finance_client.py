import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

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
