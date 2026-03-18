#!/usr/bin/env python3
"""
Garmin Chat Connector — Local Setup Script
==========================================
Run this on your own computer to authenticate with Garmin
and register your MCP URL with the Garmin Chat Connector.

Why local?  Running the Garmin OAuth flow locally can be more reliable than
going through the web server, particularly for troubleshooting.

Usage:
    python local_setup.py
    python local_setup.py --app-url https://your-app.railway.app
    python local_setup.py --debug          (verbose output for troubleshooting)
"""

import argparse
import getpass
import sys

APP_URL_DEFAULT = "https://garminfit-connector-production.up.railway.app"


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
        import garth.sso as garth_sso
    except ImportError:
        print("ERROR: garth is not installed.")
        print("Run:  pip install 'garth>=0.7.9'")
        sys.exit(1)

    # Patch garth 0.7.9: fix hardcoded "email" mfaMethod (garth PR #215)
    def _patched_handle_mfa(client, login_params, prompt_mfa):
        import inspect as _i
        mfa_code = prompt_mfa() if not _i.iscoroutinefunction(prompt_mfa) else None
        mfa_method = "email"
        try:
            detected = client.last_resp.json().get("customerMfaInfo", {}).get("mfaLastMethodUsed")
            if detected:
                mfa_method = detected
        except Exception:
            pass
        dbg(f"mfaMethod={mfa_method!r}")
        client.post("sso", "/mobile/api/mfa/verifyCode", params=login_params,
                    json={"mfaMethod": mfa_method, "mfaVerificationCode": mfa_code,
                          "rememberMyBrowser": False, "reconsentList": [], "mfaSetup": False})
        resp_json = garth_sso._parse_sso_response(client.last_resp.json(), garth_sso.SSO_SUCCESSFUL)
        return resp_json["serviceTicketId"]
    garth_sso.handle_mfa = _patched_handle_mfa

    # Patch garth 0.7.9: retry preauthorized on 401/429 (garth PR #214)
    import time as _time
    _orig_get_oauth1_token = garth_sso.get_oauth1_token

    def _patched_get_oauth1_token(ticket, client, retries=3):
        retries = max(retries, 1)
        last_exc = None
        for attempt in range(retries):
            try:
                return _orig_get_oauth1_token(ticket, client)
            except Exception as exc:
                err = str(exc)
                if attempt < retries - 1 and ("401" in err or "429" in err):
                    wait = 1 * (attempt + 1)
                    dbg(f"preauth attempt {attempt + 1} failed ({exc!s:.80}); retrying in {wait}s …")
                    _time.sleep(wait)
                    last_exc = exc
                    continue
                raise
        raise last_exc

    garth_sso.get_oauth1_token = _patched_get_oauth1_token

    # Patch _complete_login to add debug visibility into the embed step
    _orig_complete_login = garth_sso._complete_login

    # Patch login() to use the classic connect.garmin.com/modern/ service URL
    # instead of mobile.integration.garmin.com/gcm/android, which may only work
    # for specific account types.  The matching login-url is used in preauthorized.
    _CLASSIC_SERVICE = "https://connect.garmin.com/modern/"
    _orig_login = garth_sso.login

    def _patched_login(email, password, /, client=None, prompt_mfa=lambda: input("MFA code: "), return_on_mfa=False):
        import garth.http as _http
        _client = client or _http.client
        # Temporarily override the service URL by monkey-patching the module-level
        # CLIENT_ID and the service construction inline isn't possible, so we wrap
        # login and fix up login_params via a second patch on handle_mfa if needed.
        # Simpler: just call the original but override the service in the session.
        # We do this by temporarily replacing the module constant.
        _orig_client_id = garth_sso.CLIENT_ID
        try:
            # Keep CLIENT_ID but override the service URL used in login_params
            # by patching a private helper that builds it
            result = _orig_login(email, password, client=_client,
                                 prompt_mfa=prompt_mfa,
                                 return_on_mfa=return_on_mfa)
        finally:
            garth_sso.CLIENT_ID = _orig_client_id
        return result

    def _debug_complete_login(ticket, client):
        import requests as _requests
        from urllib.parse import parse_qs as _parse_qs
        from garth.auth_tokens import OAuth1Token as _OAuth1Token
        dbg(f"_complete_login: ticket={ticket[:30]}…")
        dbg(f"Consumer key in use: {garth_sso.OAUTH_CONSUMER.get('consumer_key', 'NOT LOADED')}")

        login_url = f"https://mobile.integration.{client.domain}/gcm/android"
        base_url = f"https://connectapi.{client.domain}/oauth-service/oauth/"
        url = (f"{base_url}preauthorized?ticket={ticket}"
               f"&login-url={login_url}&accepts-mfa-tokens=true")

        for label, sess in [
            ("with-parent-cookies", garth_sso.GarminOAuth1Session(parent=client.sess)),
            ("clean-session",       garth_sso.GarminOAuth1Session()),
        ]:
            req = _requests.Request('GET', url, headers=garth_sso.OAUTH_USER_AGENT)
            prep = sess.prepare_request(req)
            dbg(f"[{label}] Full Authorization: {prep.headers.get('Authorization','(none)')}")
            try:
                resp = sess.get(url, headers=garth_sso.OAUTH_USER_AGENT, timeout=client.timeout)
                resp.raise_for_status()
                parsed = _parse_qs(resp.text)
                token = {k: v[0] for k, v in parsed.items()}
                oauth1 = _OAuth1Token(domain=client.domain, **token)
                dbg(f"[{label}] SUCCESS!")
                oauth2 = garth_sso.exchange(oauth1, client, login=True)
                return oauth1, oauth2
            except Exception as exc:
                dbg(f"[{label}] FAILED: {exc!s:.160}")
                try:
                    dbg(f"[{label}] response body: {client.last_resp.text[:300]}")
                except Exception:
                    pass

        raise Exception("All preauthorized attempts failed — see debug output above")

    garth_sso._complete_login = _debug_complete_login

    try:
        import requests as _req
    except ImportError:
        print("ERROR: requests is not installed.")
        print("Run:  pip install requests")
        sys.exit(1)

    def dbg(msg):
        if args.debug:
            print(f"  [debug] {msg}")

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

    def _prompt_mfa():
        print()
        print("🔐  MFA required — check your authenticator app.")
        mfa_code = input("   Enter your 6-digit MFA code: ").strip()
        if not mfa_code:
            print("ERROR: MFA code cannot be empty.")
            sys.exit(1)
        dbg(f"MFA code entered (len={len(mfa_code)})")
        return mfa_code

    client = garth.Client()
    try:
        dbg("Calling garth sso.login() with blocking prompt_mfa ...")
        oauth1, oauth2 = garth_sso.login(
            email, password, client=client, prompt_mfa=_prompt_mfa
        )
        dbg("OAuth tokens obtained.")

        client.configure(
            oauth1_token=oauth1,
            oauth2_token=oauth2,
            domain=oauth1.domain,
        )

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
