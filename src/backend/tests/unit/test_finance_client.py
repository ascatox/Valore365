import sys
import types

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
