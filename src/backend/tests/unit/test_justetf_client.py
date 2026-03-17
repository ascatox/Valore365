import sys
import types

import pytest

from app.errors import ProviderError
from app.justetf_client import JustEtfClient


def test_justetf_invalid_isin_raises_provider_error():
    client = JustEtfClient(rate_limit_seconds=0.0)

    with pytest.raises(ProviderError) as exc:
        client.fetch_profile("INVALID")

    assert exc.value.reason == "invalid_isin"


def test_justetf_fetch_profile_parses_library_payload(monkeypatch):
    fake_module = types.SimpleNamespace(
        get_etf_overview=lambda isin, **_: {
            "name": "Test ETF",
            "description": "Test description",
            "index": "MSCI World",
            "investment_focus": "Equity",
            "countries": [{"name": "USA", "percentage": 60.0}],
            "sectors": [{"name": "Technology", "percentage": 25.0}],
            "top_holdings": [{"name": "Apple", "percentage": 4.5, "isin": "US0378331005"}],
            "fund_provider": "Example",
            "fund_size_eur": 1234567.0,
            "ter": 0.2,
        }
    )
    monkeypatch.setitem(sys.modules, "justetf_scraping", fake_module)

    client = JustEtfClient(rate_limit_seconds=0.0)
    data = client.fetch_profile("IE00B4L5Y983")

    assert data["name"] == "Test ETF"
    assert data["country_weights"][0]["name"] == "USA"
    assert data["sector_weights"][0]["percentage"] == 25.0
    assert data["top_holdings"][0]["isin"] == "US0378331005"


def test_justetf_403_enters_cooldown_without_retries(monkeypatch):
    calls = 0

    def _raise_403(_: str, **__):
        nonlocal calls
        calls += 1
        raise RuntimeError("Failed to fetch ETF page for IE00B441G979: status 403")

    fake_module = types.SimpleNamespace(get_etf_overview=_raise_403)
    monkeypatch.setitem(sys.modules, "justetf_scraping", fake_module)

    client = JustEtfClient(rate_limit_seconds=0.0, blocked_cooldown_seconds=60.0)

    with pytest.raises(ProviderError) as exc:
        client.fetch_profile("IE00B441G979")

    assert exc.value.reason == "temporarily_blocked"
    assert calls == 1

    with pytest.raises(ProviderError) as exc:
        client.fetch_profile("IE00B441G979")

    assert exc.value.reason == "temporarily_blocked"
    assert calls == 1


def test_justetf_fetch_profile_disables_gettex_by_default(monkeypatch):
    received_include_gettex: bool | None = None

    def _overview(_: str, **kwargs):
        nonlocal received_include_gettex
        received_include_gettex = kwargs.get("include_gettex")
        return {
            "name": "Test ETF",
            "countries": [],
            "sectors": [],
            "top_holdings": [],
        }

    fake_module = types.SimpleNamespace(get_etf_overview=_overview)
    monkeypatch.setitem(sys.modules, "justetf_scraping", fake_module)

    client = JustEtfClient(rate_limit_seconds=0.0)
    client.fetch_profile("IE00B4L5Y983")

    assert received_include_gettex is False


def test_justetf_403_uses_fmp_fallback_when_configured(monkeypatch):
    def _raise_403(_: str, **__):
        raise RuntimeError("Failed to fetch ETF page for IE00B441G979: status 403")

    fake_module = types.SimpleNamespace(get_etf_overview=_raise_403)
    monkeypatch.setitem(sys.modules, "justetf_scraping", fake_module)
    monkeypatch.setenv("FMT_API_KEY", "test-key")

    client = JustEtfClient(rate_limit_seconds=0.0, blocked_cooldown_seconds=60.0)
    calls: list[str] = []

    def _fake_fmp(symbol: str):
        calls.append(symbol)
        return {"name": "Fallback ETF", "source": "fmp"}

    monkeypatch.setattr(client, "_fetch_profile_from_fmp", _fake_fmp)

    data = client.fetch_profile("IE00B441G979", symbol="SWDA")

    assert data["source"] == "fmp"
    assert calls == ["SWDA"]
