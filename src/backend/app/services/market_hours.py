"""Orari di borsa per lo scheduler prezzi.

Il mercato di un asset si ricava dal simbolo Yahoo: suffisso di borsa (.MI,
.DE, ...), nessun suffisso = USA, crypto (BTC-USD) 24/7, cambi e future (=X,
=F) 24/5, indici (^GSPC) quando la borsa è nota. is_market_open considera solo
orari regolari e weekend (nelle festività lo scheduler aggiorna come prima);
il conteggio delle sedute (completed_sessions_after, usato per le quotazioni
ferme) salta anche le principali festività di NYSE e delle borse europee.
Simbolo non riconosciuto = mercato aperto: meglio una richiesta inutile che un
prezzo fermo.

Funzioni pure: l'istante da valutare è sempre un parametro.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketSession:
    timezone: str
    open: time
    close: time


_US = MarketSession('America/New_York', time(9, 30), time(16, 0))
_XETRA = MarketSession('Europe/Berlin', time(9, 0), time(17, 30))
# Borse regionali tedesche (Francoforte, Stoccarda, Berlino, ...): 08:00-22:00.
_GERMAN_REGIONAL = MarketSession('Europe/Berlin', time(8, 0), time(22, 0))
_PARIS = MarketSession('Europe/Paris', time(9, 0), time(17, 30))
_AMSTERDAM = MarketSession('Europe/Amsterdam', time(9, 0), time(17, 30))
_MADRID = MarketSession('Europe/Madrid', time(9, 0), time(17, 30))
_ZURICH = MarketSession('Europe/Zurich', time(9, 0), time(17, 30))
_LONDON = MarketSession('Europe/London', time(8, 0), time(16, 30))
_TOKYO = MarketSession('Asia/Tokyo', time(9, 0), time(15, 30))
_SYDNEY = MarketSession('Australia/Sydney', time(10, 0), time(16, 0))
_HONG_KONG = MarketSession('Asia/Hong_Kong', time(9, 30), time(16, 0))

# Suffisso Yahoo -> orario continuo locale (asta di chiusura compresa dove
# finisce dopo; il margine after-close copre il resto).
_SUFFIX_SESSIONS: dict[str, MarketSession] = {
    '.MI': MarketSession('Europe/Rome', time(9, 0), time(17, 30)),
    '.DE': _XETRA,
    '.F': _GERMAN_REGIONAL,
    # Su Yahoo .SG è la borsa di Stoccarda (Singapore è .SI).
    '.SG': _GERMAN_REGIONAL,
    '.BE': _GERMAN_REGIONAL,
    '.DU': _GERMAN_REGIONAL,
    '.HM': _GERMAN_REGIONAL,
    '.HA': _GERMAN_REGIONAL,
    '.MU': _GERMAN_REGIONAL,
    '.PA': _PARIS,
    '.AS': _AMSTERDAM,
    '.BR': MarketSession('Europe/Brussels', time(9, 0), time(17, 30)),
    '.LS': MarketSession('Europe/Lisbon', time(8, 0), time(16, 30)),
    '.IR': MarketSession('Europe/Dublin', time(8, 0), time(16, 30)),
    '.MC': _MADRID,
    '.VI': MarketSession('Europe/Vienna', time(9, 0), time(17, 30)),
    '.HE': MarketSession('Europe/Helsinki', time(10, 0), time(18, 30)),
    '.OL': MarketSession('Europe/Oslo', time(9, 0), time(16, 25)),
    '.ST': MarketSession('Europe/Stockholm', time(9, 0), time(17, 30)),
    '.CO': MarketSession('Europe/Copenhagen', time(9, 0), time(17, 0)),
    '.SW': _ZURICH,
    '.L': _LONDON,
    '.IL': _LONDON,
    '.AT': MarketSession('Europe/Athens', time(10, 0), time(17, 20)),
    '.WA': MarketSession('Europe/Warsaw', time(9, 0), time(17, 5)),
    '.T': _TOKYO,
    '.AX': _SYDNEY,
    '.HK': _HONG_KONG,
    '.SI': MarketSession('Asia/Singapore', time(9, 0), time(17, 0)),
    '.TO': MarketSession('America/Toronto', time(9, 30), time(16, 0)),
    '.V': MarketSession('America/Toronto', time(9, 30), time(16, 0)),
}

# Indici con borsa nota; gli altri ^... restano sempre aperti.
_INDEX_SESSIONS: dict[str, MarketSession] = {
    '^GSPC': _US,
    '^DJI': _US,
    '^IXIC': _US,
    '^NDX': _US,
    '^RUT': _US,
    '^VIX': _US,
    '^GDAXI': _XETRA,
    '^STOXX50E': _XETRA,
    '^FCHI': _PARIS,
    '^AEX': _AMSTERDAM,
    '^IBEX': _MADRID,
    '^SSMI': _ZURICH,
    '^FTSE': _LONDON,
    '^N225': _TOKYO,
    '^HSI': _HONG_KONG,
    '^AXJO': _SYDNEY,
}

# BTC-USD, ETH-EUR, ...: la parte dopo il trattino è la valuta di quotazione.
# Le classi di azioni USA (BRK-B) hanno una sola lettera e restano USA.
_CRYPTO_QUOTE_CURRENCIES = {'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'USDT', 'USDC', 'BTC', 'ETH'}
_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$')

# Cambi e future: da domenica 17:00 a venerdì 17:00, ora di New York.
_FX_TIMEZONE = ZoneInfo('America/New_York')
_FX_ROLLOVER = time(17, 0)


def _is_crypto(symbol: str) -> bool:
    if '.' in symbol or '-' not in symbol:
        return False
    base, _, quote = symbol.rpartition('-')
    return bool(base) and quote in _CRYPTO_QUOTE_CURRENCIES


def market_session_for_symbol(symbol: str) -> MarketSession | None:
    """Orario regolare della borsa del simbolo, o None se non è una borsa nota."""
    normalized = (symbol or '').strip().upper()
    if not normalized or _ISIN_RE.match(normalized):
        # Un ISIN viene risolto da Yahoo su una borsa qualsiasi.
        return None
    if normalized.startswith('^'):
        return _INDEX_SESSIONS.get(normalized)
    if '=' in normalized or _is_crypto(normalized):
        return None
    if '.' in normalized:
        return _SUFFIX_SESSIONS.get(normalized[normalized.rindex('.'):])
    return _US


def is_market_open(symbol: str, now: datetime, *, after_close_grace_minutes: int = 30) -> bool:
    """True se il mercato del simbolo è aperto in `now`, o ha chiuso da meno di `after_close_grace_minutes`."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    grace = timedelta(minutes=max(0, int(after_close_grace_minutes)))
    normalized = (symbol or '').strip().upper()

    if _is_crypto(normalized):
        return True
    if normalized.endswith(('=X', '=F')):
        return _is_open_24x5(now, grace)

    session = market_session_for_symbol(normalized)
    if session is None:
        return True
    local = now.astimezone(ZoneInfo(session.timezone))
    if local.weekday() >= 5:
        return False
    opens_at = local.replace(hour=session.open.hour, minute=session.open.minute, second=0, microsecond=0)
    closes_at = local.replace(hour=session.close.hour, minute=session.close.minute, second=0, microsecond=0)
    return opens_at <= local < closes_at + grace


def _is_open_24x5(now: datetime, grace: timedelta) -> bool:
    local = now.astimezone(_FX_TIMEZONE)
    rollover = local.replace(hour=_FX_ROLLOVER.hour, minute=_FX_ROLLOVER.minute, second=0, microsecond=0)
    weekday = local.weekday()
    if weekday == 5:  # sabato
        return False
    if weekday == 6:  # domenica: riapre alle 17:00
        return local >= rollover
    if weekday == 4:  # venerdì: chiude alle 17:00 (+ margine)
        return local < rollover + grace
    return True


# --- Calendario delle sedute (TASK-53) ---------------------------------------

_UTC_SESSION = MarketSession('UTC', time(0, 0), time(23, 59, 59, 999999))


def _easter_sunday(year: int) -> date:
    """Domenica di Pasqua (calendario gregoriano, algoritmo anonimo)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = (date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    """Festività USA di sabato -> venerdì, di domenica -> lunedì."""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


@lru_cache(maxsize=64)
def market_holidays(timezone: str, year: int) -> frozenset[date]:
    """Principali chiusure di borsa per fuso: NYSE per New York, festività comuni per le borse europee.

    Approssimato per eccesso (es. Londra il 1/5 è aperta): una festività in più
    fa solo contare una seduta in meno, mai segnalare un prezzo fermo a torto.
    """
    easter = _easter_sunday(year)
    if timezone == 'America/New_York':
        days = {
            _nth_weekday(year, 1, 0, 3),   # Martin Luther King Jr. Day
            _nth_weekday(year, 2, 0, 3),   # Washington's Birthday
            easter - timedelta(days=2),    # Good Friday
            _last_weekday(year, 5, 0),     # Memorial Day
            _observed(date(year, 6, 19)),  # Juneteenth
            _observed(date(year, 7, 4)),   # Independence Day
            _nth_weekday(year, 9, 0, 1),   # Labor Day
            _nth_weekday(year, 11, 3, 4),  # Thanksgiving
            _observed(date(year, 12, 25)),
        }
        new_year = date(year, 1, 1)
        # Capodanno di sabato non si recupera il venerdì (31/12) alla NYSE.
        if new_year.weekday() != 5:
            days.add(_observed(new_year))
        return frozenset(days)
    if timezone.startswith('Europe/'):
        days = {
            date(year, 1, 1),
            easter - timedelta(days=2),  # Venerdì santo
            easter + timedelta(days=1),  # Lunedì dell'Angelo
            date(year, 5, 1),
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
            date(year, 12, 31),
        }
        if timezone == 'Europe/Rome':
            days.add(date(year, 8, 15))
        return frozenset(days)
    return frozenset()


def _calendar_for_symbol(symbol: str) -> tuple[MarketSession, bool, bool]:
    """(sessione, solo giorni feriali, festività) con cui contare le sedute del simbolo."""
    normalized = (symbol or '').strip().upper()
    if _is_crypto(normalized):
        return _UTC_SESSION, False, False
    if normalized.endswith(('=X', '=F')):
        return MarketSession('America/New_York', time(0, 0), _FX_ROLLOVER), True, False
    session = market_session_for_symbol(normalized)
    if session is None:
        # ISIN o borsa sconosciuta: giorni feriali, chiusi a mezzanotte UTC.
        return _UTC_SESSION, True, False
    return session, True, True


def is_trading_day(symbol: str, day: date) -> bool:
    """True se la borsa del simbolo ha una seduta in `day` (weekend e principali festività esclusi)."""
    session, weekdays_only, holidays = _calendar_for_symbol(symbol)
    if weekdays_only and day.weekday() >= 5:
        return False
    return not (holidays and day in market_holidays(session.timezone, day.year))


def completed_sessions_after(symbol: str, last_day: date, now: datetime, *, limit: int = 60) -> int:
    """Sedute concluse (chiusura passata in `now`) dopo `last_day`, al massimo `limit`.

    Con la barra di venerdì, lunedì mattina restituisce 0 e lunedì sera 1.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    session, _, _ = _calendar_for_symbol(symbol)
    local = now.astimezone(ZoneInfo(session.timezone))
    today = local.date()
    count = 0
    day = last_day + timedelta(days=1)
    while day <= today and count < limit:
        if is_trading_day(symbol, day) and (day < today or local.time() >= session.close):
            count += 1
        day += timedelta(days=1)
    return count
