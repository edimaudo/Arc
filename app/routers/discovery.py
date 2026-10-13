from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from app.services.agent_service import ArcAgent
from app.auth import require_authenticated

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
    if not sector:
        raise HTTPException(status_code=400, detail='Industry or sector is required.')
    criteria = {
        'reference_company': str(payload.get('reference_company') or '').strip(),
        'sector': sector,
        'geography': str(payload.get('geography') or 'Canada').strip() or 'Canada',
        'size_metric': str(payload.get('size_metric') or 'revenue').strip(),
        'size_band': str(payload.get('size_band') or 'Any size').strip(),
    }
    allowed_metrics = {'revenue', 'valuation', 'employees'}
    if criteria['size_metric'] not in allowed_metrics:
        criteria['size_metric'] = 'revenue'
    try:
        result = await _agent.find_comparable_companies(criteria)
    except Exception as exc:
        return JSONResponse({'error': str(exc), 'status': 'Discovery failed'}, status_code=502)
    return {
        'comparables': result.get('comparables', [])[:10],
        'search_activity': result.get('search_activity', []),
        'criteria': criteria,
    }
