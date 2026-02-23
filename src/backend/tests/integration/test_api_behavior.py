from fastapi.testclient import TestClient

import app.main as api_main


class _FakeRepo:
    def list_portfolios(self):
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

    def create_portfolio(self, payload):
        return {
            'id': 123,
            'name': payload.name.strip(),
            'base_currency': payload.base_currency.strip().upper(),
            'timezone': payload.timezone.strip(),
            'created_at': '2026-02-23T10:00:00Z',
        }

    def get_summary(self, portfolio_id: int):
        raise ValueError('Portfolio non trovato')

    def get_idempotency_response(self, *, idempotency_key: str, endpoint: str):
        return {
            'provider': 'twelvedata',
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


class _FailPricingService:
    def refresh_prices(self, portfolio_id=None):
        raise AssertionError('non dovrebbe essere chiamato quando c\'e cache idempotente')


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


def test_admin_list_portfolios_route(monkeypatch):
    monkeypatch.setattr(api_main, 'repo', _FakeRepo())
    client = TestClient(api_main.app)

    response = client.get('/api/admin/portfolios')

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
