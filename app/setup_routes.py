"""
Web routes for the user-facing setup and disconnect flows.

Auth model (browser-based session cookies):
--------------------------------------------
Garmin's SSO is protected by Cloudflare Turnstile, which blocks automated
login attempts.  Users now authenticate locally using Playwright (a real
Chrome browser) via scripts/playwright_setup.py, then import the resulting
session cookies to this server.

Endpoints:
  GET  /            → redirect to /setup
  GET  /setup       → setup instructions page
  GET  /disconnect  → disconnect form
  GET  /health      → health check (Railway)
  GET  /debug/mcp   → MCP session diagnostics

  POST /api/setup/import-token  → register cookies obtained by playwright_setup.py
  POST /api/disconnect          → revoke user's access token
"""

import asyncio
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from app.auth_manager import encrypt_token, generate_access_token
from app.database import SessionLocal, User
from app.garmin_api_client import GarminApiClient


# ---------------------------------------------------------------------------
# Jinja2 template environment
# ---------------------------------------------------------------------------

_templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja_env = Environment(
    loader=FileSystemLoader(_templates_dir),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **ctx) -> HTMLResponse:
    tmpl = _jinja_env.get_template(template_name)
    return HTMLResponse(tmpl.render(**ctx))


# ---------------------------------------------------------------------------
# Helper: save authenticated user and return their MCP URL
# ---------------------------------------------------------------------------

async def _save_user_and_get_url(
    request: Request,
    token_json: str,
    display_name: str | None,
    email: str,
) -> str:
    access_token = generate_access_token()
    encrypted = encrypt_token(token_json)

    base_url = os.environ.get("APP_BASE_URL", str(request.base_url).rstrip("/"))
    mcp_url = f"{base_url}/garmin/?token={access_token}"

    async with SessionLocal() as db:
        user = User(
            access_token=access_token,
            garth_token_encrypted=encrypted,
            display_name=display_name,
            garmin_email=email.lower().strip(),
            created_at=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()

    return mcp_url


# ---------------------------------------------------------------------------
# HTML page routes
# ---------------------------------------------------------------------------

async def root(request: Request):
    return RedirectResponse(url="/setup")


async def setup_page(request: Request) -> HTMLResponse:
    return _render("setup.html")


async def disconnect_page(request: Request) -> HTMLResponse:
    return _render("disconnect.html")


async def setup_success_page(request: Request) -> HTMLResponse:
    return _render("success.html")


async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "garminfit-connector"})


async def debug_mcp(request: Request) -> JSONResponse:
    """Diagnostic endpoint — confirms the MCP session manager is alive."""
    from app.mcp_server import mcp
    try:
        sm = mcp.session_manager
        return JSONResponse({
            "status": "ok",
            "session_manager": type(sm).__name__,
            "json_response": sm.json_response,
            "stateless": sm.stateless,
            "active_sessions": len(getattr(sm, "_server_instances", {})),
        })
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# API: Import session cookies (from scripts/playwright_setup.py)
# ---------------------------------------------------------------------------

async def api_setup_import_token(request: Request) -> JSONResponse:
    """
    Register a Garmin session obtained by running scripts/playwright_setup.py
    locally on the user's machine.

    Request body: {"email": str, "token": str}
      token — JSON string: {"cookies": {name: value, ...}, "display_name": str}

    Responses:
      200 {"mcp_url": str}   — success
      400 {"error": str}     — invalid/expired token or bad request
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    email = (body.get("email") or "").strip()
    token = (body.get("token") or "").strip()

    if not email or not token:
        return JSONResponse({"error": "email and token are required"}, status_code=400)

    # Validate the token by making a live API call
    loop = asyncio.get_event_loop()

    def _validate(token_str: str):
        client = GarminApiClient.from_token(token_str)
        # Fetch social profile — verifies the session is live
        data = client._get("/userprofile-service/socialProfile")
        display_name = (
            data.get("displayName") or data.get("userName")
            if isinstance(data, dict)
            else None
        )
        # Sync display_name back to the client so dumps() includes it
        if display_name:
            client.display_name = display_name
        return display_name, client.dumps()

    try:
        display_name, updated_token = await loop.run_in_executor(None, _validate, token)
    except Exception as e:
        print(f"[import-token] validation error: {type(e).__name__}: {e}")
        return JSONResponse(
            {"error": f"Token validation failed: {e}"},
            status_code=400,
        )

    try:
        mcp_url = await _save_user_and_get_url(request, updated_token, display_name, email)
    except Exception as e:
        print(f"[import-token] save error: {type(e).__name__}: {e}")
        return JSONResponse(
            {"error": f"Session valid but failed to save account: {e}"},
            status_code=500,
        )

    return JSONResponse({"mcp_url": mcp_url})


# ---------------------------------------------------------------------------
# API: Disconnect (revoke access token)
# ---------------------------------------------------------------------------

async def api_disconnect(request: Request) -> JSONResponse:
    """
    Revoke all access tokens for a given Garmin email address.

    Request body: {"email": str}

    Responses:
      200 {"revoked": int}  — number of tokens revoked
      400 {"error": str}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    email = (body.get("email") or "").strip().lower()
    if not email:
        return JSONResponse({"error": "Email address is required"}, status_code=400)

    now = datetime.utcnow()
    revoked_count = 0

    async with SessionLocal() as db:
        result = await db.execute(
            select(User).where(
                User.garmin_email == email,
                User.revoked == False,  # noqa: E712
            )
        )
        users = result.scalars().all()
        for user in users:
            user.revoked = True
            user.revoked_at = now
            revoked_count += 1
        await db.commit()

    if revoked_count == 0:
        return JSONResponse(
            {"error": f"No active connections found for {email}."},
            status_code=404,
        )

    return JSONResponse(
        {
            "revoked": revoked_count,
            "message": (
                f"Successfully disconnected {revoked_count} Garmin connection(s) for {email}. "
                "Your MCP URL will no longer work. Visit /setup to reconnect."
            ),
        }
    )


# ---------------------------------------------------------------------------
# Route list (imported by main.py)
# ---------------------------------------------------------------------------

setup_routes = [
    Route("/", root, methods=["GET"]),
    Route("/setup", setup_page, methods=["GET"]),
    Route("/setup/success", setup_success_page, methods=["GET"]),
    Route("/disconnect", disconnect_page, methods=["GET"]),
    Route("/health", health_check, methods=["GET"]),
    Route("/debug/mcp", debug_mcp, methods=["GET"]),
    Route("/api/setup/import-token", api_setup_import_token, methods=["POST"]),
    Route("/api/disconnect", api_disconnect, methods=["POST"]),
]
