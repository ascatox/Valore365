from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_pricing import register_pricing_routes
from app.errors import AppError
from app.models import DailyBackfillResponse, PriceRefreshResponse


class _PricingService:
    def __init__(self):
        self.calls = []

    def refresh_prices(self, portfolio_id, asset_scope, user_id):
        self.calls.append((portfolio_id, asset_scope, user_id))
        if portfolio_id == 404:
            raise ValueError("Portfolio non trovato")
        return PriceRefreshResponse(
            provider="yfinance", requested_assets=14, refreshed_assets=14, failed_assets=0, items=[], errors=[],
        )


class _HistoricalService:
    def __init__(self):
        self.calls = []

    def backfill_daily(self, portfolio_id, days, asset_scope, user_id):
        self.calls.append((portfolio_id, days, asset_scope, user_id))
        return DailyBackfillResponse(
            provider="yfinance",
            portfolio_id=portfolio_id,
            start_date=date(2025, 10, 25),
            end_date=date(2026, 10, 25),
            assets_requested=14,
            assets_refreshed=14,
            fx_pairs_refreshed=0,
            asset_items=[],
            fx_items=[],
            errors=[],
        )


def _client():
    pricing, historical = _PricingService(), _HistoricalService()
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_pricing_routes(
        router,
        repo=object(),
        settings=SimpleNamespace(),
        pricing_service=pricing,
        historical_service=historical,
        finance_client=object(),
        ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)
    return TestClient(app), pricing, historical


def test_refresh_and_backfill_run_once_per_request():
    client, pricing, historical = _client()

    assert client.post("/api/prices/refresh?portfolio_id=26&asset_scope=all").json()["refreshed_assets"] == 14
    assert client.post("/api/prices/refresh?portfolio_id=26&asset_scope=all").status_code == 200
    response = client.post("/api/prices/backfill-daily?portfolio_id=26&days=365&asset_scope=all")

    assert response.status_code == 200
    assert response.json()["assets_refreshed"] == 14
    # Sequential requests are not shared: each one runs.
    assert len(pricing.calls) == 2
    assert pricing.calls[0][:2] == (26, "all")
    assert [call[:3] for call in historical.calls] == [(26, 365, "all")]


def test_refresh_errors_still_map_to_bad_request():
    client, _, _ = _client()

    # app.main turns AppError into the JSON error response.
    with pytest.raises(AppError) as excinfo:
        client.post("/api/prices/refresh?portfolio_id=404&asset_scope=all")
    assert (excinfo.value.status_code, excinfo.value.message) == (400, "Portfolio non trovato")
