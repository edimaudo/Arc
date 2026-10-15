from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from app.services.agent_service import ArcAgent
from app.auth import require_authenticated
from app.services.api_errors import friendly_api_error

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(prefix='/discovery', tags=['discovery'], dependencies=[Depends(require_authenticated)])
_agent = ArcAgent()


@router.get('')
async def discovery_page(request: Request):
    return TEMPLATES.TemplateResponse(request, 'discovery.html', {'request': request})


@router.post('/api/comparables')
async def comparable_companies_api(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    sector = str(payload.get('sector') or '').strip()
    reference_company = str(payload.get('reference_company') or '').strip()
    if not reference_company:
        raise HTTPException(status_code=400, detail='Choose a reference company before searching.')
    criteria = {
        'reference_company': reference_company,
        'sector': sector,
        'geography': str(payload.get('geography') or 'Canada').strip() or 'Canada',
        'size_metric': 'all',
        'size_band': 'All available scale indicators',
    }
    try:
        result = await _agent.find_comparable_companies(criteria)
    except Exception as exc:
        return JSONResponse({'error': friendly_api_error(exc, 'Discovery service'), 'status': 'Discovery failed', 'retryable': True}, status_code=503)
    return {
        'comparables': result.get('comparables', [])[:5],
        'search_activity': result.get('search_activity', []),
        'criteria': criteria,
    }
