"""TASK-52: X-Ray separates 'not applicable' from 'missing data'.

Equity look-through (underlying shares, countries, sectors) applies to single
shares, equity funds and unclassified instruments. Gold, commodities, bonds,
money market and crypto are not applicable; an equity fund without holdings
data is missing.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import copilot_tools
from app.finance_client import ProviderEtfHolding
from app.services.portfolio_doctor import _xray
from app.services.portfolio_doctor._holdings import AnalyzedHolding


def _h(asset_id, symbol, name, weight, asset_type="etf") -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency="USD", market_value=weight * 100.0, weight_pct=weight,
    )


class _Repo:
    def __init__(self, enrichment=None):
        self._enrichment = enrichment or {}

    def get_etf_enrichment_bulk(self, ids):
        return {aid: v for aid, v in self._enrichment.items() if aid in ids}

    def get_asset_pricing_symbols(self, ids, provider):
        return {}

    def get_asset_metadata_bulk(self, ids):
        return {}


@pytest.fixture(autouse=True)
def _clear_cache():
    _xray._top_holdings_cache.clear()
    yield
    _xray._top_holdings_cache.clear()


def _vti_top10(total_pct: float) -> list[ProviderEtfHolding]:
    # Yahoo returns fractions of the fund.
    return [ProviderEtfHolding(symbol=f"S{i}", name=f"Stock {i}", weight=total_pct / 1000.0) for i in range(10)]


def _all_weather() -> list[AnalyzedHolding]:
    return [
        _h(1, "TLT", "iShares 20+ Year Treasury Bond ETF", 40.0),
        _h(2, "IEF", "iShares 7-10 Year Treasury Bond ETF", 15.0),
        _h(3, "VTI", "Vanguard Total Stock Market ETF", 30.0),
        _h(4, "DJP", "iPath Bloomberg Commodity Index Total Return ETN", 7.5),
        _h(5, "GLD", "SPDR Gold Shares", 7.5),
    ]


def _azionario() -> list[AnalyzedHolding]:
    return [
        _h(11, "VTI", "Vanguard Total Stock Market ETF", 40.0),
        _h(12, "VEUR", "Vanguard FTSE Developed Europe UCITS ETF", 35.0),
        _h(13, "VFEM", "Vanguard FTSE Emerging Markets UCITS ETF", 25.0),
    ]


def _run(monkeypatch, holdings, repo=None, yahoo=None):
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: holdings)
    yahoo = yahoo or {}
    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: yahoo.get(symbol, []))
    return _xray.compute_portfolio_xray(repo or _Repo(), 1, "u", finance, None)


def _status(out):
    return {d.symbol: d.lookthrough_status for d in out.etf_details}


# --- All Weather -------------------------------------------------------------------


def test_all_weather_statuses(monkeypatch):
    out = _run(monkeypatch, _all_weather(), yahoo={"VTI": _vti_top10(30.0)})

    assert _status(out) == {
        "TLT": "not_applicable",
        "IEF": "not_applicable",
        "VTI": "available",
        "DJP": "not_applicable",
        "GLD": "not_applicable",
    }
    reasons = {d.symbol: d.lookthrough_reason for d in out.etf_details}
    assert "obbligazion" in reasons["TLT"].lower()
    assert "oro" in reasons["GLD"].lower()
    assert "materie prime" in reasons["DJP"].lower()
    assert reasons["VTI"]


def test_all_weather_applicable_coverage(monkeypatch):
    out = _run(monkeypatch, _all_weather(), yahoo={"VTI": _vti_top10(30.0)})

    # Applicable part = VTI only (30% of the portfolio); its top 10 cover 30% of the fund.
    assert out.applicable_lookthrough_coverage_pct == pytest.approx(30.0, abs=0.05)
    assert out.not_applicable_pct == pytest.approx(70.0)
    assert out.missing_pct == 0.0
    assert out.available_pct == pytest.approx(30.0)
    # Whole-portfolio look-through stays as in TASK-48: 30 x 30% = 9%.
    assert out.lookthrough_coverage_pct == pytest.approx(9.0, abs=0.05)
    assert out.applicable_denominator
    note = out.coverage_note
    assert "parte azionaria" in note
    assert "non applicabile" in note.lower()


def test_all_weather_without_vti_data_is_missing_not_zero_everywhere(monkeypatch):
    out = _run(monkeypatch, _all_weather())

    assert _status(out)["VTI"] == "missing"
    assert out.missing_pct == pytest.approx(30.0)
    assert out.not_applicable_pct == pytest.approx(70.0)
    assert out.applicable_lookthrough_coverage_pct == 0.0
    vti = next(d for d in out.etf_details if d.symbol == "VTI")
    assert "mancan" in vti.lookthrough_reason.lower()


def test_only_not_applicable_positions_have_no_applicable_coverage(monkeypatch):
    holdings = [_h(5, "GLD", "SPDR Gold Shares", 60.0), _h(1, "TLT", "iShares 20+ Year Treasury Bond ETF", 40.0)]

    out = _run(monkeypatch, holdings)

    assert out.applicable_lookthrough_coverage_pct is None
    assert out.not_applicable_pct == pytest.approx(100.0)
    assert out.missing_pct == 0.0
    assert "non applicabile" in out.coverage_note.lower()


# --- 100% Azionario ----------------------------------------------------------------


def test_azionario_missing_pct(monkeypatch):
    repo = _Repo(enrichment={13: {"top_holdings": [
        {"name": f"EM{i}", "isin": f"KY{i:04d}", "percentage": 2.0} for i in range(10)
    ]}})

    out = _run(monkeypatch, _azionario(), repo=repo, yahoo={"VTI": _vti_top10(30.0)})

    assert _status(out) == {"VTI": "available", "VEUR": "missing", "VFEM": "available"}
    assert out.missing_pct == pytest.approx(35.0)
    assert out.not_applicable_pct == 0.0
    # 40 x 30% + 25 x 20% = 17 over an applicable 100.
    assert out.applicable_lookthrough_coverage_pct == pytest.approx(17.0, abs=0.05)
    assert out.lookthrough_coverage_pct == pytest.approx(17.0, abs=0.05)


def test_azionario_veur_and_vfem_missing(monkeypatch):
    out = _run(monkeypatch, _azionario(), yahoo={"VTI": _vti_top10(30.0)})

    assert _status(out)["VEUR"] == "missing"
    assert _status(out)["VFEM"] == "missing"
    assert out.missing_pct == pytest.approx(60.0)
    issues = {i.symbol: i.lookthrough_status for i in out.coverage_issues}
    assert issues == {"VEUR": "missing", "VFEM": "missing"}


def test_direct_stock_is_available_and_money_market_not_applicable(monkeypatch):
    holdings = [
        _h(21, "AAPL", "Apple Inc", 50.0, asset_type="stock"),
        _h(22, "XEON", "Xtrackers II EUR Overnight Rate Swap UCITS ETF", 50.0),
    ]
    asked: list[str] = []
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: holdings)
    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: asked.append(symbol) or [])

    out = _xray.compute_portfolio_xray(_Repo(), 1, "u", finance, None)

    assert _status(out) == {"AAPL": "available", "XEON": "not_applicable"}
    assert "XEON" not in asked  # money market: no basket of shares to ask Yahoo about
    assert out.applicable_lookthrough_coverage_pct == pytest.approx(100.0)


def test_shares_sum_to_100(monkeypatch):
    out = _run(monkeypatch, _all_weather() + [_h(12, "VEUR", "Vanguard FTSE Developed Europe UCITS ETF", 10.0)],
               yahoo={"VTI": _vti_top10(30.0)})
    assert out.available_pct + out.not_applicable_pct + out.missing_pct == pytest.approx(100.0, abs=0.15)


# --- copilot / MCP -----------------------------------------------------------------


def test_copilot_summary_exposes_statuses_and_applicable_coverage(monkeypatch):
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: _all_weather())
    finance = SimpleNamespace(get_etf_top_holdings=lambda s: _vti_top10(30.0) if s == "VTI" else [])

    out = copilot_tools._get_xray_summary({}, _Repo(), MagicMock(), 1, "u", finance_client=finance)

    assert out["applicable_lookthrough_coverage_pct"] == pytest.approx(30.0, abs=0.05)
    assert out["not_applicable_pct"] == pytest.approx(70.0)
    assert out["missing_pct"] == 0.0
    assert out["applicable_denominator"]
    funds = {f["symbol"]: f for f in out["funds"]}
    assert funds["GLD"]["lookthrough_status"] == "not_applicable"
    assert funds["VTI"]["lookthrough_status"] == "available"
    assert funds["TLT"]["lookthrough_reason"]
    assert all("lookthrough_status" in ci for ci in out["coverage_issues"])


# --- Yahoo top holdings: a transient error is not "no holdings" ---------------------


def _fake_yfinance(monkeypatch, behaviour):
    import sys
    import types

    import pandas as pd

    class _Funds:
        @property
        def top_holdings(self):
            return behaviour()

    class _Ticker:
        def __init__(self, symbol):
            self.funds_data = _Funds()

    class YFDataException(Exception):
        pass

    module = types.SimpleNamespace(Ticker=_Ticker, exceptions=types.SimpleNamespace(YFDataException=YFDataException))
    monkeypatch.setitem(sys.modules, "yfinance", module)
    return pd, YFDataException


def test_yahoo_top_holdings_fractions_are_parsed(monkeypatch):
    from app.finance_client import YahooFinanceClient

    pd, _ = _fake_yfinance(monkeypatch, lambda: frame)
    frame = pd.DataFrame({"Name": ["Apple", "Microsoft"], "Holding Percent": [0.065, 0.06]}, index=["AAPL", "MSFT"])

    out = YahooFinanceClient(max_retries=1).get_etf_top_holdings("VTI")

    # Yahoo gives fractions of the fund (0.065 = 6.5%): kept as fractions.
    assert [(h.symbol, h.weight) for h in out] == [("AAPL", 0.065), ("MSFT", 0.06)]


def test_no_fund_data_is_an_empty_answer(monkeypatch):
    from app.finance_client import YahooFinanceClient

    holder = {}

    def _raise():
        raise holder["exc"]("AAPL: No Fund data found.")

    _, exc_type = _fake_yfinance(monkeypatch, _raise)
    holder["exc"] = exc_type

    assert YahooFinanceClient(max_retries=1).get_etf_top_holdings("AAPL") == []


def test_a_network_error_raises_and_is_not_cached_as_no_holdings(monkeypatch):
    from app.errors import ProviderError
    from app.finance_client import YahooFinanceClient

    def _raise():
        raise ConnectionError("curl: (7) CONNECT tunnel failed, response 403")

    _fake_yfinance(monkeypatch, _raise)
    with pytest.raises(ProviderError):
        YahooFinanceClient(max_retries=1).get_etf_top_holdings("VTI")


def test_xray_retries_yahoo_after_a_transient_error(monkeypatch):
    calls: list[str] = []
    state = {"fail": True}

    def _top(symbol):
        calls.append(symbol)
        if state["fail"]:
            raise RuntimeError("rate limited")
        return _vti_top10(30.0)

    holdings = [_h(3, "VTI", "Vanguard Total Stock Market ETF", 100.0)]
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: holdings)
    finance = SimpleNamespace(get_etf_top_holdings=_top)

    first = _xray.compute_portfolio_xray(_Repo(), 1, "u", finance, None)
    assert first.etf_details[0].lookthrough_status == "missing"
    assert "temporaneo" in first.etf_details[0].lookthrough_reason

    state["fail"] = False
    second = _xray.compute_portfolio_xray(_Repo(), 1, "u", finance, None)
    assert second.etf_details[0].lookthrough_status == "available"
    assert calls == ["VTI", "VTI"]
