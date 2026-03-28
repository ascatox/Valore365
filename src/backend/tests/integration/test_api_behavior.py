from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.api.portfolio_health as portfolio_health_api
import app.api.instant_portfolio_analyzer as instant_portfolio_api
import app.main as api_main
from app.errors import AppError
from app.schemas.portfolio_doctor import (
    PortfolioHealthAlert,
    PortfolioHealthCategoryScores,
    PortfolioHealthEducation,
    PortfolioHealthMetrics,
    PortfolioHealthResponse,
    PortfolioHealthSummary,
)
from app.schemas.instant_portfolio_analyzer import (
    InstantAnalyzeCta,
    InstantAnalyzeLineError,
    InstantAnalyzeResponse,
    InstantAnalyzeUnresolvedItem,
    PortfolioAnalyzeAlert,
    PortfolioAnalyzeMetrics,
    PortfolioAnalyzeSuggestion,
    PortfolioAnalyzeSummary,
    ResolvedPosition,
)
from app.models import AdminUsageSummary


class _FakeRepo:
    def list_portfolios(self, user_id: str):
        return [
            {
                'id': 2,
                'name': 'Portfolio B',
                'base_currency': 'EUR',
                'timezone': 'Europe/Rome',
                'created_at': '2026-02-23T10:01:00Z',
            },
            {
                'id': 1,
                'name': 'Portfolio A',
                'base_currency': 'USD',
                'timezone': 'America/New_York',
                'created_at': '2026-02-23T10:00:00Z',
            },
        ]

    def create_portfolio(self, payload, user_id: str):
        return {
            'id': 123,
            'name': payload.name.strip(),
            'base_currency': payload.base_currency.strip().upper(),
            'timezone': payload.timezone.strip(),
            'created_at': '2026-02-23T10:00:00Z',
        }

    def get_summary(self, portfolio_id: int, user_id: str):
        raise ValueError('Portfolio non trovato')

    def get_idempotency_response(self, *, idempotency_key: str, endpoint: str, user_id: str | None = None):
        return {
            'provider': 'yfinance',
            'requested_assets': 1,
            'refreshed_assets': 1,
            'failed_assets': 0,
            'items': [
                {
                    'asset_id': 1,
                    'symbol': 'AAPL',
                    'provider_symbol': 'AAPL',
                    'price': 100.0,
                    'ts': '2026-02-17T00:00:00Z',
                }
            ],
            'errors': [],
        }

    def list_transactions(self, portfolio_id: int, user_id: str):
        return [
            {
                'id': 10,
                'portfolio_id': portfolio_id,
                'asset_id': 1,
                'side': 'buy',
                'trade_at': '2026-02-24T10:00:00Z',
                'quantity': 2.0,
                'price': 100.0,
                'fees': 1.0,
                'taxes': 0.0,
                'trade_currency': 'EUR',
                'notes': 'test',
                'symbol': 'AAPL',
                'asset_name': 'Apple Inc.',
            }
        ]

    def update_transaction(self, transaction_id: int, payload, user_id: str):
        if transaction_id == 404:
            raise ValueError('Transazione non trovata')
        if payload.quantity == 999:
            raise ValueError('Quantita insufficiente per sell')
        return {
            'id': transaction_id,
            'portfolio_id': 1,
            'asset_id': 1,
            'side': 'buy',
            'trade_at': payload.trade_at or '2026-02-24T10:00:00Z',
            'quantity': payload.quantity if payload.quantity is not None else 1.0,
            'price': payload.price if payload.price is not None else 100.0,
            'fees': payload.fees if payload.fees is not None else 0.0,
            'taxes': payload.taxes if payload.taxes is not None else 0.0,
            'trade_currency': 'EUR',
            'notes': payload.notes,
        }

    def delete_transaction(self, transaction_id: int, user_id: str):
        if transaction_id == 404:
            raise ValueError('Transazione non trovata')
        return None

    def get_admin_usage_summary(self):
        return AdminUsageSummary(
            registered_users=5,
            users_with_portfolios=4,
            users_with_transactions=3,
            users_with_imports=2,
            portfolios_total=7,
            transactions_total=42,
            csv_import_batches_total=6,
            portfolios_created_7d=3,
            imports_started_7d=2,
            analyzer_runs_total=11,
            analyzer_runs_7d=5,
            analyzer_unique_visitors_7d=4,
            public_instant_analyzer_tracked=True,
        )


class _FailPricingService:
    def refresh_prices(self, portfolio_id=None, asset_scope='target', user_id=None):
        raise AssertionError('non dovrebbe essere chiamato quando c\'e cache idempotente')


class _FakePerformanceService:
    def get_performance_summary(self, portfolio_id: int, user_id: str, period: str):
        return {
            'period': period,
            'period_label': '1 anno',
            'start_date': '2025-01-01',
            'end_date': '2026-01-01',
            'period_days': 365,
            'twr': {
                'twr_pct': 12.34,
                'twr_annualized_pct': 12.34,
                'period_days': 365,
                'start_date': '2025-01-01',
                'end_date': '2026-01-01',
            },
            'mwr': {
                'mwr_pct': 10.01,
                'period_days': 365,
                'start_date': '2025-01-01',
                'end_date': '2026-01-01',
                'converged': True,
            },
            'total_deposits': 10000,
            'total_withdrawals': 2000,
            'net_invested': 8000,
            'current_value': 9000,
            'absolute_gain': 1000,
        }


def test_error_model_uniform(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)
    response = client.get('/api/portfolios/1/summary')

    assert response.status_code == 404
    payload = response.json()
    assert payload['error']['code'] == 'not_found'


def test_create_portfolio_route(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.post(
        '/api/portfolios',
        json={'name': ' Nuovo Portfolio ', 'base_currency': 'EUR', 'timezone': 'Europe/Rome'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['id'] == 123
    assert payload['name'] == 'Nuovo Portfolio'
    assert payload['base_currency'] == 'EUR'
    assert payload['timezone'] == 'Europe/Rome'


def test_list_portfolios_route(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.get('/api/portfolios')

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]['id'] == 2
    assert payload[0]['name'] == 'Portfolio B'


def test_admin_usage_summary_route(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    monkeypatch.setattr(api_main.settings, 'admin_user_ids', 'dev-user')
    client = TestClient(api_main.app)

    response = client.get('/api/admin/usage-summary')

    assert response.status_code == 200
    payload = response.json()
    assert payload['registered_users'] == 5
    assert payload['users_with_imports'] == 2
    assert payload['analyzer_runs_total'] == 11
    assert payload['public_instant_analyzer_tracked'] is True


def test_admin_usage_summary_route_forbidden_without_admin_access(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    monkeypatch.setattr(api_main.settings, 'admin_user_ids', '')
    monkeypatch.setattr(api_main.settings, 'admin_emails', '')
    client = TestClient(api_main.app)

    response = client.get('/api/admin/usage-summary')

    assert response.status_code == 403
    payload = response.json()
    assert payload['error']['code'] == 'forbidden'


def test_idempotency_refresh_returns_cached(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    monkeypatch.setattr(api_main, 'pricing_service', _FailPricingService())
    client = TestClient(api_main.app)

    response = client.post('/api/prices/refresh', headers={'Idempotency-Key': 'abc-123'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['requested_assets'] == 1
    assert payload['refreshed_assets'] == 1


def test_list_transactions_route(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.get('/api/portfolios/1/transactions')

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]['id'] == 10
    assert payload[0]['symbol'] == 'AAPL'


def test_patch_transaction_route_not_found(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.patch('/api/transactions/404', json={'price': 123.45})

    assert response.status_code == 404
    payload = response.json()
    assert payload['error']['code'] == 'not_found'


def test_patch_transaction_route_bad_request(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.patch('/api/transactions/1', json={'quantity': 999})

    assert response.status_code == 400
    payload = response.json()
    assert payload['error']['code'] == 'bad_request'


def test_public_instant_portfolio_analyzer_route_bad_request_includes_details(monkeypatch):
    instant_portfolio_api.reset_public_instant_analyzer_rate_limiter()
    from app.services.instant_portfolio_analyzer import InstantPortfolioAnalysisError

    def _fake_analyze(repo, payload):
        raise InstantPortfolioAnalysisError(
            'No valid positions found',
            parse_errors=[
                InstantAnalyzeLineError(
                    line=1,
                    raw='BAD',
                    error='Expected format: IDENTIFIER VALUE',
                )
            ],
            unresolved=[
                InstantAnalyzeUnresolvedItem(
                    identifier='UNKNOWN',
                    raw='UNKNOWN 1000',
                    line=2,
                    error='Asset not found in the supported catalog',
                )
            ],
        )

    monkeypatch.setattr(instant_portfolio_api, 'analyze_public_portfolio', _fake_analyze)
    client = TestClient(api_main.app)

    response = client.post('/api/public/portfolio/analyze', json={'input_mode': 'raw_text', 'raw_text': 'BAD\nUNKNOWN 1000'})

    assert response.status_code == 400
    payload = response.json()
    assert payload['error']['code'] == 'bad_request'
    assert payload['error']['message'] == 'No valid positions found'
    assert payload['error']['details']['parse_errors'][0]['line'] == 1
    assert payload['error']['details']['unresolved'][0]['identifier'] == 'UNKNOWN'


def test_delete_transaction_route_not_found(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.delete('/api/transactions/404')

    assert response.status_code == 404
    payload = response.json()
    assert payload['error']['code'] == 'not_found'


def test_delete_transaction_route_ok(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.delete('/api/transactions/1')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_performance_summary_route(monkeypatch):
    monkeypatch.setattr(api_main, 'performance_service', _FakePerformanceService())
    client = TestClient(api_main.app)

    response = client.get('/api/portfolios/1/performance/summary?period=1y')

    assert response.status_code == 200
    payload = response.json()
    assert payload['period'] == '1y'
    assert payload['twr']['twr_pct'] == 12.34
    assert payload['mwr']['converged'] is True


def test_portfolio_health_route(monkeypatch):
    def _fake_analyze(repo, portfolio_id: int, user_id: str):
        assert user_id == 'dev-user'
        return PortfolioHealthResponse(
            portfolio_id=portfolio_id,
            score=74,
            summary=PortfolioHealthSummary(
                risk_level='medium',
                diversification='good',
                overlap='moderate',
                cost_efficiency='low_cost',
            ),
            metrics=PortfolioHealthMetrics(
                geographic_exposure={'usa': 67.2, 'europe': 14.5, 'emerging': 6.3, 'other': 12.0},
                max_position_weight=45.1,
                overlap_score=58.0,
                portfolio_volatility=16.2,
                weighted_ter=0.24,
            ),
            category_scores=PortfolioHealthCategoryScores(
                diversification=19,
                risk=16,
                concentration=14,
                overlap=11,
                cost_efficiency=14,
            ),
            alerts=[
                PortfolioHealthAlert(
                    severity='warning',
                    type='geographic_concentration',
                    message='Il portafoglio e fortemente esposto al mercato statunitense (67.2%).',
                    education=PortfolioHealthEducation(
                        code='geographic_concentration',
                        title='Esposizione geografica concentrata',
                        what_it_means='Una parte molto ampia del portafoglio dipende dalla stessa area geografica.',
                        why_it_matters='Quando un solo mercato pesa troppo, il portafoglio reagisce in modo meno bilanciato.',
                        how_to_read_it='Nel tuo caso gli USA pesano circa 67.2% del portafoglio.',
                        concept='Diversificazione geografica',
                        copilot_prompts=['Spiegamelo semplice'],
                    ),
                )
            ],
            suggestions=[],
        )

    monkeypatch.setattr(portfolio_health_api, 'analyze_portfolio_health', _fake_analyze)
    client = TestClient(api_main.app)

    response = client.get('/api/portfolios/7/health')

    assert response.status_code == 200
    payload = response.json()
    assert payload['portfolio_id'] == 7
    assert payload['score'] == 74
    assert payload['summary']['diversification'] == 'good'
    assert payload['alerts'][0]['education']['code'] == 'geographic_concentration'


def test_portfolio_health_route_not_found(monkeypatch):
    def _fake_analyze(repo, portfolio_id: int, user_id: str):
        raise ValueError('Portfolio non trovato')

    monkeypatch.setattr(portfolio_health_api, 'analyze_portfolio_health', _fake_analyze)
    client = TestClient(api_main.app)

    response = client.get('/api/portfolios/999/health')

    assert response.status_code == 404
    payload = response.json()
    assert payload['error']['code'] == 'not_found'


def test_public_instant_portfolio_analyzer_route(monkeypatch):
    instant_portfolio_api.reset_public_instant_analyzer_rate_limiter()

    def _fake_analyze(repo, payload):
        assert payload.input_mode == 'raw_text'
        return InstantAnalyzeResponse(
            summary=PortfolioAnalyzeSummary(
                total_value=17000,
                score=74,
                risk_level='medium',
                diversification='good',
                overlap='moderate',
                cost_efficiency='low_cost',
            ),
            positions=[
                ResolvedPosition(
                    identifier='VWCE',
                    resolved_symbol='VWCE',
                    resolved_name='Vanguard FTSE All-World UCITS ETF',
                    value=10000,
                    weight=58.82,
                )
            ],
            unresolved=[],
            parse_errors=[],
            metrics=PortfolioAnalyzeMetrics(
                geographic_exposure={'usa': 68.0, 'europe': 17.0, 'emerging': 10.0, 'other': 5.0},
                max_position_weight=58.82,
                overlap_score=61.0,
                portfolio_volatility=14.8,
                weighted_ter=0.21,
            ),
            category_scores=PortfolioHealthCategoryScores(
                diversification=18,
                risk=18,
                concentration=8,
                overlap=10,
                cost_efficiency=12,
            ),
            alerts=[
                PortfolioAnalyzeAlert(
                    severity='warning',
                    code='HIGH_US_EXPOSURE',
                    message='Your portfolio is heavily exposed to US markets (68%).',
                )
            ],
            suggestions=[
                PortfolioAnalyzeSuggestion(
                    code='ADD_DIVERSIFICATION',
                    message='Consider increasing exposure to non-US markets.',
                )
            ],
            cta=InstantAnalyzeCta(
                show_signup=True,
                message='Crea un account gratuito per salvare e monitorare questo portafoglio nel tempo.',
            ),
        )

    monkeypatch.setattr(instant_portfolio_api, 'analyze_public_portfolio', _fake_analyze)
    client = TestClient(api_main.app)

    response = client.post('/api/public/portfolio/analyze', json={'input_mode': 'raw_text', 'raw_text': 'VWCE 10000'})

    assert response.status_code == 200
    payload = response.json()
    assert payload['summary']['score'] == 74
    assert payload['category_scores']['diversification'] == 18
    assert payload['cta']['show_signup'] is True
    assert payload['positions'][0]['resolved_symbol'] == 'VWCE'


def test_public_instant_portfolio_analyzer_route_bad_request(monkeypatch):
    instant_portfolio_api.reset_public_instant_analyzer_rate_limiter()

    def _fake_analyze(repo, payload):
        raise ValueError('No valid positions found')

    monkeypatch.setattr(instant_portfolio_api, 'analyze_public_portfolio', _fake_analyze)
    client = TestClient(api_main.app)

    response = client.post('/api/public/portfolio/analyze', json={'input_mode': 'raw_text', 'raw_text': ''})

    assert response.status_code == 400
    payload = response.json()
    assert payload['error']['code'] == 'bad_request'


def test_public_instant_portfolio_analyzer_real_route_returns_structured_details():
    instant_portfolio_api.reset_public_instant_analyzer_rate_limiter()

    router = APIRouter()
    instant_portfolio_api.register_instant_portfolio_analyzer_routes(router, _FakeRepo())
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(_: object, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    app.include_router(router, prefix='/api')
    client = TestClient(app)

    response = client.post('/api/public/portfolio/analyze', json={'input_mode': 'raw_text', 'raw_text': 'BAD\nUNKNOWN 1000'})

    assert response.status_code == 400
    payload = response.json()
    assert payload['error']['code'] == 'bad_request'
    assert payload['error']['message'] == 'No valid positions found'
    assert payload['error']['details']['parse_errors'][0]['line'] == 1
    assert payload['error']['details']['unresolved'][0]['identifier'] == 'UNKNOWN'


def test_public_instant_portfolio_analyzer_real_route_rejects_too_many_positions(monkeypatch):
    instant_portfolio_api.reset_public_instant_analyzer_rate_limiter()
    monkeypatch.setattr(instant_portfolio_api.get_settings(), 'public_instant_analyzer_max_positions', 50)

    router = APIRouter()
    instant_portfolio_api.register_instant_portfolio_analyzer_routes(router, _FakeRepo())
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(_: object, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    app.include_router(router, prefix='/api')
    client = TestClient(app)

    raw_text = "\n".join(f"VWCE {index}" for index in range(1, 53))
    response = client.post('/api/public/portfolio/analyze', json={'input_mode': 'raw_text', 'raw_text': raw_text})

    assert response.status_code == 400
    payload = response.json()
    assert payload['error']['code'] == 'bad_request'
    assert 'Too many positions submitted' in payload['error']['message']


def test_public_instant_portfolio_analyzer_real_route_rate_limits_requests(monkeypatch):
    monkeypatch.setattr(
        instant_portfolio_api,
        '_public_instant_rate_limiter',
        instant_portfolio_api.SlidingWindowRateLimiter(max_requests=1, window_seconds=60),
    )
    instant_portfolio_api.reset_public_instant_analyzer_rate_limiter()

    router = APIRouter()
    instant_portfolio_api.register_instant_portfolio_analyzer_routes(router, _FakeRepo())
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(_: object, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    app.include_router(router, prefix='/api')
    client = TestClient(app)

    first = client.post('/api/public/portfolio/analyze', json={'input_mode': 'raw_text', 'raw_text': 'VWCE 10000'})
    second = client.post('/api/public/portfolio/analyze', json={'input_mode': 'raw_text', 'raw_text': 'VWCE 10000'})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()['error']['code'] == 'rate_limited'


def test_public_instant_portfolio_analyzer_does_not_trust_untrusted_forwarded_for(monkeypatch):
    monkeypatch.setattr(
        instant_portfolio_api,
        '_public_instant_rate_limiter',
        instant_portfolio_api.SlidingWindowRateLimiter(max_requests=1, window_seconds=60),
    )
    instant_portfolio_api.reset_public_instant_analyzer_rate_limiter()
    monkeypatch.setattr(instant_portfolio_api.get_settings(), 'trusted_proxy_ips', '')

    router = APIRouter()
    instant_portfolio_api.register_instant_portfolio_analyzer_routes(router, _FakeRepo())
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(_: object, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}})

    app.include_router(router, prefix='/api')
    client = TestClient(app)

    first = client.post(
        '/api/public/portfolio/analyze',
        json={'input_mode': 'raw_text', 'raw_text': 'VWCE 10000'},
        headers={'x-forwarded-for': '1.1.1.1'},
    )
    second = client.post(
        '/api/public/portfolio/analyze',
        json={'input_mode': 'raw_text', 'raw_text': 'VWCE 10000'},
        headers={'x-forwarded-for': '2.2.2.2'},
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()['error']['code'] == 'rate_limited'


def test_csv_import_preview_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(api_main.settings, 'csv_import_max_upload_bytes', 8)
    client = TestClient(api_main.app)

    response = client.post(
        '/api/portfolios/1/csv-import/preview',
        files={'file': ('import.csv', b'123456789', 'text/csv')},
        data={'broker': 'generic'},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload['error']['code'] == 'bad_request'
    assert 'File troppo grande' in payload['error']['message']


def test_csv_import_preview_rejects_unsupported_extension():
    client = TestClient(api_main.app)

    response = client.post(
        '/api/portfolios/1/csv-import/preview',
        files={'file': ('import.txt', b'test', 'text/plain')},
        data={'broker': 'generic'},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload['error']['code'] == 'bad_request'
    assert 'Formato file non supportato' in payload['error']['message']


def test_app_refuses_to_start_without_auth_outside_dev(monkeypatch):
    monkeypatch.setattr(api_main.settings, 'app_env', 'prod')
    monkeypatch.setattr(api_main.settings, 'clerk_auth_enabled', False)

    try:
        with TestClient(api_main.app):
            raise AssertionError('TestClient should not start successfully')
    except RuntimeError as exc:
        assert 'Clerk auth disabled' in str(exc)


def test_csv_import_template_route(monkeypatch):
    monkeypatch.setattr(
        api_main.csv_import_service,
        'build_template_xlsx',
        lambda broker='generic': (b'fake-xlsx', 'valore365-generic-import-template.xlsx'),
    )
    client = TestClient(api_main.app)

    response = client.get('/api/csv-import/template?broker=generic')

    assert response.status_code == 200
    assert response.headers['content-type'].startswith(
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    assert 'valore365-generic-import-template.xlsx' in response.headers['content-disposition']
