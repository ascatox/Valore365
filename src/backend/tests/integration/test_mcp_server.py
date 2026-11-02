import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from starlette.routing import Route

import app.auth as app_auth
import app.main as api_main
import app.mcp_server.auth as mcp_auth
from app.copilot_tools import TOOL_DEFINITIONS
from app.mcp_server.config import resolve_mcp_config
from app.mcp_server.tools import MAX_TEXT_FIELD_CHARS, sanitize_output
from app.rate_limit import SlidingWindowRateLimiter

ISSUER = 'https://clerk.example.test'
RESOURCE = 'https://testserver/mcp'
PRM_URL = 'https://testserver/.well-known/oauth-protected-resource/mcp'
OWNER = 'user_owner'
KID = 'ins_test'

MCP_HEADERS = {
    'Accept': 'application/json, text/event-stream',
    'Content-Type': 'application/json',
    'MCP-Protocol-Version': '2025-06-18',
}

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_jwk(private_key, kid: str) -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({'kid': kid, 'alg': 'RS256', 'use': 'sig'})
    return jwk


def _make_token(*, typ='at+jwt', key=None, kid=KID, **claim_overrides) -> str:
    now = int(time.time())
    claims = {
        'iss': ISSUER,
        'sub': OWNER,
        'client_id': 'client_abc',
        'scp': ['profile', 'email'],
        'iat': now,
        'exp': now + 300,
        'jti': 'oat_jti',
    }
    claims.update(claim_overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key or _PRIVATE_KEY, algorithm='RS256', headers={'kid': kid, 'typ': typ})


class _FakeRepo:
    def __init__(self) -> None:
        self.summary_calls: list[tuple[int, str]] = []

    def list_portfolios(self, user_id: str):
        if user_id != OWNER:
            return []
        return [SimpleNamespace(id=1, name='Principale', base_currency='EUR', cash_balance=10.0)]

    def resolve_portfolio_scope(self, portfolio_ids, user_id: str):
        if list(portfolio_ids) != [1] or user_id != OWNER:
            raise ValueError('Portfolio non trovato')
        return SimpleNamespace(portfolio_ids=(1,), base_currency='EUR')

    def get_summary(self, portfolio_id: int, user_id: str):
        self.summary_calls.append((portfolio_id, user_id))
        return SimpleNamespace(
            market_value=1000.0, cost_basis=900.0, unrealized_pl=100.0, unrealized_pl_pct=11.11,
            day_change=5.0, day_change_pct=0.5, cash_balance=10.0, base_currency='EUR',
        )


def _mcp_endpoint():
    for route in api_main.app.router.routes:
        if isinstance(route, Route) and route.path == '/mcp':
            return route.app
    raise AssertionError('/mcp route not registered')


@pytest.fixture
def fake_repo(monkeypatch):
    repo = _FakeRepo()
    monkeypatch.setattr(api_main, 'repo', repo)
    return repo


@pytest.fixture
def mcp_on(monkeypatch, fake_repo):
    s = api_main.settings
    monkeypatch.setattr(s, 'mcp_enabled', True)
    monkeypatch.setattr(s, 'clerk_auth_enabled', True)
    monkeypatch.setattr(s, 'clerk_issuer', ISSUER)
    monkeypatch.setattr(s, 'mcp_resource_url', RESOURCE)
    monkeypatch.setattr(s, 'clerk_jwks_url', '')
    monkeypatch.setattr(s, 'clerk_secret_key', '')
    monkeypatch.setattr(s, 'mcp_allowed_client_ids', '')
    monkeypatch.setattr(s, 'mcp_required_scopes', '')
    monkeypatch.setattr(s, 'mcp_require_audience', False)
    monkeypatch.setattr(s, 'mcp_scopes_supported', 'profile email')
    monkeypatch.setattr(app_auth, '_fetch_jwks', lambda url: [_public_jwk(_PRIVATE_KEY, KID)])
    monkeypatch.setitem(app_auth._JWKS_CACHE, 'keys', [])
    monkeypatch.setitem(app_auth._JWKS_CACHE, 'expires_at', 0.0)
    monkeypatch.setattr(_mcp_endpoint(), '_limiter', SlidingWindowRateLimiter(max_requests=1000, window_seconds=60))
    mcp_auth.clear_token_cache()
    yield s
    mcp_auth.clear_token_cache()


def _rpc(client, method, params=None, *, token=None, request_id=1, headers=None):
    body = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
    if params is not None:
        body['params'] = params
    all_headers = dict(MCP_HEADERS)
    if token is not None:
        all_headers['Authorization'] = f'Bearer {token}'
    all_headers.update(headers or {})
    return client.post('/mcp', content=json.dumps(body), headers=all_headers)


# --- availability (fail closed) ---------------------------------------------

def test_mcp_disabled_is_not_served(monkeypatch, fake_repo):
    monkeypatch.setattr(api_main.settings, 'mcp_enabled', False)
    client = TestClient(api_main.app)

    assert _rpc(client, 'tools/list', token=_make_token()).status_code == 404
    assert client.get('/.well-known/oauth-protected-resource').status_code == 404
    assert client.get('/.well-known/oauth-authorization-server').status_code == 404


def test_mcp_with_clerk_disabled_is_not_served(mcp_on, monkeypatch):
    monkeypatch.setattr(mcp_on, 'clerk_auth_enabled', False)
    client = TestClient(api_main.app)

    response = _rpc(client, 'tools/list', token=_make_token())
    assert response.status_code == 503
    assert 'WWW-Authenticate' not in response.headers
    assert client.get('/.well-known/oauth-protected-resource').status_code == 503


def test_mcp_with_missing_settings_is_not_served(mcp_on, monkeypatch):
    monkeypatch.setattr(mcp_on, 'clerk_issuer', '')
    client = TestClient(api_main.app)

    assert _rpc(client, 'tools/list', token=_make_token()).status_code == 503


def test_resolve_mcp_config_validation():
    base = dict(clerk_auth_enabled=True, clerk_issuer=ISSUER, mcp_resource_url=RESOURCE, clerk_jwks_url='')
    config, errors = resolve_mcp_config(SimpleNamespace(**base))
    assert errors == []
    assert config.jwks_url == f'{ISSUER}/.well-known/jwks.json'
    assert config.resource_metadata_url == PRM_URL
    assert config.host == 'testserver'

    for override in (
        {'clerk_auth_enabled': False},
        {'clerk_issuer': 'http://clerk.example.test'},
        {'mcp_resource_url': ''},
        {'mcp_resource_url': 'http://api.example.com/mcp'},
    ):
        config, errors = resolve_mcp_config(SimpleNamespace(**{**base, **override}))
        assert config is None and errors, override


# --- authentication -----------------------------------------------------------

def test_missing_token_returns_401_with_resource_metadata(mcp_on):
    client = TestClient(api_main.app)
    response = _rpc(client, 'initialize')

    assert response.status_code == 401
    assert response.headers['WWW-Authenticate'] == f'Bearer resource_metadata="{PRM_URL}"'


def test_get_without_token_is_401_too(mcp_on):
    response = TestClient(api_main.app).get('/mcp')
    assert response.status_code == 401
    assert 'resource_metadata=' in response.headers['WWW-Authenticate']


@pytest.mark.parametrize(
    'token_factory',
    [
        lambda: 'not-a-token',
        lambda: 'a.b.c',
        # Clerk session token of the web app: same keys, typ JWT.
        lambda: _make_token(typ='JWT'),
        lambda: _make_token(key=_OTHER_KEY),
        lambda: _make_token(kid='unknown-kid'),
        lambda: _make_token(iss='https://evil.example.test'),
        lambda: _make_token(exp=int(time.time()) - 60),
        lambda: _make_token(client_id=None),
        lambda: _make_token(sub='mch_machine'),
        lambda: _make_token(aud='https://other.example.test/mcp'),
    ],
    ids=['garbage', 'bad-jwt', 'session-token', 'wrong-key', 'unknown-kid', 'wrong-issuer',
         'expired', 'no-client-id', 'non-user-subject', 'wrong-audience'],
)
def test_invalid_tokens_return_401(mcp_on, token_factory):
    response = _rpc(TestClient(api_main.app), 'tools/list', token=token_factory())

    assert response.status_code == 401
    header = response.headers['WWW-Authenticate']
    assert header.startswith(f'Bearer resource_metadata="{PRM_URL}"')
    assert 'error="invalid_token"' in header


def test_non_bearer_scheme_is_rejected(mcp_on):
    client = TestClient(api_main.app)
    response = client.post('/mcp', content='{}', headers={**MCP_HEADERS, 'Authorization': f'Basic {_make_token()}'})
    assert response.status_code == 401


def test_audience_matching_resource_is_accepted(mcp_on):
    response = _rpc(TestClient(api_main.app), 'tools/list', token=_make_token(aud=[RESOURCE]))
    assert response.status_code == 200


def test_required_audience_and_scope_and_client_allowlist(mcp_on, monkeypatch):
    client = TestClient(api_main.app)

    monkeypatch.setattr(mcp_on, 'mcp_require_audience', True)
    assert _rpc(client, 'tools/list', token=_make_token()).status_code == 401
    monkeypatch.setattr(mcp_on, 'mcp_require_audience', False)

    monkeypatch.setattr(mcp_on, 'mcp_required_scopes', 'valore365:read')
    response = _rpc(client, 'tools/list', token=_make_token())
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers['WWW-Authenticate']
    monkeypatch.setattr(mcp_on, 'mcp_required_scopes', '')

    monkeypatch.setattr(mcp_on, 'mcp_allowed_client_ids', 'client_other')
    assert _rpc(client, 'tools/list', token=_make_token()).status_code == 401
    monkeypatch.setattr(mcp_on, 'mcp_allowed_client_ids', 'client_abc')
    assert _rpc(client, 'tools/list', token=_make_token()).status_code == 200


class _FakeHttpResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _opaque_payload(**overrides):
    payload = {
        'object': 'clerk_idp_oauth_access_token',
        'id': 'oat_id',
        'client_id': 'client_abc',
        'subject': OWNER,
        'scopes': ['profile', 'email'],
        'revoked': False,
        'revocation_reason': None,
        'expired': False,
        'expiration': (time.time() + 300) * 1000,
        'created_at': time.time() * 1000,
        'updated_at': time.time() * 1000,
    }
    payload.update(overrides)
    return payload


def test_opaque_token_verified_with_clerk_and_cached(mcp_on, monkeypatch):
    monkeypatch.setattr(mcp_on, 'clerk_secret_key', 'sk_test_secret')
    calls = []

    def _fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return _FakeHttpResponse(200, _opaque_payload())

    monkeypatch.setattr(mcp_auth.httpx, 'post', _fake_post)
    client = TestClient(api_main.app)

    for request_id in (1, 2):
        response = _rpc(client, 'tools/list', token='oat_opaque_token', request_id=request_id)
        assert response.status_code == 200

    assert len(calls) == 1
    url, body, headers = calls[0]
    assert url == 'https://api.clerk.com/v1/oauth_applications/access_tokens/verify'
    assert body == {'access_token': 'oat_opaque_token'}
    assert headers == {'Authorization': 'Bearer sk_test_secret'}


@pytest.mark.parametrize(
    'status_code, payload',
    [
        (200, _opaque_payload(revoked=True)),
        (200, _opaque_payload(expired=True)),
        (200, _opaque_payload(subject='mch_machine')),
        (404, {'errors': []}),
    ],
    ids=['revoked', 'expired', 'machine', 'not-found'],
)
def test_opaque_token_rejected(mcp_on, monkeypatch, status_code, payload):
    monkeypatch.setattr(mcp_on, 'clerk_secret_key', 'sk_test_secret')
    monkeypatch.setattr(mcp_auth.httpx, 'post', lambda *a, **kw: _FakeHttpResponse(status_code, payload))

    response = _rpc(TestClient(api_main.app), 'tools/list', token='oat_opaque_token')
    assert response.status_code == 401


def test_opaque_token_without_secret_key_is_rejected(mcp_on, monkeypatch):
    def _fail(*_a, **_kw):
        raise AssertionError('Clerk must not be called without a secret key')

    monkeypatch.setattr(mcp_auth.httpx, 'post', _fail)
    assert _rpc(TestClient(api_main.app), 'tools/list', token='oat_opaque_token').status_code == 401


# --- metadata -----------------------------------------------------------------

@pytest.mark.parametrize('path', ['/.well-known/oauth-protected-resource', '/.well-known/oauth-protected-resource/mcp'])
def test_protected_resource_metadata(mcp_on, path):
    response = TestClient(api_main.app).get(path)

    assert response.status_code == 200
    assert response.json() == {
        'resource': RESOURCE,
        'authorization_servers': [ISSUER],
        'bearer_methods_supported': ['header'],
        'scopes_supported': ['profile', 'email'],
        'resource_name': 'Valore365',
    }


# --- MCP protocol -------------------------------------------------------------

def test_initialize_and_list_read_only_tools(mcp_on):
    client = TestClient(api_main.app)
    token = _make_token()

    init = _rpc(client, 'initialize', {
        'protocolVersion': '2025-06-18',
        'capabilities': {},
        'clientInfo': {'name': 'pytest', 'version': '1.0'},
    }, token=token)
    assert init.status_code == 200
    result = init.json()['result']
    assert result['serverInfo']['name'] == 'valore365'
    assert 'tools' in result['capabilities']
    assert 'mcp-session-id' not in {k.lower() for k in init.headers}

    listed = _rpc(client, 'tools/list', token=token, request_id=2)
    assert listed.status_code == 200
    tools = listed.json()['result']['tools']
    names = {t['name'] for t in tools}
    assert names == {'list_portfolios', *(t['name'] for t in TOOL_DEFINITIONS)}

    for tool in tools:
        assert tool['annotations']['readOnlyHint'] is True
        assert tool['annotations']['destructiveHint'] is False
        if tool['name'] != 'list_portfolios':
            assert tool['inputSchema']['required'][0] == 'portfolio_id'
            assert tool['inputSchema']['properties']['portfolio_id']['type'] == 'integer'


def test_ping(mcp_on):
    response = _rpc(TestClient(api_main.app), 'ping', token=_make_token())
    assert response.status_code == 200
    assert response.json()['result'] == {}


def test_list_portfolios_tool_returns_only_user_portfolios(mcp_on):
    response = _rpc(TestClient(api_main.app), 'tools/call', {'name': 'list_portfolios', 'arguments': {}}, token=_make_token())

    assert response.status_code == 200
    result = response.json()['result']
    assert result['isError'] is False
    assert result['structuredContent'] == {'portfolios': [{'id': 1, 'name': 'Principale', 'base_currency': 'EUR'}]}


def test_tool_call_on_owned_portfolio(mcp_on, fake_repo):
    response = _rpc(
        TestClient(api_main.app), 'tools/call',
        {'name': 'get_portfolio_summary', 'arguments': {'portfolio_id': 1}},
        token=_make_token(),
    )

    result = response.json()['result']
    assert result['isError'] is False
    assert result['structuredContent']['market_value'] == 1000.0
    assert fake_repo.summary_calls == [(1, OWNER)]


def test_tool_call_on_portfolio_not_owned_returns_error(mcp_on, fake_repo):
    client = TestClient(api_main.app)
    # A portfolio that does not exist for the owner, and the owner's
    # portfolio read with another user's token.
    for portfolio_id, sub in ((99, OWNER), (1, 'user_intruder')):
        response = _rpc(
            client, 'tools/call',
            {'name': 'get_portfolio_summary', 'arguments': {'portfolio_id': portfolio_id}},
            token=_make_token(sub=sub),
        )
        result = response.json()['result']
        assert result['isError'] is True
        assert result['content'][0]['text'] == 'Portfolio non trovato'

    assert fake_repo.summary_calls == []


def test_tool_call_requires_portfolio_id(mcp_on):
    response = _rpc(TestClient(api_main.app), 'tools/call', {'name': 'get_positions', 'arguments': {}}, token=_make_token())
    result = response.json()['result']
    assert result['isError'] is True
    assert 'portfolio_id' in result['content'][0]['text']


def test_unknown_tool_is_rejected(mcp_on):
    response = _rpc(
        TestClient(api_main.app), 'tools/call',
        {'name': 'delete_portfolio', 'arguments': {'portfolio_id': 1}},
        token=_make_token(),
    )
    result = response.json()['result']
    assert result['isError'] is True
    assert 'Tool sconosciuto' in result['content'][0]['text']


def test_only_post_is_allowed(mcp_on):
    response = TestClient(api_main.app).get('/mcp', headers={'Authorization': f'Bearer {_make_token()}'})
    assert response.status_code == 405
    assert response.headers['Allow'] == 'POST'


def test_rate_limit_per_user(mcp_on, monkeypatch):
    monkeypatch.setattr(_mcp_endpoint(), '_limiter', SlidingWindowRateLimiter(max_requests=1, window_seconds=60))
    client = TestClient(api_main.app)

    assert _rpc(client, 'ping', token=_make_token()).status_code == 200
    assert _rpc(client, 'ping', token=_make_token()).status_code == 429
    assert _rpc(client, 'ping', token=_make_token(sub='user_other')).status_code == 200


def test_browser_origin_not_allowed_by_default(mcp_on):
    response = _rpc(TestClient(api_main.app), 'ping', token=_make_token(), headers={'Origin': 'https://evil.example.test'})
    assert response.status_code == 400


def test_sanitize_output_truncates_and_drops_non_finite():
    long_text = 'x' * (MAX_TEXT_FIELD_CHARS + 50)
    result = sanitize_output({'a': long_text, 'b': [float('nan'), 1.5], 'c': {'d': float('inf')}})

    assert len(result['a']) == MAX_TEXT_FIELD_CHARS + 1
    assert result['b'] == [None, 1.5]
    assert result['c'] == {'d': None}


def test_stateless_teardown_noise_filter_only_drops_closed_stream_errors():
    import logging
    import sys

    import anyio

    from app.mcp_server.routes import _StatelessTeardownNoiseFilter

    def _record(message, exc):
        try:
            raise exc
        except Exception:
            exc_info = sys.exc_info()
        return logging.LogRecord('mcp.server.streamable_http', logging.ERROR, __file__, 1, message, None, exc_info)

    noise_filter = _StatelessTeardownNoiseFilter()
    assert noise_filter.filter(_record('Error in message router', anyio.ClosedResourceError())) is False
    assert noise_filter.filter(_record('Error in message router', RuntimeError('boom'))) is True
    assert noise_filter.filter(_record('Other error', anyio.ClosedResourceError())) is True
