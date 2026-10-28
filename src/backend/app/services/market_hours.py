"""Orari di borsa per lo scheduler prezzi.

Il mercato di un asset si ricava dal simbolo Yahoo: suffisso di borsa (.MI,
.DE, ...), nessun suffisso = USA, crypto (BTC-USD) 24/7, cambi e future (=X,
=F) 24/5, indici (^GSPC) quando la borsa è nota. Solo orari regolari e weekend:
le festività non sono gestite (in quei giorni lo scheduler aggiorna come prima).
Simbolo non riconosciuto = mercato aperto: meglio una richiesta inutile che un
prezzo fermo.

Funzioni pure: l'istante da valutare è sempre un parametro.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
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
