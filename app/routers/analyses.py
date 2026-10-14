from pathlib import Path
import logging

from fastapi import APIRouter, Form, Request, Depends
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import MAX_DOCUMENT_BYTES, MAX_DOCUMENTS_PER_ANALYSIS
from app.services.analysis_service import create_analysis, run_investigation
from app.services.document_service import parse_document
from app.services.report_service import build_report_pdf
from app.services.api_errors import friendly_api_error
from app.auth import require_authenticated

logger = logging.getLogger(__name__)
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(prefix='/analysis', tags=['analysis'], dependencies=[Depends(require_authenticated)])


@router.get('/new')
async def new_analysis(request: Request):
    return TEMPLATES.TemplateResponse(request, 'new_analysis.html', {
        'request': request,
        'acquirer_default': request.query_params.get('acquirer', ''),
        'target_default': request.query_params.get('target', ''),
    })


@router.post('/start')
async def start_analysis(
    request: Request,
    acquirer: str = Form(...),
    target: str = Form(...),
    objective: str = Form(...),
    scopes: list[str] = Form(default=[]),
):
    acquirer, target, objective = acquirer.strip(), target.strip(), objective.strip()
    if not acquirer or not target:
        return JSONResponse({'error': 'Acquirer and target are required.'}, status_code=400)

    analysis = create_analysis(
        acquirer, target, objective,
        scopes or ['financial', 'business', 'cultural', 'integration'],
        owner_id=request.state.user['user_id'],
    )
    errors = []
    form = await request.form()
    # Browsers may submit a blank string (not an UploadFile) for an untouched file picker.
    # Filter form values manually so the empty field cannot fail FastAPI's UploadFile validation.
    uploads = [item for item in form.getlist('evidence') if getattr(item, 'filename', None)]
    for upload in uploads[:MAX_DOCUMENTS_PER_ANALYSIS]:
        filename = str(upload.filename).strip()
        raw = await upload.read()
        if not raw:
            await upload.close()
            continue
        if len(raw) > MAX_DOCUMENT_BYTES:
            errors.append(f'{filename}: file exceeds the {MAX_DOCUMENT_BYTES // 1000000} MB limit.')
            continue
        try:
            parsed = parse_document(filename, raw)
            analysis['documents'].append({
                'filename': parsed.get('filename'), 'type': parsed.get('type'),
                'text': parsed.get('text', '')[:16000], 'metrics': parsed.get('metrics', {}),
            })
        except Exception as exc:
            errors.append(f'{filename}: {exc}')
    analysis['upload_errors'] = errors
    return {'analysis': analysis}


@router.get('/{analysis_id}')
async def analysis_detail(request: Request, analysis_id: str):
    # Analysis content is loaded by the browser from IndexedDB. The server does not
    # need to know which browser-local records exist, including after cold starts.
    return TEMPLATES.TemplateResponse(request, 'analysis.html', {'request': request, 'analysis_id': analysis_id})


@router.post('/{analysis_id}/run')
async def run_analysis(request: Request, analysis_id: str):
    try:
        payload = await request.json()
        analysis = payload.get('analysis') if isinstance(payload, dict) else None
        if not isinstance(analysis, dict) or analysis.get('analysis_id') != analysis_id:
            return JSONResponse({'error': 'The saved analysis was not provided. Reopen it from this browser and try again.'}, status_code=400)
        result = await run_investigation(analysis)
        return {'analysis': result}
    except ValueError as exc:
        return JSONResponse({'error': str(exc), 'status': 'Investigation failed'}, status_code=400)
    except Exception as exc:
        logger.exception('Arc investigation failed')
        return JSONResponse({'error': friendly_api_error(exc, 'Live research service'), 'status': 'Investigation failed', 'retryable': True}, status_code=503)


@router.post('/{analysis_id}/report.pdf')
async def report_pdf(request: Request, analysis_id: str):
    try:
        payload = await request.json()
        analysis = payload.get('analysis') if isinstance(payload, dict) else None
        if not isinstance(analysis, dict) or analysis.get('analysis_id') != analysis_id:
            return JSONResponse({'error': 'The saved analysis was not provided.'}, status_code=400)
        content = build_report_pdf(analysis)
        safe = f"arc-{analysis.get('acquirer', 'acquirer').replace(' ', '-')}-{analysis.get('target', 'target').replace(' ', '-')}-brief.pdf"[:180]
        return Response(content, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{safe}"'})
    except Exception as exc:
        logger.exception('Report export failed')
        return JSONResponse({'error': str(exc)}, status_code=500)
