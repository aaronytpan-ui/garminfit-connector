"""
Multi-user Garmin adapter.

Auth model change (March 2026):
  Garmin's SSO/OAuth is blocked by Cloudflare, making the garth library
  non-functional.  We now use browser-based session cookies obtained via
  scripts/playwright_setup.py (run locally by each user).

  The cookies + display_name are stored as an encrypted JSON string in the
  existing garth_token_encrypted column (format changed, column name kept).

Per-request flow:
  1. Decrypt the user's stored JSON token from DB
  2. Create a GarminApiClient from the cookies
  3. Run data calls on the isolated client
  4. Persist any updated cookies back to DB (fire-and-forget)
  5. Discard the client — nothing persists between requests
"""

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.auth_manager import decrypt_token, encrypt_token
from app.database import SessionLocal, User
from app.garmin_api_client import GarminApiClient
from garmin_handler import GarminDataHandler


# ---------------------------------------------------------------------------
# Multi-user subclass of GarminDataHandler
# ---------------------------------------------------------------------------

class MultiUserGarminHandler(GarminDataHandler):
    """
    Wraps a pre-authenticated GarminApiClient.

    Inherits ALL data methods from GarminDataHandler without modification.
    Only __init__ is overridden to skip file-based auth and inject the client.
    """

    def __init__(self, api_client: GarminApiClient) -> None:
        # Bypass GarminDataHandler.__init__ (which tries to set up garth/disk auth)
        self.client = api_client
        self._authenticated = True
        self.email = ""
        self.token_store = None
        # Legacy alias: some code accesses handler.garmin
        self.garmin = api_client


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def get_user_by_token(access_token: str) -> Optional[User]:
    """Look up a User record by their MCP access token."""
    async with SessionLocal() as db:
        result = await db.execute(
            select(User).where(
                User.access_token == access_token,
                User.revoked == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()


async def update_last_used(access_token: str) -> None:
    """Update last_used_at timestamp (fire-and-forget)."""
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(User).where(User.access_token == access_token)
            )
            user = result.scalar_one_or_none()
            if user:
                user.last_used_at = datetime.utcnow()
                await db.commit()
    except Exception:
        pass


async def save_refreshed_tokens(access_token: str, garmin_client) -> None:
    """
    Persist the current client state back to the database.

    With cookie-based auth, the server may issue updated session cookies
    during an API call.  Saving the current cookie jar after each call
    ensures we always store the freshest session.
    """
    try:
        new_token_json = garmin_client.garth.dumps()
        encrypted = encrypt_token(new_token_json)
        async with SessionLocal() as db:
            result = await db.execute(
                select(User).where(User.access_token == access_token)
            )
            user = result.scalar_one_or_none()
            if user:
                user.garth_token_encrypted = encrypted
                user.token_refreshed_at = datetime.utcnow()
                await db.commit()
    except Exception:
        pass  # Non-critical — current session is still valid


# ---------------------------------------------------------------------------
# Primary adapter function used by MCP tools
# ---------------------------------------------------------------------------

async def get_garmin_handler(access_token: str) -> MultiUserGarminHandler:
    """
    Load the user's session cookies from DB and return an authenticated
    MultiUserGarminHandler ready for data queries.

    Raises ValueError if the token is invalid or revoked.
    """
    user = await get_user_by_token(access_token)
    if not user:
        raise ValueError(
            "Invalid or revoked access token. "
            "Please visit /setup to reconnect your Garmin account."
        )

    token_json = decrypt_token(user.garth_token_encrypted)
    api_client = GarminApiClient.from_token(token_json)

    asyncio.create_task(update_last_used(access_token))

    return MultiUserGarminHandler(api_client)


async def run_garmin(access_token: str, fn, *args, **kwargs):
    """
    Helper: get an authenticated handler, run a blocking call in a thread
    executor, save refreshed cookies, and return the result.
    """
    handler = await get_garmin_handler(access_token)
    loop = asyncio.get_event_loop()

    result = await loop.run_in_executor(None, lambda: fn(handler, *args, **kwargs))

    asyncio.create_task(save_refreshed_tokens(access_token, handler.garmin))

    return result
