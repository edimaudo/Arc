from __future__ import annotations

import hmac
import os
from urllib.parse import quote

from fastapi import HTTPException, Request

# Arc is a hackathon demo with one shared, non-confidential user. No user table,
# signup flow, or server-side account database is required.
DEMO_EMAIL = os.getenv('ARC_DEMO_EMAIL', 'demo@arc.app').strip().lower()
DEMO_PASSWORD = os.getenv('ARC_DEMO_PASSWORD', 'ArcDemo2026!')
DEMO_USER_ID = 'arc-demo-user'
DEMO_USER = {
    'user_id': DEMO_USER_ID,
    'email': DEMO_EMAIL,
    'display_name': 'Arc Demo',
}


def safe_next_path(value: str | None) -> str:
    if not value or not value.startswith('/') or value.startswith('//') or '\\' in value:
        return '/dashboard'
    return value


def authenticate_user(email: str, password: str) -> dict | None:
    normalized = email.strip().lower()
    if hmac.compare_digest(normalized.encode('utf-8'), DEMO_EMAIL.encode('utf-8')) and hmac.compare_digest(password.encode('utf-8'), DEMO_PASSWORD.encode('utf-8')):
        return dict(DEMO_USER)
    return None


def set_user_session(request: Request, user: dict) -> None:
    request.session.clear()
    request.session['user_id'] = DEMO_USER_ID
    request.session['email'] = DEMO_EMAIL
    request.session['display_name'] = 'Arc Demo'


def clear_user_session(request: Request) -> None:
    request.session.clear()


def require_authenticated(request: Request) -> dict:
    if request.session.get('user_id') != DEMO_USER_ID:
        next_path = request.url.path
        if request.url.query:
            next_path += '?' + request.url.query
        login_url = '/login?next=' + quote(next_path, safe='/')
        is_api = '/api/' in request.url.path or request.url.path.endswith(('/run', '/ask', '/report.pdf')) or (request.method != 'GET' and request.url.path == '/analysis/start')
        if is_api:
            raise HTTPException(status_code=401, detail={'message': 'Sign in to continue.', 'login_url': login_url})
        raise HTTPException(status_code=303, detail='Sign in to continue.', headers={'Location': login_url})
    request.state.user = dict(DEMO_USER)
    return request.state.user
