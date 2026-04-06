"""
Web routes for the user-facing setup and disconnect flows.

Auth model (SeleniumBase UC):
------------------------------
Login credentials are submitted via a plain HTML form. A background thread
runs SeleniumBase UC (undetected Chrome) to authenticate with Garmin's SSO,
bypassing Cloudflare without a residential proxy. On headless Linux (Railway)
it uses a virtual X display (xvfb) rather than Chrome's headless flag.

Setup flow
----------
1. GET  /setup              — multi-step form: credentials → MFA (if needed) → success
2. POST /api/setup/login    — starts UC login; blocks until mfa_required/success/error
3. POST /api/setup/mfa      — supplies MFA code to waiting session; returns mcp_url
4. POST /api/disconnect     — revoke by email

Other routes
------------
GET  /            → redirect to /setup
GET  /disconnect  → disconnect form
GET  /health      → Railway health check
GET  /debug/mcp   → MCP session diagnostics
POST /api/setup/import-token → register session from external script
"""

import asyncio
import logging
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
from app.uc_session import create_uc_session, get_uc_session, remove_uc_session

log = logging.getLogger(__name__)

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
# POST /api/setup/login  — step 1: submit credentials
# ---------------------------------------------------------------------------

async def api_setup_login(request: Request) -> JSONResponse:
    """
    Start a SeleniumBase UC login session with the provided credentials.

    Blocks until the browser either reaches Garmin Connect (success),
    hits an MFA page (mfa_required), or fails (error). Typically 20-60s.

    Request body: {"email": str, "password": str}
    Response (success):      {"state": "success", "mcp_url": str}
    Response (MFA required): {"state": "mfa_required", "session_id": str}
    Response (error):        {"error": str}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    email    = (body.get("email")    or "").strip()
    password = (body.get("password") or "").strip()

    if not email or not password:
        return JSONResponse({"error": "Email and password are required"}, status_code=400)

    loop = asyncio.get_event_loop()
    session = create_uc_session(email, password)

    # Wait for the browser thread to signal a state change (non-blocking)
    new_state = await loop.run_in_executor(None, session.wait_for_state_change, 120)

    if new_state == "mfa_required":
        return JSONResponse({"state": "mfa_required", "session_id": session.session_id})

    if new_state == "success":
        mcp_url = await _finalize_session(request, session, email)
        remove_uc_session(session.session_id)
        if mcp_url is None:
            return JSONResponse({"error": "Login succeeded but failed to save account"}, status_code=500)
        return JSONResponse({"state": "success", "mcp_url": mcp_url})

    # error or timeout
    remove_uc_session(session.session_id)
    return JSONResponse({"error": session.error or "Login failed — please try again"}, status_code=400)


# ---------------------------------------------------------------------------
# POST /api/setup/mfa  — step 2 (optional): submit MFA code
# ---------------------------------------------------------------------------

async def api_setup_mfa(request: Request) -> JSONResponse:
    """
    Submit an MFA code to a pending login session.

    Request body: {"session_id": str, "code": str, "email": str}
    Response (success): {"state": "success", "mcp_url": str}
    Response (error):   {"error": str}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    session_id = (body.get("session_id") or "").strip()
    code       = (body.get("code")       or "").strip()
    email      = (body.get("email")      or "").strip()

    if not session_id or not code:
        return JSONResponse({"error": "session_id and code are required"}, status_code=400)

    session = get_uc_session(session_id)
    if not session:
        return JSONResponse(
            {"error": "Session not found or expired — please start setup again"},
            status_code=404,
        )

    loop = asyncio.get_event_loop()

    # Unblock the login thread with the MFA code, then wait for the result
    session.submit_mfa(code)
    new_state = await loop.run_in_executor(None, session.wait_for_state_change, 120)

    if new_state == "success":
        effective_email = email or session.email
        mcp_url = await _finalize_session(request, session, effective_email)
        remove_uc_session(session.session_id)
        if mcp_url is None:
            return JSONResponse({"error": "MFA succeeded but failed to save account"}, status_code=500)
        return JSONResponse({"state": "success", "mcp_url": mcp_url})

    remove_uc_session(session.session_id)
    return JSONResponse({"error": session.error or "MFA verification failed"}, status_code=400)


# ---------------------------------------------------------------------------
# Internal: build token JSON and persist to DB
# ---------------------------------------------------------------------------

async def _finalize_session(
    request: Request,
    session,
    email: str,
) -> str | None:
    """Convert a successful UCLoginSession into a stored user + MCP URL."""
    if not session.result:
        return None

    cookies      = session.result.get("cookies", {})
    display_name = session.result.get("display_name", "")

    # Build the token JSON that GarminApiClient expects
    token_json = GarminApiClient(cookies=cookies, display_name=display_name).dumps()

    try:
        return await _save_user_and_get_url(request, token_json, display_name, email)
    except Exception as exc:
        log.exception("Failed to persist user after successful login: %s", exc)
        return None


# ---------------------------------------------------------------------------
# POST /api/setup/import-token  — for the garmin_givemydata / local scripts
# ---------------------------------------------------------------------------

async def api_setup_import_token(request: Request) -> JSONResponse:
    """
    Register a Garmin session obtained externally (e.g. garmin_givemydata,
    scripts/playwright_setup.py, or any tool that exports Garmin cookies).

    Request body: {"email": str, "token": str}
      token — JSON: {"cookies": {name: value, ...}, "display_name": str}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    email = (body.get("email") or "").strip()
    token = (body.get("token") or "").strip()

    if not email or not token:
        return JSONResponse({"error": "email and token are required"}, status_code=400)

    loop = asyncio.get_event_loop()

    def _validate(token_str: str):
        client = GarminApiClient.from_token(token_str)
        try:
            data = client._get("/userprofile-service/socialProfile")
            display_name = (
                data.get("displayName") or data.get("userName")
                if isinstance(data, dict)
                else None
            )
            if display_name:
                client.display_name = display_name
        except Exception as exc:
            log.info("import-token live validation skipped (%s); using display_name from token", exc)
        return client.display_name, client.dumps()

    try:
        display_name, updated_token = await loop.run_in_executor(None, _validate, token)
    except Exception as exc:
        return JSONResponse({"error": f"Token import failed: {exc}"}, status_code=400)

    try:
        mcp_url = await _save_user_and_get_url(request, updated_token, display_name, email)
    except Exception as exc:
        return JSONResponse({"error": f"Session valid but failed to save: {exc}"}, status_code=500)

    return JSONResponse({"mcp_url": mcp_url})


# ---------------------------------------------------------------------------
# POST /api/disconnect
# ---------------------------------------------------------------------------

async def api_disconnect(request: Request) -> JSONResponse:
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
        for user in result.scalars().all():
            user.revoked = True
            user.revoked_at = now
            revoked_count += 1
        await db.commit()

    if revoked_count == 0:
        return JSONResponse(
            {"error": f"No active connections found for {email}."},
            status_code=404,
        )

    return JSONResponse({
        "revoked": revoked_count,
        "message": (
            f"Successfully disconnected {revoked_count} Garmin connection(s) for {email}. "
            "Your MCP URL will no longer work. Visit /setup to reconnect."
        ),
    })


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
    Route("/api/setup/login", api_setup_login, methods=["POST"]),
    Route("/api/setup/mfa", api_setup_mfa, methods=["POST"]),
    Route("/api/setup/import-token", api_setup_import_token, methods=["POST"]),
    Route("/api/disconnect", api_disconnect, methods=["POST"]),
]
