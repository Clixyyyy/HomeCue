"""Optional remote entry point. Never publish this listener without approval.

Every app page and API requires a signed, email-allowlisted remote session.
The public surface is a password sign-in form. Local HomeCue stays unchanged.
"""
import html
import json
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

import jwt
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from main import app, SessionLocal, User, SECRET, password_version, user_jwt, verify_password

COOKIE = '__Host-homecue_remote'
LOGIN = '/remote-access'
SESSION_SECONDS = 2 * 60 * 60


def safe_next(value):
    if not isinstance(value,str):
        return '/app/'
    if not value or not value.startswith('/') or value.startswith('//') or '\\' in value or any(ord(c) < 32 for c in value):
        return '/app/'
    parts = urlsplit(value)
    return value if not parts.scheme and not parts.netloc else '/app/'


def public_user(user):
    return {'id': user.id, 'name': user.name, 'email': user.email}


class RemoteGateway:
    def __init__(self, origin, allowed_emails):
        self.origin = origin
        self.allowed = frozenset(e.strip().lower() for e in allowed_emails if e.strip())
        if not self.allowed or any('*' in e or '@' not in e for e in self.allowed):
            raise ValueError('Explicit allowed email addresses are required')
        self.failures = defaultdict(deque)

    def session_user(self, encoded):
        if not encoded:
            return None
        try:
            claims = jwt.decode(encoded, SECRET, algorithms=['HS256'],options={'require':['exp','sub','purpose','pv']})
            if claims.get('purpose') != 'remote_access':
                return None
            with SessionLocal() as db:
                user = db.get(User, int(claims['sub']))
                if not user or user.email not in self.allowed:
                    return None
                import hmac
                if not hmac.compare_digest(str(claims.get('pv', '')), password_version(user)):
                    return None
                return user
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            return None

    def check_password(self, email, password):
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            if not user or user.email not in self.allowed or not verify_password(password, user.password_hash):
                return None
            return user

    def login_page(self, destination):
        nonce = secrets.token_urlsafe(20)
        target = html.escape(safe_next(destination), quote=True)
        document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HomeCue remote sign-in</title><style>body{font:16px system-ui;background:#f7f7f7;color:#111;margin:0;padding:24px}main{max-width:430px;margin:8vh auto;background:white;border:1px solid #ddd;border-radius:24px;padding:28px}h1{font-size:30px}p{color:#555;line-height:1.5}label{display:grid;gap:7px;margin-top:18px;font-weight:600}input,button{font:inherit;padding:14px;border:1px solid #ccc;border-radius:12px}button{background:#111;color:#fff;width:100%;margin-top:22px;font-weight:700}button:disabled{opacity:.6}#error{color:#a21;min-height:24px}</style></head><body><main><strong>homecue.</strong><h1>Sign in to your home.</h1><p>Use your approved email and your HomeCue password. Your password is separate from the previous email verification code.</p><form id="login"><input type="hidden" name="next" value="TARGET"><label>Email<input type="email" name="email" autocomplete="username" required maxlength="180"></label><label>HomeCue password<input type="password" name="password" autocomplete="current-password" required maxlength="200"></label><p id="error" role="alert"></p><button>Sign in</button></form><p>Only the approved account can access this remote link. If you forgot your password, reset it on your Mac first.</p></main><script nonce="NONCE">const form=document.querySelector('#login');form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;document.querySelector('#error').textContent='';try{const data=Object.fromEntries(new FormData(form));const response=await fetch('/remote-access/sign-in',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.detail||'Could not sign in.');location.assign(result.next);}catch(error){document.querySelector('#error').textContent=error.message;button.disabled=false;}});</script></body></html>'''.replace('TARGET', target).replace('NONCE', nonce)
        return HTMLResponse(document, headers={'Content-Security-Policy': f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.origin(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type':'websocket.close','code':1008})
        if scope['type'] != 'http':
            return
        request = Request(scope, receive)
        path = scope['path']
        user = await run_in_threadpool(self.session_user, request.cookies.get(COOKIE))
        response = None
        if path == LOGIN and request.method in ('GET', 'HEAD'):
            destination = safe_next(request.query_params.get('next'))
            response = RedirectResponse(destination, status_code=303) if user else self.login_page(destination)
        elif path == LOGIN + '/sign-in' and request.method == 'POST':
            # JSON-only plus an explicit same-origin check prevents cross-site form submissions.
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc != request.headers.get('host'):
                response = JSONResponse({'detail': 'Open sign-in on this HomeCue link.'}, 403)
            elif not request.headers.get('content-type', '').startswith('application/json'):
                response = JSONResponse({'detail': 'JSON sign-in required.'}, 415)
            else:
                identity = request.headers.get('cf-connecting-ip') or (request.client.host if request.client else 'local')
                now = time.monotonic()
                failures = self.failures[identity]
                while failures and failures[0] < now - 60:
                    failures.popleft()
                if len(failures) >= 8:
                    response = JSONResponse({'detail': 'Too many attempts. Wait one minute and try again.'}, 429)
                else:
                    try:
                        raw = b''
                        async for chunk in request.stream():
                            if len(raw)+len(chunk)>8192:
                                raise ValueError()
                            raw += chunk
                        data = json.loads(raw)
                        email, password = data.get('email'), data.get('password')
                        if not isinstance(email, str) or not isinstance(password, str) or len(email) > 180 or len(password) > 200:
                            raise ValueError()
                        signed_in = await run_in_threadpool(self.check_password, email.strip().lower(), password)
                        if not signed_in:
                            failures.append(now)
                            response = JSONResponse({'detail': 'Incorrect email/password, or this account is not approved for remote access.'}, 401)
                        else:
                            failures.clear()
                            encoded = jwt.encode({'sub': str(signed_in.id), 'purpose': 'remote_access', 'pv': password_version(signed_in), 'exp': datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS)}, SECRET, algorithm='HS256')
                            response = JSONResponse({'next': safe_next(data.get('next'))})
                            response.set_cookie(COOKIE, encoded, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite='lax', path='/')
                    except (ValueError, TypeError, AttributeError):
                        response = JSONResponse({'detail': 'Enter your email and HomeCue password.'}, 400)
        elif path == '/api/remote-sign-out' and request.method == 'POST':
            origin=request.headers.get('origin')
            if origin and urlsplit(origin).netloc!=request.headers.get('host'):
                response=JSONResponse({'detail':'Use sign out on this HomeCue link.'},403)
            else:
                response = JSONResponse({'remote': True, 'sign_in_url': LOGIN + '?next=/app/'})
                response.delete_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='lax')
        elif not user:
            response = JSONResponse({'detail': 'Remote access expired. Sign in again.'}, 401) if path.startswith('/api/') or request.method not in ('GET', 'HEAD') else RedirectResponse(LOGIN + '?next=' + quote(safe_next(path + ('?' + request.url.query if request.url.query else '')), safe=''), status_code=303)
        elif path == '/api/remote-session' and request.method == 'GET':
            response = JSONResponse({'token': user_jwt(user), 'user': public_user(user)})
        elif path.startswith('/api/auth/'):
            response = JSONResponse({'detail': 'Use the remote sign-in page for this approved account.'}, 403)
        if response is not None:
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return await response(scope, receive, send)
        # The remote identity, rather than a caller-supplied bearer, selects the account.
        headers = [(key, value) for key, value in scope['headers'] if key.lower() != b'authorization']
        headers.append((b'authorization', ('Bearer ' + user_jwt(user)).encode()))
        return await self.origin({**scope, 'headers': headers}, receive, send)


def create_app():
    allowed = os.environ.get('HOMECUE_REMOTE_EMAIL', '').split(',')
    return RemoteGateway(app, allowed)
