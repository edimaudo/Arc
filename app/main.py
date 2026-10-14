from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import APP_NAME, APP_ENV, BASE_DIR, SESSION_SECRET
from app.auth import authenticate_user, clear_user_session, safe_next_path, set_user_session, DEMO_EMAIL, DEMO_PASSWORD, DEMO_USER_ID

logger = logging.getLogger(__name__)
# A deterministic demo-only fallback prevents sign-in cookies breaking across Vercel
# cold starts. Set ARC_SESSION_SECRET to a random value for a public deployment.
SESSION_KEY = SESSION_SECRET or os.getenv('ARC_SESSION_SECRET', 'arc-demo-session-secret-change-before-public-launch')
if not SESSION_SECRET:
    logger.warning('ARC_SESSION_SECRET is not configured; using the built-in demo-only session secret.')

from app.routers import dashboard, analyses, discovery  # noqa: E402

app = FastAPI(title=APP_NAME, version='0.4.0')
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_KEY,
    session_cookie='arc_session',
    max_age=12 * 60 * 60,
    same_site='lax',
    https_only=APP_ENV in {'production', 'prod'} or bool(os.getenv('VERCEL')),
)
app.include_router(dashboard.router)
app.include_router(analyses.router)
app.include_router(discovery.router)


@app.get('/', name='landing')
async def landing(request: Request):
    return templates.TemplateResponse(request, 'landing.html', {'request': request})


@app.get('/login', name='login')
async def login_page(request: Request, next: str = '/dashboard'):
    if request.session.get('user_id') == DEMO_USER_ID:
        return RedirectResponse(safe_next_path(next), status_code=303)
    return templates.TemplateResponse(request, 'auth.html', {
        'request': request, 'mode': 'Sign in', 'next_url': safe_next_path(next), 'error': None,
        'demo_email': DEMO_EMAIL, 'demo_password': DEMO_PASSWORD,
    })


@app.post('/login', name='login_submit')
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form('/dashboard'),
):
    user = authenticate_user(email, password)
    if not user:
        return templates.TemplateResponse(request, 'auth.html', {
            'request': request, 'mode': 'Sign in', 'next_url': safe_next_path(next),
            'error': 'Email or password is incorrect.',
            'demo_email': DEMO_EMAIL, 'demo_password': DEMO_PASSWORD,
        }, status_code=401)
    set_user_session(request, user)
    return RedirectResponse(safe_next_path(next), status_code=303)


@app.post('/demo-login', name='demo_login')
async def demo_login(request: Request, next: str = Form('/dashboard')):
    user = authenticate_user(DEMO_EMAIL, DEMO_PASSWORD)
    if not user:
        return templates.TemplateResponse(request, 'auth.html', {
            'request': request, 'mode': 'Sign in', 'next_url': safe_next_path(next),
            'error': 'The demo account credentials are not configured correctly.',
            'demo_email': DEMO_EMAIL, 'demo_password': DEMO_PASSWORD,
        }, status_code=503)
    set_user_session(request, user)
    return RedirectResponse(safe_next_path(next), status_code=303)


@app.get('/signup', name='signup')
async def signup_disabled(request: Request):
    # Arc is intentionally a single-user demo; no registration or user database.
    return RedirectResponse('/login', status_code=303)


@app.post('/logout', name='logout')
async def logout(request: Request):
    clear_user_session(request)
    return RedirectResponse('/', status_code=303)


@app.get('/health')
async def health():
    from app.config import missing_credentials, QLOO_BASE_URL, GEMINI_MODEL
    missing = missing_credentials()
    providers = {
        'gemini': 'configured' if 'GEMINI_API_KEY' not in missing else 'missing',
        'qloo': 'configured' if 'QLOO_API_KEY' not in missing else 'missing',
    }
    return {
        'status': 'ok' if not missing else ('degraded' if any(v == 'configured' for v in providers.values()) else 'configuration_error'),
        'storage': 'browser IndexedDB; no server database',
        'gemini_model': GEMINI_MODEL,
        'qloo_base_url': QLOO_BASE_URL,
        'credentials': providers,
        'missing_credentials': missing,
    }
