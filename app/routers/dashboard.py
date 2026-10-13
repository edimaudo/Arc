from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.auth import require_authenticated

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(dependencies=[Depends(require_authenticated)])


@router.get('/dashboard')
async def dashboard(request: Request):
    return TEMPLATES.TemplateResponse(request, 'dashboard.html', {'request': request})


@router.get('/owner')
async def owner_workspace(request: Request):
    return TEMPLATES.TemplateResponse(request, 'owner.html', {'request': request})


@router.get('/analyst')
async def analyst_workspace(request: Request):
    return TEMPLATES.TemplateResponse(request, 'analyst.html', {'request': request})
