"""HTTP wiring of the MCP server: /mcp plus the OAuth discovery documents.

/mcp is a raw ASGI endpoint in front of the SDK's Streamable HTTP transport
(stateless, JSON responses). Every request is authenticated here, before
the SDK sees it:

- MCP disabled -> 404 (as if not mounted); enabled but misconfigured -> 503.
- client IP with too many failed authentications -> 429, before any call to
  Clerk or the JWKS.
- no/invalid bearer token -> 401 + WWW-Authenticate with resource_metadata
  (generic message; the reason category goes to the logs only).
- user blocked or outside MCP_ALLOWED_USER_IDS -> 403.
- then per-user rate limit, POST only, bounded body.

Every /mcp response carries Cache-Control: no-store, nosniff and an
X-Request-ID, and every request ends with one audit log line (never the
token, the arguments or the tool output).

The discovery documents (/.well-known/...) are public but exist only when
MCP is enabled and correctly configured.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import anyio
import anyio.to_thread
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import HTTPConnection
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send

from ..rate_limit import SlidingWindowRateLimiter, client_ip
from .auth import MAX_TOKEN_LENGTH, McpAuthError, verify_access_token
from .config import McpConfig, resolve_mcp_config
from .tools import McpCallContext, ToolCallLimits, ToolDependencies, build_mcp_server, current_context

logger = logging.getLogger("valore365.mcp")

MCP_PATH = "/mcp"
MAX_BODY_BYTES = 1024 * 1024
# "Bearer " + token; longer headers are rejected without being parsed.
MAX_AUTHORIZATION_HEADER_BYTES = MAX_TOKEN_LENGTH + 16
_AS_METADATA_TTL = 3600.0
_INVALID_TOKEN_MESSAGE = "The access token is invalid or expired"
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class _StatelessTeardownNoiseFilter(logging.Filter):
    """Drop the spurious "Error in message router" of mcp 1.12.x stateless mode.

    After every stateless request the transport is terminated while its
    message router still reads the closed stream, and the SDK logs the
    resulting anyio.ClosedResourceError at ERROR level, once per request,
    after the response has been sent. Any other error still goes through.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage() != "Error in message router" or not record.exc_info:
            return True
        return not isinstance(record.exc_info[1], anyio.ClosedResourceError)


logging.getLogger("mcp.server.streamable_http").addFilter(_StatelessTeardownNoiseFilter())


def _json(status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers={**_NO_STORE_HEADERS, **(headers or {})},
    )


def _www_authenticate(config: McpConfig, error: str | None = None, description: str | None = None) -> str:
    parts = [f'resource_metadata="{config.resource_metadata_url}"']
    if error:
        parts.append(f'error="{error}"')
    if description:
        parts.append(f'error_description="{description.replace(chr(34), chr(39))}"')
    return "Bearer " + ", ".join(parts)


def _bearer_token(scope: Scope) -> str | None:
    """Token of a single ``Authorization: Bearer`` header (length checked by the caller)."""
    values = [v for k, v in scope.get("headers", []) if k == b"authorization"]
    if len(values) != 1:
        return None
    try:
        raw = values[0].decode("latin-1").strip()
    except UnicodeDecodeError:
        return None
    scheme, _, token = raw.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _authorization_too_long(scope: Scope) -> bool:
    return any(
        k == b"authorization" and len(v) > MAX_AUTHORIZATION_HEADER_BYTES for k, v in scope.get("headers", [])
    )


def _with_response_headers(send: Send, extra: list[tuple[bytes, bytes]], audit: dict[str, Any]) -> Send:
    """Add the security headers to every response, the SDK's included."""
    names = {k for k, _ in extra}

    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            audit["status"] = message["status"]
            headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in names]
            message = {**message, "headers": headers + extra}
        await send(message)

    return wrapped


class McpEndpoint:
    """ASGI app for /mcp: authenticate, rate limit, then hand over to the SDK."""

    def __init__(self, settings, deps_getter) -> None:
        self._settings = settings
        self._limits = ToolCallLimits.from_settings(settings)
        self._server = build_mcp_server(deps_getter, self._limits)
        self._limiter = SlidingWindowRateLimiter(
            max_requests=settings.mcp_rate_limit_requests,
            window_seconds=settings.mcp_rate_limit_window_seconds,
        )
        # Failed authentications per client IP (pre-auth abuse protection).
        self._auth_failures = SlidingWindowRateLimiter(
            max_requests=settings.mcp_auth_failure_limit,
            window_seconds=settings.mcp_auth_failure_window_seconds,
        )
        self._misconfig_logged = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        ip = client_ip(HTTPConnection(scope), self._settings)
        audit: dict[str, Any] = {"status": 500, "outcome": "ok", "user": "-", "client": "-"}
        send = _with_response_headers(
            send,
            [
                (b"cache-control", b"no-store"),
                (b"x-content-type-options", b"nosniff"),
                (b"x-request-id", request_id.encode()),
            ],
            audit,
        )
        try:
            response = await self._handle(scope, receive, send, request_id=request_id, ip=ip, audit=audit)
            if response is not None:
                await response(scope, receive, send)
        except Exception:
            audit["outcome"] = "error"
            raise
        finally:
            # Audit log: never the token, the arguments or the tool output.
            logger.info(
                "mcp request rid=%s ip=%s method=%s status=%s outcome=%s user=%s client=%s duration_ms=%.0f",
                request_id,
                ip,
                scope.get("method"),
                audit["status"],
                audit["outcome"],
                audit["user"],
                audit["client"],
                (time.monotonic() - started) * 1000,
            )

    def _auth_failed(self, ip: str, request_id: str, reason: str, audit: dict[str, Any]) -> None:
        audit["outcome"] = f"auth_failed:{reason}"
        logger.warning("mcp auth failed rid=%s ip=%s reason=%s", request_id, ip, reason)
        if self._auth_failures.max_requests > 0:
            self._auth_failures.allow(f"mcp-auth-fail:{ip}")

    async def _handle(
        self, scope: Scope, receive: Receive, send: Send, *, request_id: str, ip: str, audit: dict[str, Any]
    ) -> JSONResponse | None:
        settings = self._settings
        if not settings.mcp_enabled:
            audit["outcome"] = "disabled"
            return _json(404, "not_found", "Not Found")

        config, errors = resolve_mcp_config(settings)
        if config is None:
            if not self._misconfig_logged:
                logger.error("MCP endpoint disabled, configuration invalid: %s", "; ".join(errors))
                self._misconfig_logged = True
            audit["outcome"] = "misconfigured"
            return _json(503, "mcp_unavailable", "MCP server not configured")

        # Checked before the token is even parsed: no call to Clerk or the JWKS.
        # MCP_AUTH_FAILURE_LIMIT=0 disables it (e.g. when every request seems
        # to come from the same proxy IP: see TRUSTED_PROXY_IPS).
        if self._auth_failures.max_requests > 0 and self._auth_failures.is_limited(f"mcp-auth-fail:{ip}"):
            audit["outcome"] = "auth_rate_limited"
            return _json(
                429, "rate_limited", "Too many requests. Please slow down.",
                headers={"Retry-After": str(settings.mcp_auth_failure_window_seconds)},
            )

        invalid_token_response = _json(
            401, "auth_error", _INVALID_TOKEN_MESSAGE,
            headers={"WWW-Authenticate": _www_authenticate(config, "invalid_token", _INVALID_TOKEN_MESSAGE)},
        )
        if _authorization_too_long(scope):
            self._auth_failed(ip, request_id, "too_long", audit)
            return invalid_token_response

        token = _bearer_token(scope)
        if token is None:
            audit["outcome"] = "no_token"
            return _json(
                401, "auth_error", "Missing bearer token",
                headers={"WWW-Authenticate": _www_authenticate(config)},
            )

        try:
            principal = await anyio.to_thread.run_sync(verify_access_token, token, settings, config)
        except McpAuthError as exc:
            if exc.status_code == 503:
                audit["outcome"] = f"auth_unavailable:{exc.reason}"
                return _json(503, "auth_unavailable", "Unable to verify token, retry later", headers={"Retry-After": "5"})
            self._auth_failed(ip, request_id, exc.reason, audit)
            if exc.status_code == 403:
                # insufficient_scope: the missing scope is public configuration.
                return _json(
                    403, "forbidden", "Insufficient scope",
                    headers={"WWW-Authenticate": _www_authenticate(config, exc.error, exc.description)},
                )
            return invalid_token_response
        del token

        audit["user"] = principal.user_id
        audit["client"] = principal.client_id[:100]
        # Read by RequestLoggingMiddleware.
        scope.setdefault("state", {})["user_id"] = principal.user_id

        allowed_users = settings.mcp_allowed_user_ids_set
        if principal.user_id in settings.mcp_blocked_user_ids_set or (
            allowed_users and principal.user_id not in allowed_users
        ):
            audit["outcome"] = "user_not_allowed"
            logger.warning("mcp access denied rid=%s ip=%s user=%s reason=user_not_allowed", request_id, ip, principal.user_id)
            return _json(403, "forbidden", "Access denied")

        if not self._limiter.allow(f"mcp:{principal.user_id}"):
            audit["outcome"] = "rate_limited"
            return _json(
                429, "rate_limited", "Too many requests. Please slow down.",
                headers={"Retry-After": str(settings.mcp_rate_limit_window_seconds)},
            )

        if scope["method"] != "POST":
            # Stateless server: no GET SSE stream and no session to DELETE.
            audit["outcome"] = "method_not_allowed"
            return _json(405, "method_not_allowed", "Method Not Allowed", headers={"Allow": "POST"})

        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    too_large = int(value) > MAX_BODY_BYTES
                except ValueError:
                    too_large = True
                if too_large:
                    audit["outcome"] = "payload_too_large"
                    return _json(413, "payload_too_large", "Request body too large")

        manager = StreamableHTTPSessionManager(
            app=self._server,
            event_store=None,
            json_response=True,
            stateless=True,
            security_settings=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[config.host],
                allowed_origins=settings.mcp_allowed_origins_list,
            ),
        )
        reset_token = current_context.set(McpCallContext(principal=principal, request_id=request_id, client_ip=ip))
        try:
            async with manager.run():
                await manager.handle_request(scope, _limit_body(receive), send)
        finally:
            current_context.reset(reset_token)
        return None


def _limit_body(receive: Receive) -> Receive:
    """Stop reading a body that grows past MAX_BODY_BYTES (chunked uploads)."""
    received = 0

    async def wrapped() -> dict[str, Any]:
        nonlocal received
        message = await receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > MAX_BODY_BYTES:
                raise ValueError("MCP request body too large")
        return message

    return wrapped


class _AuthServerMetadataCache:
    def __init__(self) -> None:
        self.issuer: str | None = None
        self.payload: dict[str, Any] | None = None
        self.expires_at = 0.0

    async def get(self, issuer: str) -> dict[str, Any]:
        now = time.monotonic()
        if self.payload is not None and self.issuer == issuer and now < self.expires_at:
            return self.payload
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{issuer}/.well-known/oauth-authorization-server")
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected authorization server metadata")
        self.issuer, self.payload, self.expires_at = issuer, payload, now + _AS_METADATA_TTL
        return payload


def register_mcp_routes(
    app: FastAPI,
    settings,
    *,
    repo: Any,
    performance_service: Any,
    finance_client: Any = None,
) -> None:
    # No justETF client on purpose: see ToolDependencies (MCP never writes).
    deps = ToolDependencies(
        repo=repo,
        performance_service=performance_service,
        finance_client=finance_client,
    )

    if settings.mcp_enabled:
        _, errors = resolve_mcp_config(settings)
        if errors:
            logger.error("MCP_ENABLED=true but the MCP server will not be served: %s", "; ".join(errors))
        else:
            logger.info("MCP server enabled at %s", MCP_PATH)
            if not settings.mcp_require_audience:
                logger.warning(
                    "MCP_REQUIRE_AUDIENCE=false: access tokens without an `aud` claim are accepted. "
                    "Enable it once Clerk tokens carry aud=%s (see docs/mcp.md)",
                    settings.mcp_resource_url,
                )

    app.router.routes.append(Route(MCP_PATH, endpoint=McpEndpoint(settings, lambda: deps), include_in_schema=False))

    def _config_or_error() -> tuple[McpConfig | None, JSONResponse | None]:
        if not settings.mcp_enabled:
            return None, _json(404, "not_found", "Not Found")
        config, _errors = resolve_mcp_config(settings)
        if config is None:
            return None, _json(503, "mcp_unavailable", "MCP server not configured")
        return config, None

    async def protected_resource_metadata() -> JSONResponse:
        config, error = _config_or_error()
        if error is not None:
            return error
        return JSONResponse(
            {
                "resource": config.resource_url,
                "authorization_servers": [config.issuer],
                "bearer_methods_supported": ["header"],
                "scopes_supported": settings.mcp_scopes_supported_list,
                "resource_name": "Valore365",
            },
            # Public, non-sensitive and identical for everyone: cacheable.
            headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"},
        )

    as_cache = _AuthServerMetadataCache()

    async def authorization_server_metadata() -> JSONResponse:
        # For clients that still look for RFC 8414 metadata on the resource
        # server (MCP spec 2025-03-26): serve Clerk's own document, as
        # recommended by Clerk's MCP tooling.
        config, error = _config_or_error()
        if error is not None:
            return error
        try:
            payload = await as_cache.get(config.issuer)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Unable to fetch Clerk authorization server metadata: %s", type(exc).__name__)
            return _json(502, "upstream_error", "Authorization server metadata unavailable")
        return JSONResponse(
            payload, headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"}
        )

    for path in ("/.well-known/oauth-protected-resource", f"/.well-known/oauth-protected-resource{MCP_PATH}"):
        app.add_api_route(path, protected_resource_metadata, methods=["GET"], include_in_schema=False)
    for path in ("/.well-known/oauth-authorization-server", f"/.well-known/oauth-authorization-server{MCP_PATH}"):
        app.add_api_route(path, authorization_server_metadata, methods=["GET"], include_in_schema=False)
