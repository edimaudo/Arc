from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from app.services.agent_service import ArcAgent
from app.services.discovery_service import explain_score

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(prefix='/discovery', tags=['discovery'])
_agent = ArcAgent()


@router.get('')
async def discovery_page(request: Request):
    return TEMPLATES.TemplateResponse(request, 'discovery.html', {'request': request})


@router.get('/api/candidates')
async def discovery_api(acquirer: str, sector: str, geography: str = 'Canada', thesis: str = ''):
    if not acquirer.strip() or not sector.strip():
        raise HTTPException(status_code=400, detail='Acquirer and sector are required.')
    try:
        result = await _agent.find_potential_targets({'acquirer': acquirer.strip(), 'sector': sector.strip(), 'geography': geography.strip(), 'thesis': thesis.strip()})
    except Exception as exc:
        return JSONResponse({'error': str(exc), 'status': 'Discovery failed'}, status_code=502)
    candidates = result.get('candidates', [])[:8]
    screened: list[dict] = []
    for candidate in candidates:
        try:
            scored = await _agent.screen_target(acquirer.strip(), candidate, thesis.strip())
            screened.append({**scored, **explain_score(scored)})
        except Exception as exc:
            screened.append({**candidate, 'overall_fit': None, 'components': {}, 'score_detail': None, 'screening_error': str(exc)})
    screened.sort(key=lambda c: (c.get('overall_fit') is not None, c.get('overall_fit') or -1), reverse=True)
    return {'candidates': screened, 'search_activity': result.get('search_activity', [])}
