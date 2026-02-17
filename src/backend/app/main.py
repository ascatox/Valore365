import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .auth import AuthContext, require_auth
from .config import get_settings
from .db import engine
from .errors import AppError
from .historical_service import HistoricalIngestionService
from .models import (
    AllocationItem,
    AssetCreate,
    AssetProviderSymbolCreate,
    AssetProviderSymbolRead,
    AssetRead,
    DailyBackfillResponse,
    ErrorResponse,
    PortfolioSummary,
    Position,
    PriceRefreshResponse,
    TimeSeriesPoint,
    TransactionCreate,
    TransactionRead,
)
from .pricing_service import PriceIngestionService
from .repository import PortfolioRepository
from .scheduler import PriceRefreshScheduler

settings = get_settings()
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')

repo = PortfolioRepository(engine)
pricing_service = PriceIngestionService(settings, repo)
historical_service = HistoricalIngestionService(settings, repo)
scheduler = PriceRefreshScheduler(settings, pricing_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title='Valore365 API', version='0.6.0', lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={'error': {'code': exc.code, 'message': exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={'error': {'code': 'validation_error', 'message': str(exc)}})


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.post('/assets', response_model=AssetRead, responses={400: {'model': ErrorResponse}, 409: {'model': ErrorResponse}})
def create_asset(payload: AssetCreate, _auth: AuthContext = Depends(require_auth)) -> AssetRead:
    try:
        return repo.create_asset(payload)
    except ValueError as exc:
        message = str(exc)
        if 'gia esistente' in message.lower() or 'duplicato' in message.lower() or 'vincolo' in message.lower():
            raise AppError(code='conflict', message=message, status_code=409) from exc
        raise AppError(code='bad_request', message=message, status_code=400) from exc


@app.get('/assets/{asset_id}', response_model=AssetRead, responses={404: {'model': ErrorResponse}})
def get_asset(asset_id: int, _auth: AuthContext = Depends(require_auth)) -> AssetRead:
    try:
        return repo.get_asset(asset_id)
    except ValueError as exc:
        raise AppError(code='not_found', message=str(exc), status_code=404) from exc


@app.post('/asset-provider-symbols', response_model=AssetProviderSymbolRead, responses={400: {'model': ErrorResponse}, 409: {'model': ErrorResponse}})
def create_asset_provider_symbol(
    payload: AssetProviderSymbolCreate,
    _auth: AuthContext = Depends(require_auth),
) -> AssetProviderSymbolRead:
    try:
        return repo.create_asset_provider_symbol(payload)
    except ValueError as exc:
        message = str(exc)
        if 'gia esistente' in message.lower() or 'duplicato' in message.lower() or 'vincolo' in message.lower():
            raise AppError(code='conflict', message=message, status_code=409) from exc
        raise AppError(code='bad_request', message=message, status_code=400) from exc


@app.post('/transactions', response_model=TransactionRead, responses={400: {'model': ErrorResponse}})
def create_transaction(payload: TransactionCreate, _auth: AuthContext = Depends(require_auth)) -> TransactionRead:
    try:
        return repo.create_transaction(payload)
    except ValueError as exc:
        raise AppError(code='bad_request', message=str(exc), status_code=400) from exc


@app.post('/prices/refresh', response_model=PriceRefreshResponse, responses={400: {'model': ErrorResponse}})
def refresh_prices(
    portfolio_id: int | None = None,
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
    _auth: AuthContext = Depends(require_auth),
) -> PriceRefreshResponse:
    endpoint = 'prices_refresh'
    if idempotency_key:
        cached = repo.get_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint)
        if cached:
            return PriceRefreshResponse.model_validate(cached)
    try:
        response = pricing_service.refresh_prices(portfolio_id=portfolio_id)
        if idempotency_key:
            repo.save_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint, response_payload=response.model_dump(mode='json'))
        return response
    except ValueError as exc:
        raise AppError(code='bad_request', message=str(exc), status_code=400) from exc


@app.post('/prices/backfill-daily', response_model=DailyBackfillResponse, responses={400: {'model': ErrorResponse}})
def backfill_daily_prices(
    portfolio_id: int,
    days: int = Query(default=365, ge=30, le=2000),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
    _auth: AuthContext = Depends(require_auth),
) -> DailyBackfillResponse:
    endpoint = f'prices_backfill_daily:{portfolio_id}:{days}'
    if idempotency_key:
        cached = repo.get_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint)
        if cached:
            return DailyBackfillResponse.model_validate(cached)
    try:
        response = historical_service.backfill_daily(portfolio_id=portfolio_id, days=days)
        if idempotency_key:
            repo.save_idempotency_response(idempotency_key=idempotency_key, endpoint=endpoint, response_payload=response.model_dump(mode='json'))
        return response
    except ValueError as exc:
        raise AppError(code='bad_request', message=str(exc), status_code=400) from exc


@app.get('/portfolios/{portfolio_id}/positions', response_model=list[Position], responses={404: {'model': ErrorResponse}})
def get_positions(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[Position]:
    try:
        return repo.get_positions(portfolio_id)
    except ValueError as exc:
        raise AppError(code='not_found', message=str(exc), status_code=404) from exc


@app.get('/portfolios/{portfolio_id}/summary', response_model=PortfolioSummary, responses={404: {'model': ErrorResponse}})
def get_summary(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> PortfolioSummary:
    try:
        return repo.get_summary(portfolio_id)
    except ValueError as exc:
        raise AppError(code='not_found', message=str(exc), status_code=404) from exc


@app.get('/portfolios/{portfolio_id}/timeseries', response_model=list[TimeSeriesPoint], responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse}})
def get_timeseries(
    portfolio_id: int,
    range: str = Query(default='1y', pattern='^1y$'),
    interval: str = Query(default='1d', pattern='^1d$'),
    _auth: AuthContext = Depends(require_auth),
) -> list[TimeSeriesPoint]:
    try:
        return repo.get_timeseries(portfolio_id, range_value=range, interval=interval)
    except ValueError as exc:
        message = str(exc)
        status = 404 if 'portfolio non trovato' in message.lower() else 400
        code = 'not_found' if status == 404 else 'bad_request'
        raise AppError(code=code, message=message, status_code=status) from exc


@app.get('/portfolios/{portfolio_id}/allocation', response_model=list[AllocationItem], responses={404: {'model': ErrorResponse}})
def get_allocation(portfolio_id: int, _auth: AuthContext = Depends(require_auth)) -> list[AllocationItem]:
    try:
        return repo.get_allocation(portfolio_id)
    except ValueError as exc:
        raise AppError(code='not_found', message=str(exc), status_code=404) from exc


@app.get('/assets/search')
def search_assets(q: str = Query(min_length=1), _auth: AuthContext = Depends(require_auth)) -> dict[str, list[dict[str, str]]]:
    return {'items': repo.search_assets(q)}
