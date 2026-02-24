
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date

from fastapi import Depends, FastAPI, Header, Query, Request, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthContext, require_auth
from .config import get_settings
from .db import engine
from .errors import AppError
from .finance_client import TwelveDataClient
from .historical_service import HistoricalIngestionService
from .models import (
    AllocationItem,
    AssetLatestQuoteResponse,
    AssetCreate,
    AssetDiscoverItem,
    AssetDiscoverResponse,
    AssetEnsureRequest,
    AssetEnsureResponse,
    AssetProviderSymbolCreate,
    AssetProviderSymbolRead,
    AssetRead,
    DailyBackfillResponse,
    ErrorResponse,
    PortfolioCreate,
    PortfolioRead,
    PortfolioSummary,
    PortfolioUpdate,
    PortfolioTargetAllocationItem,
    PortfolioTargetAssetPerformanceResponse,
    PortfolioTargetAssetIntradayPerformanceResponse,
    PortfolioTargetIntradayResponse,
    PortfolioTargetPerformanceResponse,
    PortfolioTargetAllocationUpsert,
    Position,
    PriceRefreshResponse,
    TimeSeriesPoint,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
    TransactionUpdate,
)
from .pricing_service import PriceIngestionService
from .repository import PortfolioRepository
from .scheduler import PriceRefreshScheduler

settings = get_settings()
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

repo = PortfolioRepository(engine)
pricing_service = PriceIngestionService(settings, repo)
historical_service = HistoricalIngestionService(settings, repo)
scheduler = PriceRefreshScheduler(settings, pricing_service)
finance_client = TwelveDataClient(
    base_url=settings.finance_api_base_url,
    api_key=settings.finance_api_key,
    timeout_seconds=settings.finance_request_timeout_seconds,
    max_retries=settings.finance_max_retries,
    retry_backoff_seconds=settings.finance_retry_backoff_seconds,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title="Valore365 API", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": str(exc)}})


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/portfolios", response_model=PortfolioRead, responses={400: {"model": ErrorResponse}})
def create_portfolio(payload: PortfolioCreate, _auth: AuthContext = Depends(require_auth)) -> PortfolioRead:
    try:
        return repo.create_portfolio(payload)
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.get("/admin/portfolios", response_model=list[PortfolioRead], responses={400: {"model": ErrorResponse}})
def admin_list_portfolios(_auth: AuthContext = Depends(require_auth)) -> list[PortfolioRead]:
    return repo.list_portfolios()


@router.patch(
    "/portfolios/{portfolio_id}",
    response_model=PortfolioRead,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    _auth: AuthContext = Depends(require_auth),
) -> PortfolioRead:
    try:
        return repo.update_portfolio(portfolio_id, payload)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.delete(
    "/portfolios/{portfolio_id}",
    responses={404: {"model": ErrorResponse}},
)
def delete_portfolio(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    try:
        repo.delete_portfolio(portfolio_id)
        return {"status": "ok"}
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.post("/assets", response_model=AssetRead, responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
def create_asset(payload: AssetCreate, _auth: AuthContext = Depends(require_auth)) -> AssetRead:
    try:
        return repo.create_asset(payload)
    except ValueError as exc:
        message = str(exc)
        if "gia esistente" in message.lower() or "duplicato" in message.lower() or "vincolo" in message.lower():
            raise AppError(code="conflict", message=message, status_code=409) from exc
        raise AppError(code="bad_request", message=message, status_code=400) from exc


@router.get("/assets/search")
def search_assets(q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth)) -> dict[str, list[dict[str, str]]]:
    return {"assets": repo.search_assets(q)}


@router.get("/assets/discover", response_model=AssetDiscoverResponse)
def discover_assets(q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth)) -> AssetDiscoverResponse:
    db_items = repo.search_assets(q)
    try:
        provider_items = finance_client.search_symbols(q)
    except Exception:
        provider_items = []

    results: list[AssetDiscoverItem] = []
    db_symbols = {str(item.get("symbol", "")).upper() for item in db_items}

    for item in db_items:
        symbol = str(item.get("symbol", ""))
        results.append(
            AssetDiscoverItem(
                key=f'db:{item["id"]}',
                source='db',
                asset_id=int(item["id"]),
                symbol=symbol,
                name=item.get("name"),
            )
        )

    seen_provider_keys: set[str] = set()
    for item in provider_items:
        provider_symbol = (item.symbol or "").strip().upper()
        if not provider_symbol:
            continue
        exchange = (item.exchange or "").strip() or None
        dedupe_key = f"{provider_symbol}|{exchange or ''}"
        if dedupe_key in seen_provider_keys:
            continue
        seen_provider_keys.add(dedupe_key)
        if provider_symbol in db_symbols:
            continue
        results.append(
            AssetDiscoverItem(
                key=f'provider:{provider_symbol}:{exchange or ""}',
                source='provider',
                asset_id=None,
                symbol=provider_symbol,
                name=item.instrument_name,
                exchange=exchange,
                provider='twelvedata',
                provider_symbol=provider_symbol,
            )
        )

    return AssetDiscoverResponse(items=results)


@router.post(
    "/assets/ensure",
    response_model=AssetEnsureResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def ensure_asset(payload: AssetEnsureRequest, _auth: AuthContext = Depends(require_auth)) -> AssetEnsureResponse:
    if payload.source == "db":
        if payload.asset_id is None:
            raise AppError(code="bad_request", message="asset_id obbligatorio per source=db", status_code=400)
        try:
            asset = repo.get_asset(payload.asset_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
        return AssetEnsureResponse(asset_id=asset.id, symbol=asset.symbol, created=False)

    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise AppError(code="bad_request", message="symbol obbligatorio", status_code=400)

    base_ccy = "EUR"
    if payload.portfolio_id is not None:
        try:
            base_ccy = repo.get_portfolio_base_currency(payload.portfolio_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    created = False
    resolved_asset: AssetRead | None = None
    try:
        resolved_asset = repo.create_asset(
            AssetCreate(
                symbol=symbol,
                name=(payload.name or symbol).strip() or symbol,
                asset_type="stock",
                exchange_code=None,
                exchange_name=payload.exchange,
                quote_currency=base_ccy,
                isin=None,
                active=True,
            )
        )
        created = True
    except ValueError:
        matches = repo.search_assets(symbol)
        exact = next((m for m in matches if str(m.get("symbol", "")).upper() == symbol), None)
        if exact is None:
            raise AppError(code="conflict", message="Asset esistente ma non risolvibile", status_code=409)
        try:
            resolved_asset = repo.get_asset(int(exact["id"]))
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    if resolved_asset is None:
        raise AppError(code="bad_request", message="Impossibile risolvere asset", status_code=400)

    try:
        repo.create_asset_provider_symbol(
            AssetProviderSymbolCreate(
                asset_id=resolved_asset.id,
                provider=(payload.provider or "twelvedata").lower(),
                provider_symbol=(payload.provider_symbol or symbol).upper(),
            )
        )
    except ValueError as exc:
        # Ignore duplicate mappings, surface only unexpected errors.
        message = str(exc).lower()
        if "esistente" not in message and "duplicato" not in message and "vincolo" not in message:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    return AssetEnsureResponse(asset_id=resolved_asset.id, symbol=resolved_asset.symbol, created=created)


@router.get("/assets/{asset_id}", response_model=AssetRead, responses={404: {"model": ErrorResponse}})
def get_asset(asset_id: int, _auth: AuthContext = Depends(require_auth)) -> AssetRead:
    try:
        return repo.get_asset(asset_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.post(
    "/asset-provider-symbols",
    response_model=AssetProviderSymbolRead,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_asset_provider_symbol(
    payload: AssetProviderSymbolCreate,
    _auth: AuthContext = Depends(require_auth),
) -> AssetProviderSymbolRead:
    try:
        return repo.create_asset_provider_symbol(payload)
    except ValueError as exc:
        message = str(exc)
        if "gia esistente" in message.lower() or "duplicato" in message.lower() or "vincolo" in message.lower():
            raise AppError(code="conflict", message=message, status_code=409) from exc
        raise AppError(code="bad_request", message=message, status_code=400) from exc


@router.get(
    "/portfolios/{portfolio_id}/transactions",
    response_model=list[TransactionListItem],
    responses={404: {"model": ErrorResponse}},
)
def list_transactions(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[TransactionListItem]:
    try:
        return repo.list_transactions(portfolio_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.post("/transactions", response_model=TransactionRead, responses={400: {"model": ErrorResponse}})
def create_transaction(payload: TransactionCreate, _auth: AuthContext = Depends(require_auth)) -> TransactionRead:
    try:
        return repo.create_transaction(payload)
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.patch(
    "/transactions/{transaction_id}",
    response_model=TransactionRead,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    _auth: AuthContext = Depends(require_auth),
) -> TransactionRead:
    try:
        return repo.update_transaction(transaction_id, payload)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovata" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.delete(
    "/transactions/{transaction_id}",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def delete_transaction(transaction_id: int, _auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    try:
        repo.delete_transaction(transaction_id)
        return {"status": "ok"}
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovata" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.post("/prices/refresh", response_model=PriceRefreshResponse, responses={400: {"model": ErrorResponse}})
def refresh_prices(
    portfolio_id: int | None = None,
    asset_scope: str = Query(default="target", pattern="^(target|transactions|all)$"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _auth: AuthContext = Depends(require_auth),
) -> PriceRefreshResponse:
    endpoint = f"prices_refresh:{portfolio_id}:{asset_scope}"
    if idempotency_key:
        cached = repo.get_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint)
        if cached:
            return PriceRefreshResponse.model_validate(cached)
    try:
        response = pricing_service.refresh_prices(portfolio_id=portfolio_id, asset_scope=asset_scope)
        if idempotency_key:
            repo.save_idempotency_response(
                idempotency_key=idempotency_key, endpoint=endpoint, response_payload=response.model_dump(mode="json")
            )
        return response
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.post("/prices/backfill-daily", response_model=DailyBackfillResponse, responses={400: {"model": ErrorResponse}})
def backfill_daily_prices(
    portfolio_id: int,
    days: int = Query(default=365, ge=30, le=2000),
    asset_scope: str = Query(default="target", pattern="^(target|transactions|all)$"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _auth: AuthContext = Depends(require_auth),
) -> DailyBackfillResponse:
    endpoint = f"prices_backfill_daily:{portfolio_id}:{days}:{asset_scope}"
    if idempotency_key:
        cached = repo.get_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint)
        if cached:
            return DailyBackfillResponse.model_validate(cached)
    try:
        response = historical_service.backfill_daily(portfolio_id=portfolio_id, days=days, asset_scope=asset_scope)
        if idempotency_key:
            repo.save_idempotency_response(
                idempotency_key=idempotency_key, endpoint=endpoint, response_payload=response.model_dump(mode="json")
            )
        return response
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.get(
    "/portfolios/{portfolio_id}/positions", response_model=list[Position], responses={404: {"model": ErrorResponse}}
)
def get_positions(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[Position]:
    try:
        return repo.get_positions(portfolio_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get("/portfolios/{portfolio_id}/summary", response_model=PortfolioSummary, responses={404: {"model": ErrorResponse}})
def get_summary(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> PortfolioSummary:
    try:
        return repo.get_summary(portfolio_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/target-allocation",
    response_model=list[PortfolioTargetAllocationItem],
    responses={404: {"model": ErrorResponse}},
)
def get_target_allocation(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[PortfolioTargetAllocationItem]:
    try:
        return repo.list_portfolio_target_allocations(portfolio_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/target-performance",
    response_model=PortfolioTargetPerformanceResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_target_performance(
    portfolio_id: int, _auth: AuthContext = Depends(require_auth)
) -> PortfolioTargetPerformanceResponse:
    try:
        return repo.get_portfolio_target_performance(portfolio_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/target-performance/intraday",
    response_model=PortfolioTargetIntradayResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_target_performance_intraday(
    portfolio_id: int,
    date: date,
    _auth: AuthContext = Depends(require_auth),
) -> PortfolioTargetIntradayResponse:
    try:
        return repo.get_portfolio_target_intraday_performance(portfolio_id, date)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/target-performance/assets",
    response_model=PortfolioTargetAssetPerformanceResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_target_asset_performance(
    portfolio_id: int,
    _auth: AuthContext = Depends(require_auth),
) -> PortfolioTargetAssetPerformanceResponse:
    try:
        return repo.get_portfolio_target_asset_performance(portfolio_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/target-performance/assets/intraday",
    response_model=PortfolioTargetAssetIntradayPerformanceResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_target_asset_intraday_performance(
    portfolio_id: int,
    date: date,
    _auth: AuthContext = Depends(require_auth),
) -> PortfolioTargetAssetIntradayPerformanceResponse:
    try:
        return repo.get_portfolio_target_asset_intraday_performance(portfolio_id, date)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.post(
    "/portfolios/{portfolio_id}/target-allocation",
    response_model=PortfolioTargetAllocationItem,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def upsert_target_allocation(
    portfolio_id: int,
    payload: PortfolioTargetAllocationUpsert,
    _auth: AuthContext = Depends(require_auth),
) -> PortfolioTargetAllocationItem:
    try:
        return repo.upsert_portfolio_target_allocation(portfolio_id, payload)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.delete(
    "/portfolios/{portfolio_id}/target-allocation/{asset_id}",
    responses={404: {"model": ErrorResponse}},
)
def delete_target_allocation(portfolio_id: int, asset_id: int, _auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    try:
        repo.delete_portfolio_target_allocation(portfolio_id, asset_id)
        return {"status": "ok"}
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/timeseries",
    response_model=list[TimeSeriesPoint],
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_timeseries(
    portfolio_id: int,
    range: str = Query(default="1y", pattern="^1y$"),
    interval: str = Query(default="1d", pattern="^1d$"),
    _auth: AuthContext = Depends(require_auth),
) -> list[TimeSeriesPoint]:
    try:
        return repo.get_timeseries(portfolio_id, range_value=range, interval=interval)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "portfolio non trovato" in message.lower() else 400
        code = "not_found" if status == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status) from exc


@router.get(
    "/portfolios/{portfolio_id}/allocation",
    response_model=list[AllocationItem],
    responses={404: {"model": ErrorResponse}},
)
def get_allocation(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[AllocationItem]:
    try:
        return repo.get_allocation(portfolio_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get("/symbols")
def search_symbols(
    q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth)
) -> dict[str, list[dict[str, str]]]:
    symbols_list = finance_client.search_symbols(q)
    return {"symbols": [asdict(s) for s in symbols_list]}


@router.get(
    "/assets/{asset_id}/latest-quote",
    response_model=AssetLatestQuoteResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_asset_latest_quote(asset_id: int, _auth: AuthContext = Depends(require_auth)) -> AssetLatestQuoteResponse:
    try:
        pricing_asset = repo.get_asset_pricing_symbol(asset_id)
        quote = finance_client.get_quote(pricing_asset.provider_symbol)
        return AssetLatestQuoteResponse(
            asset_id=pricing_asset.asset_id,
            symbol=pricing_asset.symbol,
            provider="twelvedata",
            provider_symbol=pricing_asset.provider_symbol,
            price=quote.price,
            ts=quote.ts,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "asset non trovato" in message.lower() else 400
        code = "not_found" if status == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status) from exc


app.include_router(router, prefix="/api")
 
 
