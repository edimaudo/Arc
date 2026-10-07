from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import APP_NAME, BASE_DIR
from app.db import init_db
from app.routers import dashboard, analyses, discovery

init_db()
app = FastAPI(title=APP_NAME, version='0.2.0')
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
app.include_router(dashboard.router)
app.include_router(analyses.router)
app.include_router(discovery.router)


@app.get('/', name='landing')
async def landing(request: Request):
    return templates.TemplateResponse('landing.html', {'request': request})


@app.get('/login', name='login')
async def login(request: Request):
    return templates.TemplateResponse('auth.html', {'request': request, 'mode': 'Sign in'})


@app.get('/signup', name='signup')
async def signup(request: Request):
    return templates.TemplateResponse('auth.html', {'request': request, 'mode': 'Create account'})


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
