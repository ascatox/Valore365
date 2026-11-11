"""TASK-87: X-Ray of a portfolio (or an aggregate) without positions.

Same behaviour as health, stress test and Monte Carlo on an empty portfolio: a
valid, declared-empty response (``is_empty``, zero coverage, no exposures, an
Italian note), not the error that the MCP server masked with the generic
«Errore nell'esecuzione del tool get_xray_summary». A portfolio that does not
exist (or is not owned) still raises.
"""

from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app import copilot_tools
from app.api import portfolio_health
from app.auth import AuthContext
from app.rate_limit import require_auth_rate_limited
from app.services.portfolio_doctor import _xray

USER = "u"


class _Finance:
    def get_etf_top_holdings(self, symbol):  # pragma: no cover - never reached on an empty scope
        raise AssertionError("no provider call on an empty portfolio")


class _EmptyRepo:
    """No positions; ``missing`` ids behave as portfolios that do not exist."""

    def __init__(self, missing=()):
        self.missing = set(missing)

    def get_positions(self, portfolio_id, user_id, stale_days=5):
        if portfolio_id in self.missing:
            raise ValueError("Portfolio non trovato")
        return []

    def get_positions_multi(self, ids, user_id, stale_days=5):
        return []

    def resolve_portfolio_scope(self, ids, user_id):
        return SimpleNamespace(portfolio_ids=sorted(set(ids)))


def _assert_declared_empty(out):
    assert out.is_empty is True
    assert out.etf_count == 0 and out.coverage_pct == 0.0
    assert out.lookthrough_coverage_pct == 0.0
    assert out.applicable_lookthrough_coverage_pct is None
    assert out.aggregated_holdings == [] and out.etf_details == [] and out.coverage_issues == []
    assert out.aggregated_country_exposure == {} and out.aggregated_sector_exposure == {}
    assert out.coverage_note == _xray.EMPTY_PORTFOLIO_NOTE
    assert out.data_as_of is None


def test_empty_portfolio_returns_declared_empty_xray():
    out = _xray.compute_portfolio_xray(_EmptyRepo(), 9106, USER, _Finance())
    _assert_declared_empty(out)
    assert out.portfolio_id == 9106 and out.portfolio_ids is None


def test_aggregate_of_empty_portfolios_returns_declared_empty_xray():
    out = _xray.compute_portfolio_xray(_EmptyRepo(), [9107, 9106], USER, _Finance())
    _assert_declared_empty(out)
    assert out.portfolio_id == 0 and out.portfolio_ids == [9106, 9107]


def test_missing_portfolio_still_raises():
    with pytest.raises(ValueError, match="non trovato"):
        _xray.compute_portfolio_xray(_EmptyRepo(missing={42}), 42, USER, _Finance())


def test_non_empty_xray_is_not_marked_empty(monkeypatch):
    from app.services.portfolio_doctor._holdings import AnalyzedHolding

    holding = AnalyzedHolding(asset_id=1, symbol="AAA", name="AAA", asset_type="stock",
                              quote_currency="EUR", market_value=100.0, weight_pct=100.0)
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: [holding])
    repo = SimpleNamespace(get_etf_enrichment_bulk=lambda ids: {}, get_asset_pricing_symbols=lambda ids, provider: {},
                           get_asset_metadata_bulk=lambda ids: {})
    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: [])
    _xray._top_holdings_cache.clear()
    try:
        out = _xray.compute_portfolio_xray(repo, 1, USER, finance)
    finally:
        _xray._top_holdings_cache.clear()
    assert out.is_empty is False


@pytest.mark.parametrize("portfolio_id, scope", [(9106, None), (9106, [9106, 9107])])
def test_tool_answers_without_error(portfolio_id, scope):
    handler = copilot_tools._TOOL_HANDLERS["get_xray_summary"]
    ref = scope if scope is not None else portfolio_id
    out = handler({}, _EmptyRepo(), None, ref, USER, finance_client=_Finance(), justetf_client=None)
    assert "error" not in out
    assert out["is_empty"] is True
    assert out["coverage_pct"] == 0.0 and out["applicable_lookthrough_coverage_pct"] is None
    assert out["top_underlying_holdings"] == [] and out["funds"] == [] and out["coverage_issues"] == []
    assert out["geographic_exposure"] == {} and out["sector_exposure"] == {}
    assert out["coverage_note"] == _xray.EMPTY_PORTFOLIO_NOTE


def test_execute_tool_returns_empty_output_not_generic_error():
    out = copilot_tools.execute_tool("get_xray_summary", {}, _EmptyRepo(), None, 9106, USER, finance_client=_Finance())
    assert set(out) != {"error"} and out["is_empty"] is True


def test_rest_route_returns_200_with_empty_xray():
    app = FastAPI()
    router = APIRouter()
    portfolio_health.register_portfolio_health_routes(router, _EmptyRepo(), finance_client=_Finance())
    app.include_router(router)
    app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id=USER)
    response = TestClient(app).get("/portfolios/9106/xray")
    assert response.status_code == 200
    body = response.json()
    assert body["is_empty"] is True and body["etf_count"] == 0
    assert body["coverage_note"] == _xray.EMPTY_PORTFOLIO_NOTE
