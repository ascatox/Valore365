"""Vista aggregata: GET /portfolios/aggregate/... routes (TASK-26)."""

from datetime import date, datetime, timezone

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import routes_aggregate
from app.api.routes_aggregate import (
    MAX_AGGREGATE_PORTFOLIOS,
    aggregate_error,
    register_aggregate_routes,
)
from app.auth import AuthContext
from app.errors import AppError
from app.models import (
    AllocationItem,
    DrawdownResponse,
    GainTimeseriesPoint,
    HallOfFameResponse,
    IntradayTimeseriesPoint,
    MonthlyReturnsResponse,
    MWRResult,
    MWRTimeseriesPoint,
    PerformanceSummary,
    PeriodPerformer,
    PortfolioSummary,
    Position,
    RollingWindowsResponse,
    TimeSeriesPoint,
    TransactionListItem,
    TWRResult,
    TWRTimeseriesPoint,
    YearlyPerformanceResponse,
)
from app.rate_limit import require_auth_rate_limited
from app.repository import aggregate_identity, normalize_portfolio_ids
from app.repository._scope import EMPTY_SCOPE_MESSAGE, MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE
from app.schemas.portfolio_doctor import (
    MonteCarloProjectionResponse,
    PortfolioHealthCategoryScores,
    PortfolioHealthMetrics,
    PortfolioHealthResponse,
    PortfolioHealthSummary,
    StressTestResponse,
    XRayResponse,
)

USER = "u"
# id -> (owner, base currency)
PORTFOLIOS = {1: (USER, "EUR"), 2: (USER, "EUR"), 3: (USER, "USD"), 99: ("someone-else", "EUR")}


def _check_scope(ids, user_id=USER) -> list[int]:
    ids = normalize_portfolio_ids(ids)
    if not ids:
        raise ValueError(EMPTY_SCOPE_MESSAGE)
    if any(PORTFOLIOS.get(pid, (None,))[0] != user_id for pid in ids):
        raise ValueError(NOT_FOUND_MESSAGE)
    if len({PORTFOLIOS[pid][1] for pid in ids}) > 1:
        raise ValueError(MIXED_CURRENCY_MESSAGE)
    return ids


def _position(asset_id: int, value: float) -> Position:
    return Position(
        asset_id=asset_id, symbol=f"A{asset_id}", name=f"Asset {asset_id}", quantity=1, avg_cost=value,
        market_price=value, market_value=value, unrealized_pl=0, unrealized_pl_pct=0, weight=50,
    )


class _Repo:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def _record(self, name, ids, *extra):
        ids = _check_scope(ids)
        self.calls.append((name, ids, *extra))
        return ids

    def get_summary_multi(self, ids, user_id):
        ids = self._record("summary", ids)
        return PortfolioSummary(
            **aggregate_identity(ids), base_currency="EUR", market_value=300, cost_basis=250,
            unrealized_pl=50, unrealized_pl_pct=20,
        )

    def get_summary(self, portfolio_id, user_id):
        self.calls.append(("single_summary", portfolio_id))
        return PortfolioSummary(
            portfolio_id=portfolio_id, base_currency="EUR", market_value=100, cost_basis=100,
            unrealized_pl=0, unrealized_pl_pct=0,
        )

    def get_positions_multi(self, ids, user_id):
        self._record("positions", ids)
        return [_position(10, 200), _position(11, 100)]

    def get_allocation_multi(self, ids, user_id):
        self._record("allocation", ids)
        return [AllocationItem(asset_id=10, symbol="A10", market_value=200, weight_pct=100)]

    def get_period_performers_multi(self, ids, user_id, days):
        self._record("performers", ids, days)
        return [PeriodPerformer(asset_id=10, symbol="A10", name="Asset 10", return_pct=1.5)]

    def get_timeseries_multi(self, ids, range_value, interval, user_id):
        self._record("timeseries", ids, range_value, interval)
        return [TimeSeriesPoint(date="2026-10-30", market_value=300)]

    def get_intraday_timeseries_multi(self, ids, user_id, finance_client):
        self._record("intraday", ids, finance_client)
        return [IntradayTimeseriesPoint(ts="2026-10-30T10:00:00Z", market_value=300)]

    def list_transactions_multi(self, ids, user_id):
        ids = self._record("transactions", ids)
        return [
            TransactionListItem(
                id=7, portfolio_id=ids[-1], portfolio_name=f"Portafoglio {ids[-1]}", asset_id=10, side="buy",
                trade_at=datetime(2026, 10, 2, tzinfo=timezone.utc), quantity=1, price=10, fees=0, taxes=0,
                trade_currency="EUR",
            ),
            TransactionListItem(
                id=5, portfolio_id=ids[0], portfolio_name=f"Portafoglio {ids[0]}", asset_id=10, side="buy",
                trade_at=datetime(2026, 10, 1, tzinfo=timezone.utc), quantity=1, price=10, fees=0, taxes=0,
                trade_currency="EUR",
            ),
        ]

    def list_portfolios(self, user_id):
        from types import SimpleNamespace

        return [SimpleNamespace(id=1, name="Broker"), SimpleNamespace(id=2, name="Banca")]

    def get_price_coverage_multi(self, ids, user_id, days=365):
        self._record("coverage", ids, days)
        return [{
            "asset_id": 10, "symbol": "A10", "name": "Asset 10", "bar_count": 240, "first_bar": date(2025, 11, 1),
            "last_bar": date(2026, 10, 30), "expected_bars": 252, "coverage_pct": 95.2,
        }]


_TWR = TWRResult(twr_pct=5.0, twr_annualized_pct=5.0, period_days=365, start_date="2025-10-31", end_date="2026-10-31")
_MWR = MWRResult(mwr_pct=4.0, period_days=365, start_date="2025-10-31", end_date="2026-10-31", converged=True)


class _Performance:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def _record(self, name, ids, *extra):
        ids = _check_scope(ids)
        self.calls.append((name, ids, *extra))
        return ids

    def get_performance_summary(self, ids, user_id, period):
        self._record("summary", ids, period)
        return PerformanceSummary(
            period=period, period_label="1 anno", start_date="2025-10-31", end_date="2026-10-31", period_days=365,
            twr=_TWR, mwr=_MWR, total_deposits=100, total_withdrawals=0, net_invested=100, initial_value=0,
            current_value=110, absolute_gain=10,
        )

    def calculate_twr(self, ids, user_id, start_date=None, end_date=None):
        self._record("twr", ids, start_date, end_date)
        if start_date and end_date and start_date > end_date:
            raise ValueError("Intervallo date non valido")
        return _TWR

    def calculate_mwr(self, ids, user_id, start_date=None, end_date=None):
        self._record("mwr", ids, start_date, end_date)
        return _MWR

    def get_twr_timeseries(self, ids, user_id, start_date=None, end_date=None):
        self._record("twr_ts", ids)
        return [TWRTimeseriesPoint(date="2026-10-30", cumulative_twr_pct=5, portfolio_value=300)]

    def get_gain_timeseries(self, ids, user_id, start_date=None, end_date=None):
        self._record("gain_ts", ids)
        return [GainTimeseriesPoint(date="2026-10-30", portfolio_value=300, net_invested=250, absolute_gain=50)]

    def get_mwr_timeseries(self, ids, user_id, start_date=None, end_date=None):
        self._record("mwr_ts", ids)
        return [MWRTimeseriesPoint(date="2026-10-30", cumulative_mwr_pct=4)]

    def get_monthly_returns(self, ids, user_id, start_date, end_date):
        ids = self._record("monthly", ids)
        return MonthlyReturnsResponse(
            **aggregate_identity(ids), cells=[], yearly_returns=[], start_date="2025-10-31", end_date="2026-10-31",
        )

    def get_yearly_returns(self, ids, user_id):
        ids = self._record("yearly", ids)
        return YearlyPerformanceResponse(
            **aggregate_identity(ids), rows=[], start_date="2025-10-31", end_date="2026-10-31",
            cashflow_basis="investor",
        )

    def get_drawdown(self, ids, user_id, start_date, end_date):
        ids = self._record("drawdown", ids)
        return DrawdownResponse(**aggregate_identity(ids), points=[], max_drawdown_pct=0, current_drawdown_pct=0)

    def get_rolling_windows(self, ids, user_id, window_months, risk_free_rate, start_date, end_date):
        ids = self._record("rolling", ids, window_months, risk_free_rate)
        return RollingWindowsResponse(
            **aggregate_identity(ids), window_months=window_months, risk_free_rate_pct=risk_free_rate, points=[],
        )

    def get_hall_of_fame(self, ids, user_id, top_n, start_date, end_date):
        ids = self._record("hall", ids, top_n)
        return HallOfFameResponse(
            **aggregate_identity(ids), best_months=[], worst_months=[], best_years=[], worst_years=[],
        )


def _auth() -> AuthContext:
    return AuthContext(user_id=USER, org_id=None, email=None, claims={})


def _install_error_handler(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handler(_: Request, exc: AppError) -> JSONResponse:  # same body as app.main
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )


@pytest.fixture
def client_and_fakes():
    repo, performance = _Repo(), _Performance()
    finance_client = object()
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_aggregate_routes(
        router, repo, performance_service=performance, finance_client=finance_client, justetf_client=None,
    )
    app.include_router(router)
    app.dependency_overrides[require_auth_rate_limited] = _auth
    _install_error_handler(app)
    return TestClient(app), repo, performance, finance_client


Q = "portfolio_ids=1&portfolio_ids=2"


# --- Dashboard ---------------------------------------------------------------


def test_aggregate_summary_reports_portfolio_id_zero_and_the_selected_ids(client_and_fakes):
    client, repo, _, _ = client_and_fakes

    body = client.get(f"/api/portfolios/aggregate/summary?{Q}").json()

    assert body["portfolio_id"] == 0
    assert body["portfolio_ids"] == [1, 2]
    assert body["market_value"] == 300
    assert repo.calls == [("summary", [1, 2])]


def test_aggregate_ids_are_normalized_before_reaching_the_repository(client_and_fakes):
    client, repo, _, _ = client_and_fakes

    assert client.get("/api/portfolios/aggregate/positions?portfolio_ids=2&portfolio_ids=1&portfolio_ids=2").status_code == 200
    assert repo.calls == [("positions", [2, 1])]


def test_aggregate_dashboard_routes_forward_their_query_params(client_and_fakes):
    client, repo, _, finance_client = client_and_fakes

    assert len(client.get(f"/api/portfolios/aggregate/positions?{Q}").json()) == 2
    assert client.get(f"/api/portfolios/aggregate/allocation?{Q}").json()[0]["weight_pct"] == 100
    assert client.get(f"/api/portfolios/aggregate/performers?{Q}&days=30").json()[0]["return_pct"] == 1.5
    assert client.get(f"/api/portfolios/aggregate/timeseries?{Q}").json()[0]["market_value"] == 300
    assert client.get(f"/api/portfolios/aggregate/intraday-timeseries?{Q}").status_code == 200
    # Same validation as the single route.
    assert client.get(f"/api/portfolios/aggregate/timeseries?{Q}&range=5y").status_code == 422

    assert [c[0] for c in repo.calls] == ["positions", "allocation", "performers", "timeseries", "intraday"]
    assert repo.calls[2] == ("performers", [1, 2], 30)
    assert repo.calls[3] == ("timeseries", [1, 2], "1y", "1d")
    assert repo.calls[4] == ("intraday", [1, 2], finance_client)


def test_aggregate_transactions_name_the_portfolio_of_every_row(client_and_fakes):
    client, repo, _, _ = client_and_fakes

    rows = client.get(f"/api/portfolios/aggregate/transactions?{Q}").json()

    assert [(r["id"], r["portfolio_id"], r["portfolio_name"]) for r in rows] == [
        (7, 2, "Portafoglio 2"),
        (5, 1, "Portafoglio 1"),
    ]
    assert repo.calls == [("transactions", [1, 2])]


def test_aggregate_data_coverage(client_and_fakes):
    client, repo, _, _ = client_and_fakes

    body = client.get(f"/api/portfolios/aggregate/data-coverage?{Q}&days=200&threshold_pct=96").json()

    assert (body["portfolio_id"], body["portfolio_ids"]) == (0, [1, 2])
    assert body["days"] == 200
    assert body["sufficient"] is False
    assert body["assets"][0]["symbol"] == "A10"
    assert repo.calls == [("coverage", [1, 2], 200)]


def test_aggregate_data_coverage_honours_the_target_allocation_flag():
    def _disabled():
        raise AppError(code="feature_disabled", message="Feature Target Allocation disabilitata", status_code=404)

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_aggregate_routes(router, _Repo(), performance_service=_Performance(), ensure_target_allocation_enabled=_disabled)
    app.include_router(router)
    app.dependency_overrides[require_auth_rate_limited] = _auth
    _install_error_handler(app)

    response = TestClient(app).get(f"/api/portfolios/aggregate/data-coverage?{Q}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "feature_disabled"


def test_aggregate_markdown_export(client_and_fakes, monkeypatch):
    client, repo, performance, _ = client_and_fakes
    from app.services import portfolio_markdown_export as export

    monkeypatch.setattr(export, "analyze_portfolio_health", lambda *a: (_ for _ in ()).throw(ValueError("skip")))
    monkeypatch.setattr(export, "run_monte_carlo_projection", lambda *a: (_ for _ in ()).throw(ValueError("skip")))

    response = client.get(f"/api/portfolios/aggregate/export/markdown?{Q}")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="valore365-aggregato-{date.today().isoformat()}.md"'
    )
    assert "Vista aggregata: Broker, Banca" in response.text
    assert "## Non inclusi nella vista aggregata" in response.text
    assert repo.calls[:2] == [("summary", [1, 2]), ("positions", [1, 2])]
    assert [c for c in performance.calls if c[0] == "summary"][0][1] == [1, 2]


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        ("", 400, "invalid_request"),
        ("portfolio_ids=1&portfolio_ids=3", 400, "invalid_request"),
        ("portfolio_ids=1&portfolio_ids=99", 404, "not_found"),
    ],
)
def test_aggregate_markdown_export_scope_errors(client_and_fakes, query, status, code):
    client, _, _, _ = client_and_fakes

    response = client.get(f"/api/portfolios/aggregate/export/markdown?{query}")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


# --- Performance -------------------------------------------------------------


def test_aggregate_performance_routes(client_and_fakes):
    client, _, performance, _ = client_and_fakes
    base = "/api/portfolios/aggregate/performance"

    assert client.get(f"{base}/summary?{Q}&period=3y").json()["period"] == "3y"
    assert client.get(f"{base}/twr?{Q}&start_date=2026-01-01&end_date=2026-06-30").json()["twr_pct"] == 5.0
    assert client.get(f"{base}/mwr?{Q}").json()["converged"] is True
    assert client.get(f"{base}/twr/timeseries?{Q}").status_code == 200
    assert client.get(f"{base}/mwr/timeseries?{Q}").status_code == 200
    assert client.get(f"{base}/gain/timeseries?{Q}").status_code == 200
    for path in ("monthly-returns", "yearly", "drawdown", "rolling-windows?window_months=24", "hall-of-fame?top_n=3"):
        sep = "&" if "?" in path else "?"
        body = client.get(f"{base}/{path}{sep}{Q}").json()
        assert (body["portfolio_id"], body["portfolio_ids"]) == (0, [1, 2]), path

    assert [c[0] for c in performance.calls] == [
        "summary", "twr", "mwr", "twr_ts", "mwr_ts", "gain_ts", "monthly", "yearly", "drawdown", "rolling", "hall",
    ]
    assert performance.calls[0] == ("summary", [1, 2], "3y")
    assert performance.calls[1] == ("twr", [1, 2], date(2026, 1, 1), date(2026, 6, 30))
    assert performance.calls[9] == ("rolling", [1, 2], 24, 2.0)
    assert performance.calls[10] == ("hall", [1, 2], 3)
    # Same query validation as the single routes.
    assert client.get(f"{base}/summary?{Q}&period=10y").status_code == 422


def test_aggregate_performance_other_errors_keep_the_single_route_status(client_and_fakes):
    client, _, _, _ = client_and_fakes

    response = client.get(f"/api/portfolios/aggregate/performance/twr?{Q}&start_date=2026-06-30&end_date=2026-01-01")

    assert response.status_code == 400
    assert response.json()["error"] == {"code": "bad_request", "message": "Intervallo date non valido", "details": None}


# --- Portfolio Doctor ----------------------------------------------------------


def _metrics() -> PortfolioHealthMetrics:
    return PortfolioHealthMetrics(
        geographic_exposure={}, max_position_weight=0, overlap_score=0, portfolio_volatility=None, weighted_ter=None,
    )


def test_aggregate_doctor_routes_pass_the_id_list_to_the_services(client_and_fakes, monkeypatch):
    client, _, _, finance_client = client_and_fakes
    calls = []

    def _health(repo, ids, user_id):
        calls.append(("health", list(_check_scope(ids))))
        return PortfolioHealthResponse(
            **aggregate_identity(ids), score=0,
            summary=PortfolioHealthSummary(
                risk_level="unknown", diversification="unknown", overlap="unknown", cost_efficiency="unknown",
            ),
            metrics=_metrics(),
            category_scores=PortfolioHealthCategoryScores(diversification=0, risk=0, concentration=0, overlap=0, cost_efficiency=0),
        )

    def _monte_carlo(repo, ids, user_id):
        calls.append(("monte-carlo", list(ids)))
        return MonteCarloProjectionResponse(
            **aggregate_identity(ids), num_simulations=0, horizons=[5], projections=[],
            annualized_mean_return_pct=0, annualized_volatility_pct=0,
        )

    def _stress(repo, ids, user_id):
        calls.append(("stress-test", list(ids)))
        return StressTestResponse(**aggregate_identity(ids), analysis_date="2026-10-31")

    def _xray(repo, ids, user_id, fc, justetf_client=None):
        calls.append(("xray", list(ids), fc))
        return XRayResponse(**aggregate_identity(ids), etf_count=0, coverage_pct=0)

    monkeypatch.setattr(routes_aggregate, "analyze_portfolio_health", _health)
    monkeypatch.setattr(routes_aggregate, "run_monte_carlo_projection", _monte_carlo)
    monkeypatch.setattr(routes_aggregate, "run_stress_test", _stress)
    monkeypatch.setattr(routes_aggregate, "compute_portfolio_xray", _xray)

    for resource in ("health", "monte-carlo", "stress-test", "xray"):
        response = client.get(f"/api/portfolios/aggregate/{resource}?{Q}")
        assert response.status_code == 200, (resource, response.text)
        assert (response.json()["portfolio_id"], response.json()["portfolio_ids"]) == (0, [1, 2])

    assert calls == [
        ("health", [1, 2]), ("monte-carlo", [1, 2]), ("stress-test", [1, 2]), ("xray", [1, 2], finance_client),
    ]

    # A doctor scope error maps like every other aggregate route.
    response = client.get("/api/portfolios/aggregate/health?portfolio_ids=1&portfolio_ids=3")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_aggregate_decumulation_still_validates_its_params(client_and_fakes, monkeypatch):
    client, _, _, _ = client_and_fakes
    monkeypatch.setattr(routes_aggregate, "run_aggregate_decumulation_plan", lambda *a, **k: pytest.fail("not called"))

    response = client.get(
        f"/api/portfolios/aggregate/decumulation?{Q}&annual_withdrawal=1000&years=10&one_off_ages=70"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


# --- Errors --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "status", "code", "message"),
    [
        ("", 400, "invalid_request", EMPTY_SCOPE_MESSAGE),
        ("portfolio_ids=0", 400, "invalid_request", EMPTY_SCOPE_MESSAGE),
        ("portfolio_ids=1&portfolio_ids=3", 400, "invalid_request", MIXED_CURRENCY_MESSAGE),
        ("portfolio_ids=1&portfolio_ids=99", 404, "not_found", NOT_FOUND_MESSAGE),
        ("portfolio_ids=1&portfolio_ids=12345", 404, "not_found", NOT_FOUND_MESSAGE),
    ],
)
@pytest.mark.parametrize("resource", ["summary", "transactions", "performance/drawdown", "data-coverage"])
def test_aggregate_scope_errors(client_and_fakes, resource, query, status, code, message):
    client, _, _, _ = client_and_fakes

    response = client.get(f"/api/portfolios/aggregate/{resource}?{query}")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"] == message


def test_aggregate_rejects_too_many_portfolios(client_and_fakes):
    client, repo, _, _ = client_and_fakes
    query = "&".join(f"portfolio_ids={i}" for i in range(1, MAX_AGGREGATE_PORTFOLIOS + 2))

    response = client.get(f"/api/portfolios/aggregate/summary?{query}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert repo.calls == []


def test_aggregate_error_mapping():
    assert (aggregate_error(ValueError(EMPTY_SCOPE_MESSAGE)).status_code, aggregate_error(ValueError(EMPTY_SCOPE_MESSAGE)).code) == (400, "invalid_request")
    assert aggregate_error(ValueError(MIXED_CURRENCY_MESSAGE)).status_code == 400
    not_found = aggregate_error(ValueError(NOT_FOUND_MESSAGE), default_status=400)
    assert (not_found.status_code, not_found.code) == (404, "not_found")
    other = aggregate_error(ValueError("Intervallo date non valido"), default_status=400)
    assert (other.status_code, other.code) == (400, "bad_request")
    assert aggregate_error(ValueError("Portafoglio non trovato o vuoto")).status_code == 404


# --- Route precedence in the real application ---------------------------------


def test_every_aggregate_route_is_registered_before_the_portfolio_id_routes():
    import app.main as main

    paths = [getattr(route, "path", "") for route in main.app.routes]
    aggregate = [p for p in paths if p.startswith("/api/portfolios/aggregate/")]
    by_id = [i for i, p in enumerate(paths) if p.startswith("/api/portfolios/{portfolio_id}")]

    expected = {
        "summary", "positions", "allocation", "timeseries", "intraday-timeseries", "performers", "transactions",
        "data-coverage", "export/markdown", "health", "monte-carlo", "stress-test", "xray", "decumulation",
        "performance/summary", "performance/twr", "performance/twr/timeseries", "performance/mwr",
        "performance/mwr/timeseries", "performance/gain/timeseries", "performance/monthly-returns",
        "performance/yearly", "performance/drawdown", "performance/rolling-windows", "performance/hall-of-fame",
    }
    assert {p.removeprefix("/api/portfolios/aggregate/") for p in aggregate} == expected
    assert max(paths.index(p) for p in aggregate) < min(by_id)


def test_real_app_routes_aggregate_and_single_requests(monkeypatch):
    import app.main as main

    repo = _Repo()
    monkeypatch.setattr(main, "repo", repo)
    main.app.dependency_overrides[require_auth_rate_limited] = _auth
    try:
        client = TestClient(main.app)
        aggregate = client.get(f"/api/portfolios/aggregate/summary?{Q}")
        single = client.get("/api/portfolios/1/summary")
        not_owned = client.get("/api/portfolios/aggregate/summary?portfolio_ids=99")
    finally:
        main.app.dependency_overrides.pop(require_auth_rate_limited, None)

    assert aggregate.status_code == 200, aggregate.text
    assert (aggregate.json()["portfolio_id"], aggregate.json()["portfolio_ids"]) == (0, [1, 2])
    # The single-portfolio route is untouched: same id, no portfolio_ids.
    assert single.status_code == 200
    assert (single.json()["portfolio_id"], single.json()["portfolio_ids"]) == (1, None)
    assert not_owned.status_code == 404
    assert repo.calls == [("summary", [1, 2]), ("single_summary", 1)]
