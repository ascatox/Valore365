from dataclasses import asdict as _asdict
from typing import Any

from fastapi import APIRouter, Depends, Header, Query

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..finance_client import make_finance_client, QUOTE_TYPE_MAP
from ..models import (
    DailyBackfillResponse,
    ErrorResponse,
    PriceRefreshResponse,
)
from ..repository import PortfolioRepository


def register_pricing_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    settings: object,
    pricing_service: object,
    historical_service: object,
    finance_client: object,
    ensure_target_allocation_enabled: object,
) -> None:

    @router.post("/prices/refresh", response_model=PriceRefreshResponse, responses={400: {"model": ErrorResponse}})
    def refresh_prices(
        portfolio_id: int | None = None,
        asset_scope: str = Query(default="target", pattern="^(target|transactions|all)$"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PriceRefreshResponse:
        if asset_scope == "target":
            ensure_target_allocation_enabled()
        endpoint = f"prices_refresh:{portfolio_id}:{asset_scope}"
        if idempotency_key:
            cached = repo.get_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint, user_id=_auth.user_id)
            if cached:
                return PriceRefreshResponse.model_validate(cached)
        try:
            response = pricing_service.refresh_prices(portfolio_id=portfolio_id, asset_scope=asset_scope, user_id=_auth.user_id)
            if idempotency_key:
                repo.save_idempotency_response(
                    idempotency_key=idempotency_key, endpoint=endpoint, response_payload=response.model_dump(mode="json"), user_id=_auth.user_id
                )
            return response
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.post("/portfolios/{portfolio_id}/reclassify-assets", responses={400: {"model": ErrorResponse}})
    def reclassify_assets(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> dict[str, Any]:
        try:
            asset_ids = repo.get_portfolio_asset_ids(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

        client = make_finance_client(settings)
        updated: list[dict[str, str]] = []
        for aid in asset_ids:
            try:
                asset = repo.get_asset(aid)
            except ValueError:
                continue
            try:
                info = client.get_asset_info(asset.symbol)
            except Exception:
                continue
            try:
                repo.upsert_asset_metadata(aid, _asdict(info))
            except Exception:
                pass
            if info.quote_type:
                new_type = QUOTE_TYPE_MAP.get(info.quote_type.upper(), "stock")
                if new_type != asset.asset_type:
                    repo.update_asset_type(aid, new_type)
                    updated.append({"symbol": asset.symbol, "old": asset.asset_type, "new": new_type})
        return {"updated": updated, "total_checked": len(asset_ids)}

    @router.post("/prices/backfill-daily", response_model=DailyBackfillResponse, responses={400: {"model": ErrorResponse}})
    def backfill_daily_prices(
        portfolio_id: int,
        days: int = Query(default=365, ge=30, le=2000),
        asset_scope: str = Query(default="target", pattern="^(target|transactions|all)$"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> DailyBackfillResponse:
        if asset_scope == "target":
            ensure_target_allocation_enabled()
        endpoint = f"prices_backfill_daily:{portfolio_id}:{days}:{asset_scope}"
        if idempotency_key:
            cached = repo.get_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint, user_id=_auth.user_id)
            if cached:
                return DailyBackfillResponse.model_validate(cached)
        try:
            response = historical_service.backfill_daily(portfolio_id=portfolio_id, days=days, asset_scope=asset_scope, user_id=_auth.user_id)
            if idempotency_key:
                repo.save_idempotency_response(
                    idempotency_key=idempotency_key, endpoint=endpoint, response_payload=response.model_dump(mode="json"), user_id=_auth.user_id
                )
            return response
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc
