#!/usr/bin/env python3
"""
garmin_setup.py — Local Garmin authentication script for Garmin Chat Connector.

Runs Chrome on YOUR machine to log in to Garmin Connect, then posts the
session cookies to your garminfit-connector server so Claude (and other
AI tools) can query your live Garmin data.

Requirements (install once):
    pip install seleniumbase
    seleniumbase install chromedriver

Usage:
    python garmin_setup.py --server-url https://your-app.up.railway.app

Optional flags:
    --email    your@email.com   (prompted if omitted)
"""

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.request

GARMIN_CONNECT_URL = "https://connect.garmin.com/modern/"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authenticate with Garmin and register your session with "
                    "garminfit-connector.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--server-url", "--server_url",
        default="",
        metavar="URL",
        help="Base URL of your garminfit-connector deployment "
             "(e.g. https://your-app.up.railway.app)",
    )
    parser.add_argument(
        "--email",
        default="",
        help="Garmin account email address",
    )
    args = parser.parse_args()

    # ── Collect inputs ──────────────────────────────────────────────────────

    server_url = args.server_url.strip().rstrip("/")
    if not server_url:
        server_url = input(
            "Server URL (e.g. https://your-app.up.railway.app): "
        ).strip().rstrip("/")
    if not server_url:
        _die("Server URL is required.")

    email = args.email.strip()
    if not email:
        email = input("Garmin email: ").strip()
    if not email:
        _die("Email is required.")

    password = getpass.getpass("Garmin password: ")
    if not password:
        _die("Password is required.")

    # ── Run browser login ───────────────────────────────────────────────────

    print(
        "\nOpening Chrome… Garmin Connect will load in a few seconds.\n"
        "Complete any CAPTCHA or two-factor prompts in the browser window.\n"
    )

    try:
        cookies = _run_browser_login(email, password)
    except ImportError:
        _die(
            "seleniumbase is not installed.\n\n"
            "Install it with:\n"
            "    pip install seleniumbase\n"
            "    seleniumbase install chromedriver"
        )

    if not cookies:
        _die(
            "Login failed — no Garmin cookies were captured.\n"
            "Make sure you logged in successfully before the browser closed."
        )

    print(f"Login successful. {len(cookies)} session cookies captured.")
    print("Registering your session with the server…\n")

    # ── Register with server ────────────────────────────────────────────────

    try:
        mcp_url = _register_with_server(server_url, email, cookies)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        _die(f"Server returned HTTP {exc.code}:\n{body}")
    except urllib.error.URLError as exc:
        _die(f"Could not reach server ({server_url}):\n{exc.reason}")
    except ValueError as exc:
        _die(str(exc))

    # ── Done ────────────────────────────────────────────────────────────────

    print("=" * 62)
    print("  Connected! Your MCP URL:")
    print()
    print(f"  {mcp_url}")
    print()
    print("  Paste this URL into Claude Desktop, Claude.ai, or any other")
    print("  MCP-compatible AI client to connect your Garmin data.")
    print("=" * 62)


# ---------------------------------------------------------------------------
# Browser login via SeleniumBase UC
# ---------------------------------------------------------------------------

def _run_browser_login(email: str, password: str) -> dict:
    """
    Opens Chrome (via SeleniumBase UC mode) to log in to Garmin Connect.
    UC mode patches the ChromeDriver binary to bypass Cloudflare checks —
    no residential proxy needed.

    Returns a dict of {cookie_name: cookie_value} scoped to garmin.com domains.
    """
    from seleniumbase import SB  # noqa: PLC0415  (lazy import — gives clean error if missing)

    with SB(uc=True, headless=False) as sb:
        # uc_open_with_reconnect briefly disconnects CDP during navigation
        # so Cloudflare sees it as human-initiated.
        sb.uc_open_with_reconnect(GARMIN_CONNECT_URL, reconnect_time=6)

        # Dismiss Cloudflare CAPTCHA if it appears
        try:
            sb.uc_gui_click_captcha()
        except Exception:
            pass

        # Wait for Garmin SSO login form
        try:
            sb.wait_for_element('input[name="email"]', timeout=40)
        except Exception:
            print(
                "ERROR: Garmin login page did not load within 40 seconds.\n"
                "Cloudflare may have blocked the request — try again.",
                file=sys.stderr,
            )
            return {}

        # Fill in credentials
        sb.type('input[name="email"]', email)
        sb.type('input[name="password"]', password)

        # Check "Remember me" for a longer session lifetime
        try:
            sb.click('input[id="rememberMe"]', timeout=2)
        except Exception:
            pass

        sb.click('button[type="submit"]')
        sb.sleep(3)

        # ── MFA detection ──────────────────────────────────────────────────
        current_url = sb.get_current_url()
        if any(
            x in current_url.lower()
            for x in ("mfa", "verif", "security-code", "totp")
        ):
            print("\nTwo-factor authentication required.")
            mfa_code = input("Enter your verification code: ").strip()

            _MFA_SELECTORS = [
                'input[name="verificationCode"]',
                'input[name="securityCode"]',
                'input[type="tel"]',
                'input[autocomplete="one-time-code"]',
                'input[placeholder*="code"]',
            ]
            filled = False
            for sel in _MFA_SELECTORS:
                try:
                    sb.wait_for_element(sel, timeout=4)
                    sb.type(sel, mfa_code)
                    filled = True
                    break
                except Exception:
                    continue

            if not filled:
                print("ERROR: Could not find MFA input field on the page.", file=sys.stderr)
                return {}

            sb.click('button[type="submit"]')
            sb.sleep(3)

        # ── Wait for successful redirect ───────────────────────────────────
        print("Waiting for Garmin Connect to load…")
        for _ in range(30):
            url = sb.get_current_url()
            if "connect.garmin.com" in url and "sso.garmin.com" not in url:
                break
            sb.sleep(1)
        else:
            print("ERROR: Login timed out — never reached Garmin Connect.", file=sys.stderr)
            return {}

        # ── Extract Garmin-domain cookies ──────────────────────────────────
        cookies = {
            c["name"]: c["value"]
            for c in sb.get_cookies()
            if "garmin" in c.get("domain", "")
        }

        return cookies


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------

def _register_with_server(server_url: str, email: str, cookies: dict) -> str:
    """
    POST cookies to /api/setup/import-token and return the MCP URL.

    Token format matches what GarminApiClient.from_token() expects:
        {"cookies": {name: value, ...}, "display_name": ""}
    """
    token_json = json.dumps({"cookies": cookies, "display_name": ""})
    payload = json.dumps({"email": email, "token": token_json}).encode()

    req = urllib.request.Request(
        f"{server_url}/api/setup/import-token",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    mcp_url = data.get("mcp_url")
    if not mcp_url:
        raise ValueError(f"Unexpected server response: {data}")

    return mcp_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _die(message: str, code: int = 1) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    main()
