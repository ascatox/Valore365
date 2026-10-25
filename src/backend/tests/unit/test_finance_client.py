import sys
import types
from datetime import UTC, datetime

import pandas as pd
import pytest

from app.errors import ProviderError
from app.finance_client import YahooFinanceClient, normalize_expense_ratio_pct


def test_normalize_expense_ratio_pct_handles_percent_and_fraction_inputs():
    assert normalize_expense_ratio_pct(0.13) == 0.13
    assert normalize_expense_ratio_pct(0.0013) == 0.13
    assert normalize_expense_ratio_pct(0.22) == 0.22
    assert normalize_expense_ratio_pct(None) is None


def test_yfinance_quote_falls_back_to_history_close(monkeypatch):
    class _FastInfo:
        @property
        def last_price(self):
            raise RuntimeError("fast info unavailable")

    class _Ticker:
        def __init__(self, symbol: str):
            self.symbol = symbol
            self.fast_info = _FastInfo()

        @property
        def info(self):
            return {}

        def history(self, **kwargs):
            return pd.DataFrame(
                {"Close": [100.0, 101.5]},
                index=pd.to_datetime(["2026-03-10", "2026-03-11"]),
            )

    fake_module = types.SimpleNamespace(Ticker=lambda symbol: _Ticker(symbol))
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    client = YahooFinanceClient(max_retries=1)
    quote = client.get_quote("AAPL")

    assert quote.price == 101.5
    assert quote.source == "history_close"
    assert quote.is_realtime is False
    assert quote.is_fallback is True
    assert quote.stale is True


def test_yfinance_asset_info_marks_missing_metadata(monkeypatch):
    class _Ticker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        @property
        def info(self):
            raise RuntimeError("provider down")

    fake_module = types.SimpleNamespace(Ticker=lambda symbol: _Ticker(symbol))
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    client = YahooFinanceClient(max_retries=1)
    info = client.get_asset_info("VWCE")

    assert info.metadata_status == "missing"
    assert info.current_price_source is None
    assert info.warnings


def test_yfinance_daily_bars_empty_raises_provider_error(monkeypatch):
    class _Ticker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        def history(self, **kwargs):
            return pd.DataFrame()

    fake_module = types.SimpleNamespace(Ticker=lambda symbol: _Ticker(symbol))
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    client = YahooFinanceClient(max_retries=1)
    with pytest.raises(ProviderError) as exc:
        client.get_daily_bars("AAPL")

    assert exc.value.reason == "no_data"


class _MarketQuoteTicker:
    """Ticker whose chart metadata carries the last trade time."""

    def __init__(self, metadata):
        self._metadata = metadata
        self.fast_info = types.SimpleNamespace(last_price=6850.2, previous_close=6821.6)
        self.info_reads = 0

    @property
    def info(self):
        # quoteSummary: needs a Yahoo crumb, so market quotes must not read it.
        self.info_reads += 1
        return {}

    def get_history_metadata(self):
        if isinstance(self._metadata, Exception):
            raise self._metadata
        return self._metadata


@pytest.mark.parametrize(
    "regular_market_time",
    [
        # yfinance 1.x formats it as a Timestamp in the exchange timezone...
        pd.Timestamp("2026-10-23 16:00:00", tz="America/New_York"),
        # ...older releases leave Yahoo's epoch seconds.
        1792785600,
    ],
)
def test_yfinance_market_quote_reads_last_trade_time_from_chart_metadata(monkeypatch, regular_market_time):
    ticker = _MarketQuoteTicker({"regularMarketTime": regular_market_time})
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: ticker))

    quote = YahooFinanceClient(max_retries=1).get_market_quote("^GSPC")

    assert quote.price == 6850.2
    assert quote.previous_close == 6821.6
    assert quote.ts == datetime(2026, 10, 23, 20, 0, tzinfo=UTC)
    assert quote.source == "fast_info"
    assert ticker.info_reads == 0


def test_yfinance_market_quote_survives_missing_chart_metadata(monkeypatch):
    ticker = _MarketQuoteTicker(RuntimeError("chart unavailable"))
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda symbol: ticker))

    quote = YahooFinanceClient(max_retries=1).get_market_quote("^GSPC")

    assert quote.price == 6850.2
    assert quote.ts is not None
    assert ticker.info_reads == 0
