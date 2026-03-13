"""
Starlette application entry point.

Key components:
  1. GarminMCPRouter — custom ASGI router that:
       - Parses {access_token} from /mcp/{access_token} (Streamable HTTP)
         and from /mcp/{access_token}/sse + /mcp/{access_token}/messages/ (SSE)
       - Sets user_access_token_var ContextVar so MCP tools can identify the user
       - Rewrites the path before delegating to FastMCP's transport app

  2. setup_routes — HTML setup/disconnect pages and /api/* JSON endpoints

  3. on_startup — creates DB tables if they don't exist

The app is served by uvicorn:
  uvicorn app.main:app --host 0.0.0.0 --port $PORT

Transport support:
  - Streamable HTTP (MCP 2025-03): POST/GET /mcp/{token}   ← Claude.ai uses this
  - SSE (legacy):                  GET /mcp/{token}/sse    ← kept for compatibility
"""

import traceback

from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse

from app.database import create_tables
from app.mcp_server import mcp, user_access_token_var
from app.setup_routes import setup_routes


# ---------------------------------------------------------------------------
# Custom ASGI router for per-user MCP URLs
# ---------------------------------------------------------------------------

class GarminMCPRouter:
    """
    Routes requests from (after Starlette Mount("/mcp", ...) strips "/mcp"):

      /{access_token}           → FastMCP Streamable HTTP (GET + POST, MCP 2025-03)
      /{access_token}/sse       → FastMCP SSE endpoint (GET, legacy)
      /{access_token}/messages/ → FastMCP SSE messages (POST, legacy)

    Extracts {access_token} from the URL, sets it in user_access_token_var
    (a contextvars.ContextVar), rewrites the path, and delegates to the
    appropriate FastMCP ASGI app.
    """

    # Legacy SSE subpaths (kept for backward compat)
    SSE_SUBPATHS = {"/sse", "/messages/", "/messages"}

    # Streamable HTTP uses FastMCP's internal path (/mcp is default)
    STREAMABLE_HTTP_INTERNAL_PATH = "/mcp"

    def __init__(self):
        # Lazy-initialized on first request
        self._sse_app = None             # FastMCP SSE transport (legacy)
        self._streamable_app = None      # FastMCP Streamable HTTP transport (current)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            # Lifespan — initialize and pass through to streamable app
            if self._streamable_app is None:
                self._streamable_app = mcp.streamable_http_app()
            await self._streamable_app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "")

        # After Mount("/mcp", ...) strips the prefix, paths arrive as:
        #   /{token}           → Streamable HTTP
        #   /{token}/sse       → SSE GET
        #   /{token}/messages/ → SSE messages POST
        if not path.startswith("/"):
            await self._not_found(scope, receive, send)
            return

        rest = path[1:]   # strip leading "/" → "{token}" or "{token}/sse"

        if not rest:
            await self._not_found(scope, receive, send)
            return

        slash_idx = rest.find("/")

        if slash_idx == -1:
            # No subpath — this is /{token} → Streamable HTTP
            access_token = rest
            transport = "streamable"
            internal_path = self.STREAMABLE_HTTP_INTERNAL_PATH
        else:
            # Has subpath — SSE legacy routing
            access_token = rest[:slash_idx]
            sub_path = rest[slash_idx:]   # "/sse", "/messages/", etc.
            if sub_path not in self.SSE_SUBPATHS:
                await self._not_found(scope, receive, send)
                return
            transport = "sse"
            internal_path = sub_path

        if not access_token:
            await self._not_found(scope, receive, send)
            return

        print(f"[MCP] {method} {path} → transport={transport} token={access_token[:8]}...")

        # Lazy-initialize the appropriate transport app
        if transport == "streamable":
            if self._streamable_app is None:
                self._streamable_app = mcp.streamable_http_app()
            app = self._streamable_app
        else:
            if self._sse_app is None:
                self._sse_app = mcp.sse_app()
            app = self._sse_app

        # Set the ContextVar so MCP tools can read the user's identity
        token_ctx = user_access_token_var.set(access_token)

        # Rewrite path for the inner app
        new_scope = dict(scope)
        new_scope["path"] = internal_path
        new_scope["raw_path"] = internal_path.encode()

        if transport == "sse":
            # For SSE, include access_token in root_path so FastMCP advertises
            # the correct messages URL: /mcp/{token}/messages/?session_id=...
            new_scope["root_path"] = scope.get("root_path", "").rstrip("/") + f"/{access_token}"

        try:
            await app(new_scope, receive, send)
        except Exception as e:
            print(f"[MCP] ERROR in transport={transport}: {type(e).__name__}: {e}")
            traceback.print_exc()
            raise
        finally:
            user_access_token_var.reset(token_ctx)

    @staticmethod
    async def _not_found(scope, receive, send):
        if scope["type"] == "http":
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [[b"content-type", b"application/json"]],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error": "MCP endpoint not found. Check your connector URL."}',
            })


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

_mcp_router = GarminMCPRouter()


async def on_startup():
    """Create database tables on startup (idempotent — uses CREATE IF NOT EXISTS)."""
    import os
    print("✓ garminfit-connector starting up")
    print(f"  DATABASE_URL set: {'yes' if os.environ.get('DATABASE_URL') else 'NO — using SQLite fallback'}")
    print(f"  TOKEN_ENCRYPTION_KEY set: {'yes' if os.environ.get('TOKEN_ENCRYPTION_KEY') else 'NO — will crash on setup'}")
    print(f"  APP_BASE_URL: {os.environ.get('APP_BASE_URL', '(not set — using request host)')}")
    try:
        await create_tables()
        print("✓ Database tables ready")
    except Exception as e:
        print(f"⚠ Database startup warning: {e}")
        print("  App will continue — DB may not be ready yet")


app = Starlette(
    on_startup=[on_startup],
    routes=[
        # Web pages + API endpoints
        *setup_routes,

        # MCP connector — everything under /mcp/ goes to GarminMCPRouter
        Mount("/mcp", app=_mcp_router),
    ],
)
