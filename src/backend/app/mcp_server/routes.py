"""HTTP wiring of the MCP server: /mcp plus the OAuth discovery documents.

/mcp is a raw ASGI endpoint in front of the SDK's Streamable HTTP transport
(stateless, JSON responses). Every request is authenticated here, before
the SDK sees it:

- MCP disabled -> 404 (as if not mounted); enabled but misconfigured -> 503.
- no/invalid bearer token -> 401 + WWW-Authenticate with resource_metadata.
- then per-user rate limit, POST only, bounded body.

The discovery documents (/.well-known/...) are public but exist only when
MCP is enabled and correctly configured.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import anyio
import anyio.to_thread
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from ..rate_limit import SlidingWindowRateLimiter
from .auth import McpAuthError, verify_access_token
from .config import McpConfig, resolve_mcp_config
from .tools import ToolDependencies, build_mcp_server, current_principal

logger = logging.getLogger("valore365.mcp")

MCP_PATH = "/mcp"
MAX_BODY_BYTES = 1024 * 1024
_AS_METADATA_TTL = 3600.0


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
        headers=headers,
    )


def _www_authenticate(config: McpConfig, error: str | None = None, description: str | None = None) -> str:
    parts = [f'resource_metadata="{config.resource_metadata_url}"']
    if error:
        parts.append(f'error="{error}"')
    if description:
        parts.append(f'error_description="{description.replace(chr(34), chr(39))}"')
    return "Bearer " + ", ".join(parts)


def _bearer_token(scope: Scope) -> str | None:
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


class McpEndpoint:
    """ASGI app for /mcp: authenticate, rate limit, then hand over to the SDK."""

    def __init__(self, settings, deps_getter) -> None:
        self._settings = settings
        self._server = build_mcp_server(deps_getter)
        self._limiter = SlidingWindowRateLimiter(
            max_requests=settings.mcp_rate_limit_requests,
            window_seconds=settings.mcp_rate_limit_window_seconds,
        )
        self._misconfig_logged = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        response = await self._handle(scope, receive, send)
        if response is not None:
            await response(scope, receive, send)

    async def _handle(self, scope: Scope, receive: Receive, send: Send) -> JSONResponse | None:
        settings = self._settings
        if not settings.mcp_enabled:
            return _json(404, "not_found", "Not Found")

        config, errors = resolve_mcp_config(settings)
        if config is None:
            if not self._misconfig_logged:
                logger.error("MCP endpoint disabled, configuration invalid: %s", "; ".join(errors))
                self._misconfig_logged = True
            return _json(503, "mcp_unavailable", "MCP server not configured")

        token = _bearer_token(scope)
        if token is None:
            return _json(
                401, "auth_error", "Missing bearer token",
                headers={"WWW-Authenticate": _www_authenticate(config)},
            )

        try:
            principal = await anyio.to_thread.run_sync(verify_access_token, token, settings, config)
        except McpAuthError as exc:
            if exc.status_code == 503:
                return _json(503, "auth_unavailable", "Unable to verify token, retry later", headers={"Retry-After": "5"})
            return _json(
                exc.status_code,
                "auth_error" if exc.status_code == 401 else "forbidden",
                exc.description,
                headers={"WWW-Authenticate": _www_authenticate(config, exc.error, exc.description)},
            )
        del token

        # Read by RequestLoggingMiddleware.
        scope.setdefault("state", {})["user_id"] = principal.user_id

        if not self._limiter.allow(f"mcp:{principal.user_id}"):
            return _json(
                429, "rate_limited", "Too many requests. Please slow down.",
                headers={"Retry-After": str(settings.mcp_rate_limit_window_seconds)},
            )

        if scope["method"] != "POST":
            # Stateless server: no GET SSE stream and no session to DELETE.
            return _json(405, "method_not_allowed", "Method Not Allowed", headers={"Allow": "POST"})

        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    too_large = int(value) > MAX_BODY_BYTES
                except ValueError:
                    too_large = True
                if too_large:
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
        reset_token = current_principal.set(principal)
        try:
            async with manager.run():
                await manager.handle_request(scope, _limit_body(receive), send)
        finally:
            current_principal.reset(reset_token)
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
    justetf_client: Any = None,
) -> None:
    deps = ToolDependencies(
        repo=repo,
        performance_service=performance_service,
        finance_client=finance_client,
        justetf_client=justetf_client,
    )

    if settings.mcp_enabled:
        _, errors = resolve_mcp_config(settings)
        if errors:
            logger.error("MCP_ENABLED=true but the MCP server will not be served: %s", "; ".join(errors))
        else:
            logger.info("MCP server enabled at %s", MCP_PATH)

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
            headers={"Cache-Control": "public, max-age=300"},
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
        return JSONResponse(payload, headers={"Cache-Control": "public, max-age=300"})

    for path in ("/.well-known/oauth-protected-resource", f"/.well-known/oauth-protected-resource{MCP_PATH}"):
        app.add_api_route(path, protected_resource_metadata, methods=["GET"], include_in_schema=False)
    for path in ("/.well-known/oauth-authorization-server", f"/.well-known/oauth-authorization-server{MCP_PATH}"):
        app.add_api_route(path, authorization_server_metadata, methods=["GET"], include_in_schema=False)
