"""Validate the MCP settings and derive the URLs the server publishes.

The MCP endpoint fails closed: it is served only when every check here
passes. Nothing falls back to the "dev-user" of require_auth.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class McpConfig:
    # Public URL of the /mcp endpoint, the OAuth resource identifier.
    resource_url: str
    # Clerk Frontend API URL: authorization server and expected JWT issuer.
    issuer: str
    jwks_url: str
    # RFC 9728 metadata URL for resource_url (path inserted after the
    # well-known prefix), advertised in WWW-Authenticate.
    resource_metadata_url: str
    # Host header value the transport accepts (DNS-rebinding protection).
    host: str


def _normalize_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _is_https_or_local(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and (parts.hostname or "") in _LOCAL_HOSTS


def resolve_mcp_config(settings) -> tuple[McpConfig | None, list[str]]:
    """Return (config, errors). config is None whenever errors is not empty."""
    errors: list[str] = []

    if not settings.clerk_auth_enabled:
        errors.append("MCP_ENABLED richiede CLERK_AUTH_ENABLED=true (nessun fallback dev-user per MCP)")

    issuer = _normalize_url(settings.clerk_issuer)
    if not issuer:
        errors.append("CLERK_ISSUER mancante (URL della Frontend API di Clerk)")
    elif urlsplit(issuer).scheme != "https" or not urlsplit(issuer).hostname:
        errors.append("CLERK_ISSUER deve essere un URL https")

    resource_url = _normalize_url(settings.mcp_resource_url)
    resource_parts = urlsplit(resource_url)
    if not resource_url:
        errors.append("MCP_RESOURCE_URL mancante (URL pubblico dell'endpoint /mcp)")
    elif not resource_parts.hostname or not _is_https_or_local(resource_url):
        errors.append("MCP_RESOURCE_URL deve essere un URL https (http solo per localhost)")
    elif resource_parts.query or resource_parts.fragment:
        errors.append("MCP_RESOURCE_URL non deve contenere query string o fragment")

    if errors:
        return None, errors

    jwks_url = _normalize_url(settings.clerk_jwks_url) or f"{issuer}/.well-known/jwks.json"
    origin = f"{resource_parts.scheme}://{resource_parts.netloc}"
    path = resource_parts.path.rstrip("/")
    return (
        McpConfig(
            resource_url=resource_url,
            issuer=issuer,
            jwks_url=jwks_url,
            resource_metadata_url=f"{origin}/.well-known/oauth-protected-resource{path}",
            host=resource_parts.netloc,
        ),
        [],
    )
