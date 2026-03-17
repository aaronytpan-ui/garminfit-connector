#!/usr/bin/env python3
"""
Garmin Chat Connector — Local Setup Script
==========================================
Run this on your own computer to authenticate with Garmin
and register your MCP URL with the Garmin Chat Connector.

Why local?  Garmin's OAuth endpoints can be finicky from cloud servers.
Running locally uses your own machine and IP, which tends to be more reliable.

Usage:
    python local_setup.py
    python local_setup.py --app-url https://your-app.railway.app
    python local_setup.py --debug          (verbose output for troubleshooting)
"""

import argparse
import getpass
import re
import sys
from urllib.parse import parse_qs

APP_URL_DEFAULT = "https://garminfit-connector-production.up.railway.app"


# ---------------------------------------------------------------------------
# Core login helper — handles both MFA and non-MFA accounts.
#
# Garth's default GarminOAuth1Session does NOT copy SSO session cookies when
# it calls the `preauthorized` endpoint.  For MFA accounts, Garmin requires
# those cookies (set by the verifyMFA response) to be present on that request,
# otherwise it returns 401 Unauthorized.  We replicate the flow manually so
# we can inject the cookies at the right moment.
# ---------------------------------------------------------------------------

def _login_with_cookie_carry(client, email: str, password: str, debug: bool = False):
    """Authenticate with Garmin, correctly forwarding SSO cookies for MFA accounts."""

    try:
        import garth.sso as garth_sso
        from garth.auth_tokens import OAuth1Token, OAuth2Token
        from requests_oauthlib import OAuth1Session
        import requests as _req
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}")
        print("Run:  pip install garth requests requests-oauthlib")
        sys.exit(1)

    def dbg(msg):
        if debug:
            print(f"  [debug] {msg}")

    # Step 1 — initiate login; bail out early if MFA is needed
    dbg("Calling garth sso.login(return_on_mfa=True) ...")
    result = garth_sso.login(email, password, client=client, return_on_mfa=True)

    if isinstance(result, tuple) and result[0] == "needs_mfa":
        # ---- MFA path -------------------------------------------------------
        _, client_state = result
        signin_params = client_state["signin_params"]

        print()
        print("🔐  MFA required — check your authenticator app.")
        mfa_code = input("   Enter your 6-digit MFA code: ").strip()
        if not mfa_code:
            print("ERROR: MFA code cannot be empty.")
            sys.exit(1)

        # Step 2 — submit MFA code (uses client.sess which carries all SSO cookies)
        dbg("Submitting MFA code via handle_mfa() ...")
        garth_sso.handle_mfa(client, signin_params, lambda: mfa_code)

        # Diagnostic: confirm we got the Success page
        title_m = re.search(r"<title>(.+?)</title>", client.last_resp.text, re.IGNORECASE)
        page_title = title_m.group(1).strip() if title_m else "unknown"
        dbg(f"verifyMFA response: HTTP {client.last_resp.status_code}  title={page_title!r}")
        dbg(f"SSO cookies after verifyMFA: {[c.name for c in client.sess.cookies]}")

        if "success" not in page_title.lower():
            # Could be "Invalid MFA" or another error page
            body_preview = client.last_resp.text[:600]
            dbg(f"verifyMFA body preview: {body_preview!r}")
            raise Exception(
                f"MFA verification failed — page title was {page_title!r}. "
                "Double-check your code and try again."
            )

        # Step 3 — extract the CAS ticket from the Success page
        m = re.search(r'embed\?ticket=([^"]+)"', client.last_resp.text)
        if not m:
            m = re.search(r"embed\?ticket=([^']+)'", client.last_resp.text)
        if not m:
            dbg(f"Success page body (first 800): {client.last_resp.text[:800]!r}")
            raise Exception("Couldn't find CAS ticket in the Success page response.")
        ticket = m.group(1)
        dbg(f"CAS ticket extracted: {ticket[:50]}...")

        # Step 4 — ensure OAuth consumer credentials are loaded
        if not garth_sso.OAUTH_CONSUMER:
            dbg("Fetching OAuth consumer credentials from S3 ...")
            garth_sso.OAUTH_CONSUMER = _req.get(garth_sso.OAUTH_CONSUMER_URL).json()
        dbg(f"OAuth consumer_key: {garth_sso.OAUTH_CONSUMER.get('consumer_key', '?')[:20]}...")

        # Step 5 — exchange the ticket for an OAuth1 token, WITH SSO cookies
        #
        # This is the critical difference from garth's default GarminOAuth1Session:
        # we copy client.sess.cookies into the OAuth1Session so Garmin can verify
        # the MFA session on the preauthorized endpoint.
        oauth1_sess = OAuth1Session(
            garth_sso.OAUTH_CONSUMER["consumer_key"],
            garth_sso.OAUTH_CONSUMER["consumer_secret"],
        )
        oauth1_sess.cookies.update(client.sess.cookies)         # <-- the fix
        oauth1_sess.mount("https://", client.sess.adapters["https://"])
        oauth1_sess.proxies = client.sess.proxies
        oauth1_sess.verify = client.sess.verify

        preauth_url = (
            f"https://connectapi.{client.domain}/oauth-service/oauth/"
            f"preauthorized?ticket={ticket}"
            f"&login-url=https://sso.{client.domain}/sso/embed"
            f"&accepts-mfa-tokens=true"
        )
        dbg(f"Calling preauthorized endpoint (cookies={len(oauth1_sess.cookies)}) ...")
        resp = oauth1_sess.get(
            preauth_url, headers=garth_sso.USER_AGENT, timeout=client.timeout
        )
        dbg(f"preauthorized response: HTTP {resp.status_code}")
        if not resp.ok:
            dbg(f"preauthorized error body: {resp.text[:400]!r}")
            dbg(f"preauthorized response headers: {dict(resp.headers)}")
        resp.raise_for_status()

        parsed = parse_qs(resp.text)
        token_dict = {k: v[0] for k, v in parsed.items()}
        dbg(f"OAuth1 token keys: {list(token_dict.keys())}")
        oauth1 = OAuth1Token(domain=client.domain, **token_dict)

        # Step 6 — exchange OAuth1 for OAuth2
        dbg("Exchanging OAuth1 → OAuth2 ...")
        oauth2 = garth_sso.exchange(oauth1, client)
        dbg("OAuth2 token obtained.")

        # Store tokens on the client object so client.dumps() works
        client.oauth1_token = oauth1
        client.oauth2_token = oauth2

    else:
        # ---- Non-MFA path ---------------------------------------------------
        # garth already completed the full flow and returned (oauth1, oauth2)
        oauth1, oauth2 = result
        dbg("No MFA required — login completed by garth directly.")
        client.oauth1_token = oauth1
        client.oauth2_token = oauth2


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Local Garmin Chat Connector setup")
    parser.add_argument(
        "--app-url",
        default=APP_URL_DEFAULT,
        help=f"Your Railway app URL (default: {APP_URL_DEFAULT})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print verbose diagnostic output (useful for troubleshooting)",
    )
    args = parser.parse_args()

    # Lazy-import so the script gives a helpful error if deps are missing
    try:
        import garth
    except ImportError:
        print("ERROR: garth is not installed.")
        print("Run:  pip install garth")
        sys.exit(1)
    try:
        import requests as _req
    except ImportError:
        print("ERROR: requests is not installed.")
        print("Run:  pip install requests")
        sys.exit(1)

    print()
    print("Garmin Chat Connector — Local Setup")
    print("=" * 42)
    print("Authenticate with Garmin on this machine,")
    print("then register the token with your app.")
    print()

    email = input("Garmin Connect email: ").strip()
    if not email:
        print("ERROR: email is required.")
        sys.exit(1)
    password = getpass.getpass("Garmin Connect password: ")
    if not password:
        print("ERROR: password is required.")
        sys.exit(1)

    print()
    print("Connecting to Garmin…")

    client = garth.Client()
    try:
        _login_with_cookie_carry(client, email, password, debug=args.debug)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR: Garmin login failed: {exc}")
        if not args.debug:
            print("Tip: re-run with --debug for more detail.")
        sys.exit(1)

    token = client.dumps()
    print("✓ Garmin authentication successful.")
    print()
    print(f"Registering token with {args.app_url} …")

    try:
        resp = _req.post(
            f"{args.app_url}/api/setup/import-token",
            json={"email": email, "token": token},
            timeout=30,
        )
    except Exception as exc:
        print(f"\nERROR: Could not reach app: {exc}")
        sys.exit(1)

    if resp.status_code == 200:
        mcp_url = resp.json().get("mcp_url", "(not returned)")
        print()
        print("✅  Setup complete!")
        print()
        print("Your MCP URL:")
        print()
        print(f"   {mcp_url}")
        print()
        print("Add this URL to Claude (or another AI tool) as an MCP server.")
    else:
        try:
            err = resp.json().get("error", resp.text)
        except Exception:
            err = resp.text
        print(f"\nERROR: App returned {resp.status_code}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
