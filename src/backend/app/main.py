
import logging
import threading
import time as _time
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime

from fastapi import Depends, FastAPI, Header, Query, Request, APIRouter
from sqlalchemy import text
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from fastapi import UploadFile, File

from .auth import AuthContext, require_auth
from .config import get_settings
from .csv_service import CsvImportService
from .db import engine
from .errors import AppError
from .finance_client import make_finance_client
from .historical_service import HistoricalIngestionService
from .models import (
    AllocationItem,
    AssetCoverageItem,
    AssetLatestQuoteResponse,
    AssetCreate,
    AssetDiscoverItem,
    AssetDiscoverResponse,
    AssetEnsureRequest,
    AssetEnsureResponse,
    AssetProviderSymbolCreate,
    AssetProviderSymbolRead,
    AssetRead,
    CashBalanceResponse,
    CashFlowTimelineResponse,
    CashMovementCreate,
    CsvImportCommitResponse,
    CsvImportPreviewResponse,
    DailyBackfillResponse,
    DataCoverageResponse,
    ErrorResponse,
    MarketCategory,
    MarketQuoteItem,
    MarketQuotesResponse,
    PacExecutionConfirm,
    PacExecutionRead,
    PacRuleCreate,
    PacRuleRead,
    PacRuleUpdate,
    PerformanceSummary,
    PortfolioCreate,
    PortfolioCloneRequest,
    PortfolioCloneResponse,
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
    RebalancePreviewItem,
    RebalanceCommitCreatedItem,
    RebalanceCommitItemInput,
    RebalanceCommitRequest,
    RebalanceCommitResponse,
    RebalancePreviewRequest,
    RebalancePreviewResponse,
    RebalancePreviewSummary,
    TimeSeriesPoint,
    TWRResult,
    TWRTimeseriesPoint,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
    TransactionUpdate,
    UserSettingsRead,
    UserSettingsUpdate,
    MWRResult,
)
from .pac_service import PacExecutionService
from .performance_service import PerformanceService
from .pricing_service import PriceIngestionService
from .repository import PortfolioRepository
from .scheduler import PriceRefreshScheduler

settings = get_settings()
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

repo = PortfolioRepository(engine)
pricing_service = PriceIngestionService(settings, repo)
historical_service = HistoricalIngestionService(settings, repo)
csv_import_service = CsvImportService(repo)
pac_service = PacExecutionService(engine)
performance_service = PerformanceService(repo)
scheduler = PriceRefreshScheduler(settings, pricing_service, pac_service)
finance_client = make_finance_client(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title="Valore365 API", version="0.6.0", lifespan=lifespan)

if settings.app_env == "dev":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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


@router.get("/settings/user", response_model=UserSettingsRead)
def get_user_settings(_auth: AuthContext = Depends(require_auth)) -> UserSettingsRead:
    try:
        return repo.get_user_settings(_auth.user_id)
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.put("/settings/user", response_model=UserSettingsRead, responses={400: {"model": ErrorResponse}})
def update_user_settings(payload: UserSettingsUpdate, _auth: AuthContext = Depends(require_auth)) -> UserSettingsRead:
    try:
        return repo.upsert_user_settings(_auth.user_id, payload)
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.post("/portfolios", response_model=PortfolioRead, responses={400: {"model": ErrorResponse}})
def create_portfolio(payload: PortfolioCreate, _auth: AuthContext = Depends(require_auth)) -> PortfolioRead:
    try:
        return repo.create_portfolio(payload, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.get("/portfolios", response_model=list[PortfolioRead], responses={400: {"model": ErrorResponse}})
def list_portfolios(_auth: AuthContext = Depends(require_auth)) -> list[PortfolioRead]:
    return repo.list_portfolios(_auth.user_id)


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
        return repo.update_portfolio(portfolio_id, payload, _auth.user_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.post(
    "/portfolios/{portfolio_id}/clone",
    response_model=PortfolioCloneResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def clone_portfolio(
    portfolio_id: int,
    payload: PortfolioCloneRequest,
    _auth: AuthContext = Depends(require_auth),
) -> PortfolioCloneResponse:
    try:
        return repo.clone_portfolio(portfolio_id, payload, _auth.user_id)
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
        repo.delete_portfolio(portfolio_id, _auth.user_id)
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
                provider=settings.finance_provider,
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
            base_ccy = repo.get_portfolio_base_currency(payload.portfolio_id, user_id=_auth.user_id)
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
                provider=(payload.provider or settings.finance_provider).lower(),
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
        return repo.list_transactions(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.post("/transactions", response_model=TransactionRead, responses={400: {"model": ErrorResponse}})
def create_transaction(payload: TransactionCreate, _auth: AuthContext = Depends(require_auth)) -> TransactionRead:
    try:
        result = repo.create_transaction(payload, _auth.user_id)
        threading.Thread(
            target=historical_service.backfill_single_asset,
            kwargs={"asset_id": payload.asset_id, "portfolio_id": payload.portfolio_id},
            daemon=True,
        ).start()
        return result
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
        return repo.update_transaction(transaction_id, payload, _auth.user_id)
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
        repo.delete_transaction(transaction_id, _auth.user_id)
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


@router.get(
    "/portfolios/{portfolio_id}/positions", response_model=list[Position], responses={404: {"model": ErrorResponse}}
)
def get_positions(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[Position]:
    try:
        return repo.get_positions(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get("/portfolios/{portfolio_id}/summary", response_model=PortfolioSummary, responses={404: {"model": ErrorResponse}})
def get_summary(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> PortfolioSummary:
    try:
        return repo.get_summary(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/performance/summary",
    response_model=PerformanceSummary,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_performance_summary(
    portfolio_id: int,
    period: str = Query(default="1y", pattern="^(1m|3m|6m|ytd|1y|3y|all)$"),
    _auth: AuthContext = Depends(require_auth),
) -> PerformanceSummary:
    try:
        return performance_service.get_performance_summary(portfolio_id, _auth.user_id, period)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.get(
    "/portfolios/{portfolio_id}/performance/twr",
    response_model=TWRResult,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_performance_twr(
    portfolio_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _auth: AuthContext = Depends(require_auth),
) -> TWRResult:
    try:
        return performance_service.calculate_twr(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.get(
    "/portfolios/{portfolio_id}/performance/twr/timeseries",
    response_model=list[TWRTimeseriesPoint],
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_performance_twr_timeseries(
    portfolio_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _auth: AuthContext = Depends(require_auth),
) -> list[TWRTimeseriesPoint]:
    try:
        return performance_service.get_twr_timeseries(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.get(
    "/portfolios/{portfolio_id}/performance/mwr",
    response_model=MWRResult,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_performance_mwr(
    portfolio_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    _auth: AuthContext = Depends(require_auth),
) -> MWRResult:
    try:
        return performance_service.calculate_mwr(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.get(
    "/portfolios/{portfolio_id}/target-allocation",
    response_model=list[PortfolioTargetAllocationItem],
    responses={404: {"model": ErrorResponse}},
)
def get_target_allocation(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[PortfolioTargetAllocationItem]:
    try:
        return repo.list_portfolio_target_allocations(portfolio_id, _auth.user_id)
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
        return repo.get_portfolio_target_performance(portfolio_id, _auth.user_id)
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
        return repo.get_portfolio_target_intraday_performance(portfolio_id, date, _auth.user_id)
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
        return repo.get_portfolio_target_asset_performance(portfolio_id, _auth.user_id)
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
        return repo.get_portfolio_target_asset_intraday_performance(portfolio_id, date, _auth.user_id)
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
        result = repo.upsert_portfolio_target_allocation(portfolio_id, payload, _auth.user_id)
        threading.Thread(
            target=historical_service.backfill_single_asset,
            kwargs={"asset_id": payload.asset_id, "portfolio_id": portfolio_id},
            daemon=True,
        ).start()
        return result
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
        repo.delete_portfolio_target_allocation(portfolio_id, asset_id, _auth.user_id)
        return {"status": "ok"}
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/data-coverage",
    response_model=DataCoverageResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_data_coverage(
    portfolio_id: int,
    days: int = Query(default=365, ge=1, le=2000),
    threshold_pct: float = Query(default=80, ge=0, le=100),
    _auth: AuthContext = Depends(require_auth),
) -> DataCoverageResponse:
    try:
        rows = repo.get_price_coverage(portfolio_id, days=days, user_id=_auth.user_id)
        assets = [AssetCoverageItem(**r) for r in rows]
        sufficient = all(a.coverage_pct >= threshold_pct for a in assets) if assets else True
        return DataCoverageResponse(
            portfolio_id=portfolio_id,
            days=days,
            sufficient=sufficient,
            threshold_pct=threshold_pct,
            assets=assets,
        )
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.post(
    "/portfolios/{portfolio_id}/rebalance/preview",
    response_model=RebalancePreviewResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def rebalance_preview(
    portfolio_id: int,
    payload: RebalancePreviewRequest,
    _auth: AuthContext = Depends(require_auth),
) -> RebalancePreviewResponse:
    try:
        target_alloc = repo.list_portfolio_target_allocations(portfolio_id, _auth.user_id)
        summary = repo.get_summary(portfolio_id, _auth.user_id)
        allocation = repo.get_allocation(portfolio_id, _auth.user_id)
        positions = repo.get_positions(portfolio_id, _auth.user_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc

    if not target_alloc:
        return RebalancePreviewResponse(
            portfolio_id=portfolio_id,
            base_currency=summary.base_currency,
            mode=payload.mode,
            trade_at=payload.trade_at,
            summary=RebalancePreviewSummary(
                proposed_buy_total=0.0,
                proposed_sell_total=0.0,
                cash_input=round(float(payload.cash_to_allocate or 0), 2),
                estimated_cash_residual=round(float(payload.cash_to_allocate or 0), 2),
                generated_count=0,
                skipped_count=0,
            ),
            items=[],
            warnings=["Nessuna allocazione target configurata"],
        )

    if payload.mode == "buy_only" and (payload.cash_to_allocate is None or payload.cash_to_allocate <= 0):
        raise AppError(code="bad_request", message="cash_to_allocate > 0 obbligatorio in modalità buy_only", status_code=400)

    allocation_by_asset = {item.asset_id: item for item in allocation}
    position_by_asset = {item.asset_id: item for item in positions}
    quote_ccy_by_asset = repo.get_quote_currencies_for_assets([t.asset_id for t in target_alloc])

    quote_by_asset: dict[int, float] = {}
    skipped: list[str] = []
    warnings: list[str] = []

    for target in target_alloc:
        aid = target.asset_id
        quote_ccy = (quote_ccy_by_asset.get(aid) or summary.base_currency).upper()
        if quote_ccy != summary.base_currency.upper():
            skipped.append(f"{target.symbol}: valuta {quote_ccy} diversa da {summary.base_currency} (preview MVP)")
            continue

        try:
            if payload.use_latest_prices:
                pricing_asset = repo.get_asset_pricing_symbol(aid, provider=settings.finance_provider)
                quote = finance_client.get_quote(pricing_asset.provider_symbol)
                quote_by_asset[aid] = float(quote.price)
            else:
                pos = position_by_asset.get(aid)
                if pos and pos.market_price > 0:
                    quote_by_asset[aid] = float(pos.market_price)
                else:
                    skipped.append(f"{target.symbol}: prezzo non disponibile")
        except Exception as exc:  # noqa: BLE001 - preview should degrade gracefully
            skipped.append(f"{target.symbol}: prezzo non disponibile ({exc})")

    total_market_value = max(float(summary.market_value), 0.0)
    cash_input = float(payload.cash_to_allocate or 0.0)
    min_order = float(payload.min_order_value or 0.0)

    candidate_rows: list[dict] = []
    for target in target_alloc:
        current_alloc = allocation_by_asset.get(target.asset_id)
        pos = position_by_asset.get(target.asset_id)
        current_weight = float(current_alloc.weight_pct) if current_alloc else 0.0
        current_value = float(current_alloc.market_value) if current_alloc else 0.0
        current_qty = float(pos.quantity) if pos else 0.0
        drift = current_weight - float(target.weight_pct)
        quote_price = quote_by_asset.get(target.asset_id)
        quote_ccy = (quote_ccy_by_asset.get(target.asset_id) or summary.base_currency).upper()

        if payload.mode == "buy_only" and current_weight >= float(target.weight_pct):
            continue
        if payload.mode == "sell_only" and current_weight <= float(target.weight_pct):
            continue
        if payload.mode == "rebalance" and abs(drift) <= 0:
            continue

        side = "sell" if drift > 0 else "buy"
        if payload.mode == "buy_only":
            side = "buy"
        elif payload.mode == "sell_only":
            side = "sell"

        score = abs(drift) if payload.mode == "rebalance" else (
            max(float(target.weight_pct) - current_weight, 0.0) if side == "buy" else max(current_weight - float(target.weight_pct), 0.0)
        )
        if score <= 0:
            continue

        candidate_rows.append(
            {
                "asset_id": target.asset_id,
                "symbol": target.symbol,
                "name": target.name,
                "target_weight_pct": float(target.weight_pct),
                "current_weight_pct": current_weight,
                "drift_pct": round(drift, 2),
                "current_quantity": current_qty,
                "current_value": current_value,
                "side": side,
                "price": quote_price,
                "trade_currency": quote_ccy,
                "score": score,
            }
        )

    candidate_rows.sort(key=lambda r: r["score"], reverse=True)
    considered_rows = candidate_rows[: payload.max_transactions * 3]

    generated: list[RebalancePreviewItem] = []

    def _rounded_qty(raw_qty: float) -> float:
        if payload.rounding == "integer":
            qty = float(int(raw_qty))
            return qty if qty > 0 else 0.0
        return round(raw_qty, 8)

    def _append_item(row: dict, order_value: float) -> None:
        price = float(row["price"])
        qty = _rounded_qty(order_value / price if price > 0 else 0.0)
        gross_total = round(qty * price, 2)
        if qty <= 0 or gross_total <= 0:
            skipped.append(f"{row['symbol']}: quantità non valida dopo arrotondamento")
            return
        if min_order > 0 and gross_total < min_order:
            skipped.append(f"{row['symbol']}: ordine sotto soglia minima ({gross_total:.2f} < {min_order:.2f})")
            return
        if row["side"] == "sell" and qty > float(row["current_quantity"]) + 1e-9:
            skipped.append(f"{row['symbol']}: quantità in vendita superiore al posseduto")
            return

        generated.append(
            RebalancePreviewItem(
                asset_id=int(row["asset_id"]),
                symbol=str(row["symbol"]),
                name=str(row["name"]),
                target_weight_pct=round(float(row["target_weight_pct"]), 2),
                current_weight_pct=round(float(row["current_weight_pct"]), 2),
                drift_pct=round(float(row["drift_pct"]), 2),
                current_quantity=round(float(row["current_quantity"]), 8),
                side=row["side"],
                trade_currency=str(row["trade_currency"]),
                price=round(price, 6),
                quantity=qty,
                gross_total=gross_total,
                tradable=True,
                skip_reason=None,
            )
        )

    tradable_rows: list[dict] = []
    for row in considered_rows:
        if row["price"] is None or float(row["price"]) <= 0:
            skipped.append(f"{row['symbol']}: prezzo non disponibile")
            continue
        if str(row["trade_currency"]).upper() != summary.base_currency.upper():
            skipped.append(f"{row['symbol']}: valuta {row['trade_currency']} non supportata nel preview MVP")
            continue
        tradable_rows.append(row)

    if payload.mode == "buy_only":
        buy_rows = [r for r in tradable_rows if r["side"] == "buy"][: payload.max_transactions]
        score_sum = sum(float(r["score"]) for r in buy_rows)
        if score_sum <= 0:
            warnings.append("Nessun asset sotto target disponibile per acquisti")
        else:
            for row in buy_rows:
                proportional_amount = cash_input * (float(row["score"]) / score_sum)
                _append_item(row, proportional_amount)
    elif payload.mode == "sell_only":
        sell_rows = [r for r in tradable_rows if r["side"] == "sell"][: payload.max_transactions]
        for row in sell_rows:
            if total_market_value <= 0:
                continue
            overweight_pct = max(float(row["drift_pct"]), 0.0)
            proposed_value = min(float(row["current_value"]), (overweight_pct / 100.0) * total_market_value)
            _append_item(row, proposed_value)
    else:  # rebalance
        rows = tradable_rows[: payload.max_transactions]
        for row in rows:
            if total_market_value <= 0:
                continue
            drift_abs_pct = abs(float(row["drift_pct"]))
            proposed_value = min(float(row["current_value"]) if row["side"] == "sell" else 10**18, (drift_abs_pct / 100.0) * total_market_value)
            _append_item(row, proposed_value)

    generated.sort(key=lambda i: abs(i.drift_pct), reverse=True)
    generated = generated[: payload.max_transactions]

    proposed_buy_total = round(sum(i.gross_total for i in generated if i.side == "buy"), 2)
    proposed_sell_total = round(sum(i.gross_total for i in generated if i.side == "sell"), 2)
    estimated_cash_residual = round(cash_input + proposed_sell_total - proposed_buy_total, 2)

    if skipped:
        warnings.append(f"Asset/proposte saltate: {len(skipped)}")

    return RebalancePreviewResponse(
        portfolio_id=portfolio_id,
        base_currency=summary.base_currency,
        mode=payload.mode,
        trade_at=payload.trade_at,
        summary=RebalancePreviewSummary(
            proposed_buy_total=proposed_buy_total,
            proposed_sell_total=proposed_sell_total,
            cash_input=round(cash_input, 2),
            estimated_cash_residual=estimated_cash_residual,
            generated_count=len(generated),
            skipped_count=len(skipped),
        ),
        items=generated,
        warnings=warnings + skipped[:20],
    )


@router.post(
    "/portfolios/{portfolio_id}/rebalance/commit",
    response_model=RebalanceCommitResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def rebalance_commit(
    portfolio_id: int,
    payload: RebalanceCommitRequest,
    _auth: AuthContext = Depends(require_auth),
) -> RebalanceCommitResponse:
    try:
        portfolio_summary = repo.get_summary(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    created_items: list[RebalanceCommitCreatedItem] = []
    errors: list[str] = []
    touched_assets: set[int] = set()

    for idx, item in enumerate(payload.items, start=1):
        try:
            tx = repo.create_transaction(
                TransactionCreate(
                    portfolio_id=portfolio_id,
                    asset_id=item.asset_id,
                    side=item.side,
                    trade_at=payload.trade_at,
                    quantity=item.quantity,
                    price=item.price,
                    fees=item.fees,
                    taxes=item.taxes,
                    trade_currency=portfolio_summary.base_currency,
                    notes=item.notes,
                ),
                _auth.user_id,
            )
            created_items.append(
                RebalanceCommitCreatedItem(
                    transaction_id=tx.id,
                    asset_id=tx.asset_id,
                    side=tx.side,
                    quantity=tx.quantity,
                    price=tx.price,
                )
            )
            touched_assets.add(tx.asset_id)
        except ValueError as exc:
            errors.append(f"Riga {idx} asset_id={item.asset_id}: {exc}")

    for asset_id in touched_assets:
        threading.Thread(
            target=historical_service.backfill_single_asset,
            kwargs={"asset_id": asset_id, "portfolio_id": portfolio_id},
            daemon=True,
        ).start()

    return RebalanceCommitResponse(
        portfolio_id=portfolio_id,
        requested=len(payload.items),
        created=len(created_items),
        failed=len(payload.items) - len(created_items),
        items=created_items,
        errors=errors,
    )


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
        return repo.get_timeseries(portfolio_id, range_value=range, interval=interval, user_id=_auth.user_id)
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
        return repo.get_allocation(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get("/symbols")
def search_symbols(
    q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth)
) -> dict[str, list[dict[str, str | None]]]:
    symbols_list = finance_client.search_symbols(q)
    return {"symbols": [asdict(s) for s in symbols_list]}


@router.get(
    "/assets/{asset_id}/latest-quote",
    response_model=AssetLatestQuoteResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_asset_latest_quote(asset_id: int, _auth: AuthContext = Depends(require_auth)) -> AssetLatestQuoteResponse:
    try:
        pricing_asset = repo.get_asset_pricing_symbol(asset_id, provider=settings.finance_provider)
        quote = finance_client.get_quote(pricing_asset.provider_symbol)
        return AssetLatestQuoteResponse(
            asset_id=pricing_asset.asset_id,
            symbol=pricing_asset.symbol,
            provider=settings.finance_provider,
            provider_symbol=pricing_asset.provider_symbol,
            price=quote.price,
            ts=quote.ts,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "asset non trovato" in message.lower() else 400
        code = "not_found" if status == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status) from exc


MARKET_SYMBOLS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "indices": {
        "label": "Indici",
        "symbols": [
            ("^GSPC", "S&P 500"),
            ("^DJI", "Dow Jones"),
            ("^IXIC", "Nasdaq"),
            ("^STOXX50E", "Euro Stoxx 50"),
            ("FTSEMIB.MI", "FTSE MIB"),
            ("^FTSE", "FTSE 100"),
            ("^GDAXI", "DAX"),
            ("^N225", "Nikkei 225"),
        ],
    },
    "commodities": {
        "label": "Materie Prime",
        "symbols": [
            ("GC=F", "Oro"),
            ("SI=F", "Argento"),
            ("CL=F", "Petrolio WTI"),
        ],
    },
    "crypto": {
        "label": "Criptovalute",
        "symbols": [
            ("BTC-USD", "Bitcoin"),
            ("ETH-USD", "Ethereum"),
            ("SOL-USD", "Solana"),
        ],
    },
}


@router.get("/markets/quotes", response_model=MarketQuotesResponse)
def get_market_quotes(_auth: AuthContext = Depends(require_auth)) -> MarketQuotesResponse:
    categories: list[MarketCategory] = []
    delay = settings.finance_symbol_request_delay_seconds
    first_call = True

    for cat_key, cat_info in MARKET_SYMBOLS.items():
        items: list[MarketQuoteItem] = []
        for symbol, name in cat_info["symbols"]:
            if not first_call and delay > 0:
                _time.sleep(delay)
            first_call = False

            try:
                mq = finance_client.get_market_quote(symbol)
                change: float | None = None
                change_pct: float | None = None
                if mq.price is not None and mq.previous_close is not None and mq.previous_close != 0:
                    change = mq.price - mq.previous_close
                    change_pct = (change / mq.previous_close) * 100

                items.append(MarketQuoteItem(
                    symbol=symbol,
                    name=name,
                    price=mq.price,
                    previous_close=mq.previous_close,
                    change=round(change, 4) if change is not None else None,
                    change_pct=round(change_pct, 4) if change_pct is not None else None,
                    ts=mq.ts,
                    error=None if mq.price is not None else "Prezzo non disponibile",
                ))
            except Exception as exc:
                items.append(MarketQuoteItem(
                    symbol=symbol,
                    name=name,
                    error=str(exc),
                ))

        categories.append(MarketCategory(category=cat_key, label=cat_info["label"], items=items))

    return MarketQuotesResponse(categories=categories)



# ---- Feature 2: Cash Movements ----

@router.post("/cash-movements", response_model=TransactionRead, responses={400: {"model": ErrorResponse}})
def create_cash_movement(payload: CashMovementCreate, _auth: AuthContext = Depends(require_auth)) -> TransactionRead:
    try:
        return repo.create_cash_movement(payload, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="bad_request", message=str(exc), status_code=400) from exc


@router.get(
    "/portfolios/{portfolio_id}/cash-balance",
    response_model=CashBalanceResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_cash_balance(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> CashBalanceResponse:
    try:
        return repo.get_computed_cash_balance(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/cash-flow-timeline",
    response_model=CashFlowTimelineResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_cash_flow_timeline(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> CashFlowTimelineResponse:
    try:
        return repo.get_cash_flow_timeline(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


# ---- Feature 3: CSV Import ----

@router.post(
    "/portfolios/{portfolio_id}/csv-import/preview",
    response_model=CsvImportPreviewResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def csv_import_preview(
    portfolio_id: int,
    file: UploadFile = File(...),
    _auth: AuthContext = Depends(require_auth),
) -> CsvImportPreviewResponse:
    try:
        content = await file.read()
        file_content = content.decode("utf-8-sig")
        return csv_import_service.parse_and_validate(
            portfolio_id=portfolio_id,
            user_id=_auth.user_id,
            file_content=file_content,
            filename=file.filename,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.post(
    "/csv-import/{batch_id}/commit",
    response_model=CsvImportCommitResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def csv_import_commit(batch_id: int, _auth: AuthContext = Depends(require_auth)) -> CsvImportCommitResponse:
    try:
        return csv_import_service.commit_batch(batch_id, _auth.user_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.delete("/csv-import/{batch_id}", responses={404: {"model": ErrorResponse}})
def csv_import_cancel(batch_id: int, _auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    try:
        repo.cancel_csv_import_batch(batch_id, _auth.user_id)
        return {"status": "ok"}
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


# ---- Feature 4: PAC Rules ----

@router.post(
    "/portfolios/{portfolio_id}/pac-rules",
    response_model=PacRuleRead,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def create_pac_rule(
    portfolio_id: int,
    payload: PacRuleCreate,
    _auth: AuthContext = Depends(require_auth),
) -> PacRuleRead:
    if payload.portfolio_id != portfolio_id:
        raise AppError(code="bad_request", message="portfolio_id nel path e nel body non corrispondono", status_code=400)
    try:
        rule = repo.create_pac_rule(payload, _auth.user_id)
        repo.generate_pending_executions(rule.id)
        return rule
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovato" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.get(
    "/portfolios/{portfolio_id}/pac-rules",
    response_model=list[PacRuleRead],
    responses={404: {"model": ErrorResponse}},
)
def list_pac_rules(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[PacRuleRead]:
    try:
        return repo.list_pac_rules(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/pac-rules/{rule_id}",
    response_model=PacRuleRead,
    responses={404: {"model": ErrorResponse}},
)
def get_pac_rule(rule_id: int, _auth: AuthContext = Depends(require_auth)) -> PacRuleRead:
    try:
        return repo.get_pac_rule(rule_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.patch(
    "/pac-rules/{rule_id}",
    response_model=PacRuleRead,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def update_pac_rule(
    rule_id: int,
    payload: PacRuleUpdate,
    _auth: AuthContext = Depends(require_auth),
) -> PacRuleRead:
    try:
        rule = repo.update_pac_rule(rule_id, payload, _auth.user_id)
        repo.generate_pending_executions(rule.id)
        return rule
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovata" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.delete("/pac-rules/{rule_id}", responses={404: {"model": ErrorResponse}})
def delete_pac_rule(rule_id: int, _auth: AuthContext = Depends(require_auth)) -> dict[str, str]:
    try:
        repo.delete_pac_rule(rule_id, _auth.user_id)
        return {"status": "ok"}
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/pac-rules/{rule_id}/executions",
    response_model=list[PacExecutionRead],
    responses={404: {"model": ErrorResponse}},
)
def list_pac_executions(rule_id: int, _auth: AuthContext = Depends(require_auth)) -> list[PacExecutionRead]:
    try:
        return repo.list_pac_executions(rule_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.get(
    "/portfolios/{portfolio_id}/pac-executions/pending",
    response_model=list[PacExecutionRead],
    responses={404: {"model": ErrorResponse}},
)
def list_pending_pac_executions(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[PacExecutionRead]:
    try:
        return repo.list_pending_pac_executions(portfolio_id, _auth.user_id)
    except ValueError as exc:
        raise AppError(code="not_found", message=str(exc), status_code=404) from exc


@router.post(
    "/pac-executions/{execution_id}/confirm",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def confirm_pac_execution(
    execution_id: int,
    payload: PacExecutionConfirm,
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, str]:
    try:
        # Get execution details
        with engine.begin() as conn:
            exec_row = conn.execute(
                text(
                    """
                    select e.id, e.pac_rule_id, e.scheduled_date,
                           r.portfolio_id, r.asset_id, r.mode, r.amount::float8, r.quantity::float8
                    from pac_executions e
                    join pac_rules r on r.id = e.pac_rule_id
                    where e.id = :execution_id and e.status = 'pending' and r.owner_user_id = :user_id
                    """
                ),
                {"execution_id": execution_id, "user_id": _auth.user_id},
            ).mappings().fetchone()

        if exec_row is None:
            raise ValueError("Esecuzione PAC non trovata o gia processata")

        # Determine quantity based on mode
        if str(exec_row["mode"]) == "amount":
            quantity = float(exec_row["amount"]) / payload.price if payload.price > 0 else 0.0
        else:
            quantity = float(exec_row["quantity"]) if exec_row["quantity"] else 0.0

        if quantity <= 0:
            raise ValueError("Quantita calcolata non valida")

        from datetime import datetime as dt
        tx = repo.create_transaction(
            TransactionCreate(
                portfolio_id=int(exec_row["portfolio_id"]),
                asset_id=int(exec_row["asset_id"]),
                side="buy",
                trade_at=dt.combine(exec_row["scheduled_date"], dt.min.time()),
                quantity=round(quantity, 8),
                price=payload.price,
                fees=payload.fees,
                taxes=payload.taxes,
                trade_currency=payload.trade_currency,
                notes=payload.notes or f"PAC esecuzione #{execution_id}",
            ),
            _auth.user_id,
        )

        repo.confirm_pac_execution(execution_id, tx.id, payload.price, round(quantity, 8), _auth.user_id)
        return {"status": "ok", "transaction_id": str(tx.id)}

    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovata" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


@router.post(
    "/pac-executions/{execution_id}/skip",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def skip_pac_execution(
    execution_id: int,
    _auth: AuthContext = Depends(require_auth),
) -> dict[str, str]:
    try:
        repo.skip_pac_execution(execution_id, _auth.user_id)
        return {"status": "ok"}
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "non trovata" in message.lower() else 400
        code = "not_found" if status_code == 404 else "bad_request"
        raise AppError(code=code, message=message, status_code=status_code) from exc


app.include_router(router, prefix="/api")
 
 
