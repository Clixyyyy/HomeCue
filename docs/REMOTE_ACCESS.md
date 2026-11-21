# Remote HomeCue access

Remote browser access uses a password-protected gateway with an explicit email allowlist.

The launcher prints a temporary HTTPS address. Replace `YOUR_PUBLIC_HOST` below with that hostname:

- Website: https://YOUR_PUBLIC_HOST/
- App: https://YOUR_PUBLIC_HOST/app/

Enter the approved email and its existing HomeCue password. An email verification code is no longer required. Successful sign-in opens the website or app with the same account, home, and purchases. Signing out clears the remote session.

Only explicit allowed accounts can sign in. The public sign-in form is the sole public entry; app pages, assets, API data and API documentation are behind the signed session. The session cookie is secure, HTTP-only, first-party and valid for two hours. Password changes revoke remote sessions. The gateway binds only to localhost:8001 and wraps the existing app; local/LAN access on port 8000 is unchanged. Caller-supplied bearer tokens cannot bypass remote sign-in or switch the approved account. Invalid sign-in attempts are rate-limited.

## Restart

Run `zsh scripts/START_REMOTE_ACCESS_MAC.command` from the project root and enter the approved email address. It starts the protected gateway and the HTTPS tunnel, then prints a new URL. Keep that terminal and the Mac awake and connected. Ctrl+C stops both child processes. If a gateway is already running, stop its existing launcher first. The launcher never opens a tunnel to the original backend port.

A Flutter browser build must exist in `mobile_flutter/build/web`. Run `zsh scripts/BUILD_APP_MAC.command` if it is missing. If macOS clears the temporary tunnel binary, install cloudflared from https://developers.cloudflare.com/tunnel/downloads/ or set HOMECUE_CLOUDFLARED to its executable.

This remains a temporary tunnel. Its URL changes when restarted, and it stops working if the Mac sleeps or goes offline. Always-on access requires cloud hosting.

## Account recovery

A HomeCue password is different from the previous email verification code. If the email is already registered, use Sign in instead of Create account.

A local administrator can open a 15-minute, one-time recovery page with `backend/.venv/bin/python backend/recover_account.py --email EMAIL_ADDRESS`. It changes no password until the user submits a new one. Homes and purchases stay intact; previous login sessions become invalid. Token issuance is local only. Never share recovery links.

## Verification

`backend/.venv/bin/python -m pytest backend/tests -q` verifies gateway allowlisting, cookies, password-reset revocation, sign-out, account isolation, limits and unauthenticated API rejection. `backend/.venv/bin/python scripts/remote_gateway_smoke_test.py` tests one sign-in opening both Flutter and the website over temporary local HTTPS, with a throwaway account and database. Public-link checks verify that the sign-in form is reachable and private API requests are rejected before login.
