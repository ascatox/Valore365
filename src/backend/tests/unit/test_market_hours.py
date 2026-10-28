from datetime import UTC, datetime

import pytest

from app.services.market_hours import is_market_open, market_session_for_symbol


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("symbol", "now", "expected"),
    [
        # USA (no suffix), Wednesday 28/10/2026, New York on EDT (UTC-4).
        ("AAPL", "2026-10-28 13:29", False),  # 09:29
        ("AAPL", "2026-10-28 13:30", True),   # 09:30 open
        ("AAPL", "2026-10-28 19:59", True),
        ("AAPL", "2026-10-28 20:29", True),   # 16:29, inside the 30' grace
        ("AAPL", "2026-10-28 20:30", False),  # 16:30
        ("BRK-B", "2026-10-28 15:00", True),  # share class, not crypto
        # Borsa Italiana, Milan on CET (UTC+1) after 25/10/2026.
        ("ENI.MI", "2026-10-28 07:59", False),  # 08:59
        ("ENI.MI", "2026-10-28 08:00", True),   # 09:00
        ("ENI.MI", "2026-10-28 16:55", True),   # 17:55, grace for the closing auction
        ("ENI.MI", "2026-10-28 17:00", False),  # 18:00
        # Xetra vs Frankfurt/Stuttgart floors (08:00-22:00 Berlin).
        ("VWCE.DE", "2026-10-28 20:00", False),
        ("VWCE.F", "2026-10-28 20:00", True),
        ("VWCE.SG", "2026-10-28 20:00", True),
        # London on GMT, Euronext Amsterdam, SIX.
        ("VUSA.L", "2026-10-28 08:00", True),
        ("VUSA.L", "2026-10-28 16:59", True),
        ("VUSA.L", "2026-10-28 17:00", False),
        ("IWDA.AS", "2026-10-28 07:30", False),
        ("IWDA.AS", "2026-10-28 09:00", True),
        ("NESN.SW", "2026-10-28 16:00", True),
        # Tokyo (UTC+9) and Sydney (AEDT, UTC+11).
        ("7203.T", "2026-10-28 00:00", True),   # 09:00
        ("7203.T", "2026-10-28 06:59", True),   # 15:59, grace
        ("7203.T", "2026-10-28 07:00", False),  # 16:00
        ("7203.T", "2026-10-28 15:00", False),  # 00:00
        ("CBA.AX", "2026-10-27 23:30", True),   # Wednesday 10:30
        ("CBA.AX", "2026-10-28 06:00", False),  # Wednesday 17:00
    ],
)
def test_regular_hours_per_region(symbol, now, expected):
    assert is_market_open(symbol, _utc(now)) is expected


@pytest.mark.parametrize("symbol", ["AAPL", "ENI.MI", "VWCE.F", "7203.T", "^GSPC", "EURUSD=X", "GC=F"])
def test_weekends_are_closed(symbol):
    assert is_market_open(symbol, _utc("2026-10-31 12:00")) is False  # Saturday
    assert is_market_open(symbol, _utc("2026-11-01 12:00")) is False  # Sunday


def test_grace_window_is_configurable():
    after_close = _utc("2026-10-28 20:10")  # 16:10 New York
    assert is_market_open("AAPL", after_close, after_close_grace_minutes=30) is True
    assert is_market_open("AAPL", after_close, after_close_grace_minutes=0) is False


def test_us_dst_boundary():
    # 13:45 UTC is 08:45 on Friday 6/3/2026 (EST) and 09:45 on Monday 9/3 (EDT).
    assert is_market_open("AAPL", _utc("2026-03-06 13:45")) is False
    assert is_market_open("AAPL", _utc("2026-03-09 13:45")) is True
    # Milan is still on CET that Monday: 13:45 UTC is 14:45 there.
    assert is_market_open("ENI.MI", _utc("2026-03-09 13:45")) is True


def test_eu_dst_boundary():
    # 07:30 UTC is 09:30 on Friday 23/10/2026 (CEST) and 08:30 on Monday 26/10 (CET).
    assert is_market_open("ENI.MI", _utc("2026-10-23 07:30")) is True
    assert is_market_open("ENI.MI", _utc("2026-10-26 07:30")) is False


@pytest.mark.parametrize("symbol", ["BTC-USD", "ETH-EUR", "SOL-USD", "USDT-USD"])
def test_crypto_is_always_open(symbol):
    assert is_market_open(symbol, _utc("2026-11-01 03:00")) is True  # Sunday night
    assert is_market_open(symbol, _utc("2026-10-28 23:59")) is True


def test_fx_and_futures_trade_24_5():
    for symbol in ("EURUSD=X", "GC=F"):
        assert is_market_open(symbol, _utc("2026-10-28 03:00")) is True   # Wednesday night
        assert is_market_open(symbol, _utc("2026-10-30 21:15")) is True   # Friday 17:15 New York, grace
        assert is_market_open(symbol, _utc("2026-10-30 21:45")) is False  # Friday 17:45
        assert is_market_open(symbol, _utc("2026-11-01 21:30")) is False  # Sunday 16:30 EST
        assert is_market_open(symbol, _utc("2026-11-01 22:00")) is True   # Sunday 17:00 EST


def test_indices_follow_their_exchange_when_known():
    assert is_market_open("^GSPC", _utc("2026-10-28 15:00")) is True
    assert is_market_open("^GSPC", _utc("2026-10-28 22:00")) is False
    assert is_market_open("^N225", _utc("2026-10-28 01:00")) is True
    assert is_market_open("^N225", _utc("2026-10-28 15:00")) is False
    assert is_market_open("FTSEMIB.MI", _utc("2026-10-28 22:00")) is False
    # Unknown index: always refreshed.
    assert is_market_open("^XYZ", _utc("2026-10-31 12:00")) is True


@pytest.mark.parametrize("symbol", ["ABC.ZZ", "IE00BK5BQT80", "", "WEIRD=Y"])
def test_unknown_markets_fail_open(symbol):
    assert market_session_for_symbol(symbol) is None
    assert is_market_open(symbol, _utc("2026-10-31 12:00")) is True


def test_naive_now_is_treated_as_utc():
    assert is_market_open("AAPL", datetime(2026, 10, 28, 15, 0)) is True
    assert is_market_open("AAPL", datetime(2026, 10, 28, 21, 0)) is False
