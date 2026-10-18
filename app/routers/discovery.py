from pathlib import Path
import logging
import re
import secrets


from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from app.services.agent_service import ArcAgent
from app.auth import require_authenticated
from app.services.api_errors import error_payload
from app.config import GEMINI_MODEL

logger = logging.getLogger(__name__)

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
    # Correlate the friendly message with server-side logs without exposing provider
    # response bodies or credentials to the browser. Accept only a short safe ID.
    requested_id = str(request.headers.get('x-arc-request-id') or '').strip()
    reference_id = requested_id if re.fullmatch(r'[A-Za-z0-9_-]{6,64}', requested_id) else f'DISC-{secrets.token_hex(4).upper()}'
    try:
        result = await _agent.find_comparable_companies(criteria)
    except Exception as exc:
        from app.services.api_errors import classify_api_error
        error_code, _ = classify_api_error(exc)
        # The exception/traceback is server-side only. Do not log API keys or company
        # details; the reference and model let an operator locate the failure.
        logger.exception('Discovery request failed reference_id=%s category=%s model=%s', reference_id, error_code, GEMINI_MODEL)
        body = error_payload(exc, 'Discovery service', reference_id)
        body.update({'status': 'Discovery failed'})
        return JSONResponse(body, status_code=503)
    return {
        'comparables': result.get('comparables', [])[:5],
        'search_activity': result.get('search_activity', []),
        'criteria': criteria,
    }
