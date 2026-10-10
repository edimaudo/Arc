from pathlib import Path
import logging

from fastapi import APIRouter, File, Form, Request, UploadFile, Depends
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import MAX_DOCUMENT_BYTES, MAX_DOCUMENTS_PER_ANALYSIS
from app.services.analysis_service import create_analysis, get_analysis, run_investigation
from app.services.agent_service import ArcAgent
from app.services.document_service import parse_document
from app.services.report_service import build_report_pdf
from app.auth import require_authenticated

logger = logging.getLogger(__name__)
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(prefix='/analysis', tags=['analysis'], dependencies=[Depends(require_authenticated)])
_agent = ArcAgent()


@router.get('/new')
async def new_analysis(request: Request):
    return TEMPLATES.TemplateResponse(request, 'new_analysis.html', {'request': request, 'acquirer_default': request.query_params.get('acquirer', ''), 'target_default': request.query_params.get('target', '')})


@router.post('/start')
async def start_analysis(
    request: Request, acquirer: str = Form(...), target: str = Form(...), objective: str = Form(...),
    scopes: list[str] = Form(default=[]), evidence: list[UploadFile] = File(default=[]),
):
    acquirer, target, objective = acquirer.strip(), target.strip(), objective.strip()
    if not acquirer or not target:
        return JSONResponse({'error': 'Acquirer and target are required.'}, status_code=400)
    try:
        analysis_id = create_analysis(acquirer, target, objective, scopes or ['financial', 'business', 'cultural', 'integration'], owner_id=request.state.user['user_id'])
        analysis = get_analysis(analysis_id, owner_id=request.state.user['user_id'])
    except Exception:
        logger.exception('Unable to create acquisition analysis')
        return TEMPLATES.TemplateResponse(
            request, 'new_analysis.html',
            {'request': request, 'acquirer_default': acquirer, 'target_default': target,
             'form_error': 'Arc could not save this analysis. Check database permissions and configuration, then try again.'},
            status_code=500,
        )
    errors = []
    for upload in evidence[:MAX_DOCUMENTS_PER_ANALYSIS]:
        filename = upload.filename or 'document'
        raw = await upload.read()
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
    from app.db import save_analysis
    try:
        save_analysis(analysis)
    except Exception:
        logger.exception('Unable to persist acquisition analysis after document ingestion')
        return TEMPLATES.TemplateResponse(
            request, 'new_analysis.html',
            {'request': request, 'acquirer_default': acquirer, 'target_default': target,
             'form_error': 'Arc could not save the analysis materials. Check database permissions and available storage, then try again.'},
            status_code=500,
        )
    return RedirectResponse(f'/analysis/{analysis_id}', status_code=303)


@router.get('/{analysis_id}')
async def analysis_detail(request: Request, analysis_id: str):
    try:
        data = get_analysis(analysis_id, owner_id=request.state.user['user_id'])
    except KeyError:
        return TEMPLATES.TemplateResponse(request, 'analysis.html', {'request': request, 'error_page': 'Analysis not found.'}, status_code=404)
    return TEMPLATES.TemplateResponse(request, 'analysis.html', {'request': request, **data})


@router.post('/{analysis_id}/run')
async def run_analysis(request: Request, analysis_id: str):
    try:
        result = await run_investigation(analysis_id, owner_id=request.state.user['user_id'])
        return {'analysis_id': analysis_id, 'status': result.get('status'), 'activity': result.get('activity', []), 'overview': result.get('overview', {})}
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
    except Exception as exc:
        return JSONResponse({'error': str(exc), 'status': 'Investigation failed'}, status_code=502)


@router.post('/{analysis_id}/ask')
async def ask_arc(request: Request, analysis_id: str, question: str = Form(...)):
    try:
        analysis = get_analysis(analysis_id, owner_id=request.state.user['user_id'])
        answer = await _agent.ask(question.strip(), analysis)
        return {'answer': answer}
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
    except Exception as exc:
        return JSONResponse({'error': str(exc)}, status_code=502)


@router.get('/{analysis_id}/report.pdf')
async def report_pdf(request: Request, analysis_id: str):
    try:
        analysis = get_analysis(analysis_id, owner_id=request.state.user['user_id'])
        content = build_report_pdf(analysis)
        safe = f"arc-{analysis['acquirer'].replace(' ', '-')}-{analysis['target'].replace(' ', '-')}-brief.pdf"[:180]
        return Response(content, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{safe}"'})
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
    except Exception as exc:
        return JSONResponse({'error': str(exc)}, status_code=500)

@router.get('/{analysis_id}/api')
async def analysis_api(request: Request, analysis_id: str):
    try:
        return get_analysis(analysis_id, owner_id=request.state.user['user_id'])
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
