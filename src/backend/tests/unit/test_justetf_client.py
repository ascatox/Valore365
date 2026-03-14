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
        get_etf_overview=lambda isin: {
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
