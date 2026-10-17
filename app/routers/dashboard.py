from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from app.services.agent_service import ArcAgent
from app.auth import require_authenticated
from app.services.api_errors import friendly_api_error

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(dependencies=[Depends(require_authenticated)])
_agent = ArcAgent()


@router.get('/dashboard')
async def dashboard(request: Request):
    return TEMPLATES.TemplateResponse(request, 'dashboard.html', {'request': request})


@router.get('/owner')
async def owner_workspace(request: Request):
    return TEMPLATES.TemplateResponse(request, 'owner.html', {'request': request})


@router.get('/analyst')
async def analyst_workspace(request: Request):
    return TEMPLATES.TemplateResponse(request, 'analyst.html', {'request': request})


@router.post('/owner/api/insights')
async def business_insights_api(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    company = str(payload.get('company') or '').strip()
    if not company:
        raise HTTPException(status_code=400, detail='Choose a previously searched company to research.')
    # Industry and operating geography are inferred from public company information,
    # not exposed as separate user-entered filters in Business Insights.
    criteria = {'company': company}
    try:
        result = await _agent.research_business_insights(criteria)
    except Exception as exc:
        return JSONResponse({'error': friendly_api_error(exc, 'Business research service'), 'status': 'Business research failed', 'retryable': True}, status_code=503)
    return {'insights': result.get('insights', {}), 'search_activity': result.get('search_activity', []), 'criteria': criteria}
