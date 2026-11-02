"""Remote MCP server (read-only) for Valore365.

Exposes the Copilot read-only tools over the Model Context Protocol
(Streamable HTTP, stateless) at ``/mcp``, protected by Clerk OAuth access
tokens. See docs/mcp.md.
"""

from .routes import register_mcp_routes

__all__ = ["register_mcp_routes"]
