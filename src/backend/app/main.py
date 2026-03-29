
import json
import logging
import math
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, APIRouter
from sqlalchemy import text
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that converts NaN/Inf to None instead of raising."""
    def default(self, o: Any) -> Any:
        return super().default(o)

    def iterencode(self, o: Any, _one_shot: bool = False) -> Any:
        return super().iterencode(self._sanitize(o), _one_shot=_one_shot)

    @staticmethod
    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: _SafeEncoder._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_SafeEncoder._sanitize(v) for v in obj]
        return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            cls=_SafeEncoder,
        ).encode("utf-8")


from .auth import AuthContext, require_admin
from .middleware import RequestLoggingMiddleware
from .config import get_settings
from .db import engine
from .errors import AppError
from .finance_client import make_finance_client
from .models import AdminUsageSummary, ErrorResponse
from .repository import PortfolioRepository
from .scheduler import PriceRefreshScheduler
from .services.csv_service import CsvImportService
from .services.historical_service import HistoricalIngestionService
from .services.pac_service import PacExecutionService
from .services.performance_service import PerformanceService
from .services.pricing_service import PriceIngestionService
from .justetf_client import JustEtfClient

# --- Route registrations ---
from .api.instant_portfolio_analyzer import register_instant_portfolio_analyzer_routes
from .api.portfolio_health import register_portfolio_health_routes
from .api.routes_portfolio import register_portfolio_routes
from .api.routes_assets import register_assets_routes
from .api.routes_transactions import register_transactions_routes
from .api.routes_pricing import register_pricing_routes
from .api.routes_analytics import register_analytics_routes
from .api.routes_rebalancing import register_rebalancing_routes
from .api.routes_markets import register_markets_routes
from .api.routes_cash import register_cash_routes
from .api.routes_csv import register_csv_routes
from .api.routes_pac import register_pac_routes
from .api.routes_copilot import register_copilot_routes

# ---------------------------------------------------------------------------
# Service initialization
# ---------------------------------------------------------------------------

settings = get_settings()
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

repo = PortfolioRepository(engine)
pricing_service = PriceIngestionService(settings, repo)
historical_service = HistoricalIngestionService(settings, repo)
csv_import_service = CsvImportService(repo)
pac_service = PacExecutionService(engine)
performance_service = PerformanceService(repo)
scheduler = PriceRefreshScheduler(settings, pricing_service, pac_service, historical_service, repo)
finance_client = make_finance_client(settings)
justetf_client = JustEtfClient(settings=settings)


# ---------------------------------------------------------------------------
# Feature flag helper
# ---------------------------------------------------------------------------

def ensure_target_allocation_enabled() -> None:
    """Feature-flag guard for code paths exclusively tied to Target Allocation."""
    if not settings.enable_target_allocation:
        raise AppError(
            code="feature_disabled",
            message="Feature Target Allocation disabilitata",
            status_code=404,
        )


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

def _apply_pending_migrations():
    """Apply new SQL migrations that haven't been applied yet (idempotent)."""
    from .db import engine as _engine
    try:
        with _engine.begin() as conn:
            from .sql import load_sql
            conn.execute(text(load_sql("migrations/create_asset_metadata")))
            conn.execute(text(load_sql("migrations/create_etf_enrichment")))
            conn.execute(text(load_sql("migrations/add_fire_expected_return_pct")))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_etf_enrichment_isin ON etf_enrichment(isin)
            """))
        logging.getLogger(__name__).info("asset_metadata, etf_enrichment and fire settings migrations ensured")
    except Exception as exc:
        logging.getLogger(__name__).warning("Migration check failed: %s", exc)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env != "dev" and not settings.clerk_auth_enabled:
        raise RuntimeError("Refusing to start with Clerk auth disabled outside dev")
    _apply_pending_migrations()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(title="Valore365 API", version="0.6.0", lifespan=lifespan, default_response_class=SafeJSONResponse)

# --- Middleware stack (added in reverse order: last added = first executed) ---

# CORS
if settings.app_env == "dev":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    _cors_kwargs: dict[str, Any] = dict(
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    if settings.cors_allowed_origin_regex:
        _cors_kwargs["allow_origin_regex"] = settings.cors_allowed_origin_regex
    app.add_middleware(CORSMiddleware, **_cors_kwargs)

# Request logging (runs after CORS)
app.add_middleware(RequestLoggingMiddleware)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": str(exc)}})


# ---------------------------------------------------------------------------
# Router + route registration
# ---------------------------------------------------------------------------

router = APIRouter()

# Core endpoints that stay in main
@router.get("/health")
def health() -> dict[str, Any]:
    """Liveness + readiness: pings DB to verify connectivity."""
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    status = "ok" if db_ok else "degraded"
    return {"status": status, "db": "ok" if db_ok else "unreachable"}


@router.get("/admin/usage-summary", response_model=AdminUsageSummary, responses={403: {"model": ErrorResponse}})
def get_admin_usage_summary(_auth: AuthContext = Depends(require_admin)) -> AdminUsageSummary:
    return repo.get_admin_usage_summary()


# Register all route modules
register_instant_portfolio_analyzer_routes(router, repo, csv_import_service=csv_import_service)
register_portfolio_health_routes(router, repo, finance_client, justetf_client=justetf_client)
register_portfolio_routes(router, repo, settings=settings)
register_assets_routes(
    router, repo,
    settings=settings,
    finance_client=finance_client,
    justetf_client=justetf_client,
    historical_service=historical_service,
    ensure_target_allocation_enabled=ensure_target_allocation_enabled,
)
register_transactions_routes(router, repo, historical_service=historical_service)
register_pricing_routes(
    router, repo,
    settings=settings,
    pricing_service=pricing_service,
    historical_service=historical_service,
    finance_client=finance_client,
    ensure_target_allocation_enabled=ensure_target_allocation_enabled,
)
register_analytics_routes(
    router, repo,
    performance_service=performance_service,
    finance_client=finance_client,
)
register_rebalancing_routes(
    router, repo,
    settings=settings,
    finance_client=finance_client,
    historical_service=historical_service,
    ensure_target_allocation_enabled=ensure_target_allocation_enabled,
)
register_markets_routes(router, repo, finance_client=finance_client)
register_cash_routes(router, repo)
register_csv_routes(router, repo, settings=settings, csv_import_service=csv_import_service)
register_pac_routes(router, repo, engine=engine)
register_copilot_routes(router, repo, settings=settings, performance_service=performance_service, finance_client=finance_client, justetf_client=justetf_client)

app.include_router(router, prefix="/api")
