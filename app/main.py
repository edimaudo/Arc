from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import APP_NAME, APP_ENV, BASE_DIR, SESSION_SECRET
from app.db import init_db, get_or_create_setting
from app.auth import authenticate_user, clear_user_session, safe_next_path, set_user_session, signup_user
from app.routers import dashboard, analyses, discovery

logger = logging.getLogger(__name__)
init_db()
SESSION_KEY = SESSION_SECRET or get_or_create_setting("session_secret", secrets.token_urlsafe(64))
app = FastAPI(title=APP_NAME, version='0.3.0')
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_KEY,
    session_cookie='arc_session',
    max_age=12 * 60 * 60,
    same_site='lax',
    https_only=APP_ENV in {'production', 'prod'},
)
app.include_router(dashboard.router)
app.include_router(analyses.router)
app.include_router(discovery.router)


@app.get('/', name='landing')
async def landing(request: Request):
    return templates.TemplateResponse(request, 'landing.html', {'request': request})


@app.get('/login', name='login')
async def login_page(request: Request, next: str = '/dashboard'):
    if request.session.get('user_id'):
        return RedirectResponse(safe_next_path(next), status_code=303)
    return templates.TemplateResponse(request, 'auth.html', {
        'request': request, 'mode': 'Sign in', 'next_url': safe_next_path(next), 'error': None,
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
        }, status_code=401)
    set_user_session(request, user)
    return RedirectResponse(safe_next_path(next), status_code=303)


@app.get('/signup', name='signup')
async def signup_page(request: Request, next: str = '/dashboard'):
    if request.session.get('user_id'):
        return RedirectResponse(safe_next_path(next), status_code=303)
    return templates.TemplateResponse(request, 'auth.html', {
        'request': request, 'mode': 'Create account', 'next_url': safe_next_path(next), 'error': None,
    })


@app.post('/signup', name='signup_submit')
async def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(default=''),
    next: str = Form('/dashboard'),
):
    try:
        user = signup_user(email, password, display_name)
    except ValueError as exc:
        return templates.TemplateResponse(request, 'auth.html', {
            'request': request, 'mode': 'Create account', 'next_url': safe_next_path(next),
            'error': str(exc),
        }, status_code=400)
    except Exception:
        logger.exception('Unable to create Arc account')
        return templates.TemplateResponse(request, 'auth.html', {
            'request': request, 'mode': 'Create account', 'next_url': safe_next_path(next),
            'error': 'Arc could not create your account. Check the database configuration and try again.',
        }, status_code=500)
    set_user_session(request, user)
    return RedirectResponse(safe_next_path(next), status_code=303)


@app.post('/logout', name='logout')
async def logout(request: Request):
    clear_user_session(request)
    return RedirectResponse('/', status_code=303)


@app.get('/health')
async def health():
    from app.config import missing_credentials, QLOO_BASE_URL, GEMINI_MODEL
    missing = missing_credentials()
    return {
        'status': 'ok' if not missing else 'configuration_error',
        'gemini_model': GEMINI_MODEL,
        'qloo_base_url': QLOO_BASE_URL,
        'credentials': {
            'gemini': 'configured' if 'GEMINI_API_KEY' not in missing else 'missing',
            'qloo': 'configured' if 'QLOO_API_KEY' not in missing else 'missing',
        },
    }
