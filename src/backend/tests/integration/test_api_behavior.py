from fastapi.testclient import TestClient

import app.main as api_main


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
