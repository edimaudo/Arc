from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import MAX_DOCUMENT_BYTES, MAX_DOCUMENTS_PER_ANALYSIS
from app.services.analysis_service import create_analysis, get_analysis, run_investigation
from app.services.agent_service import ArcAgent
from app.services.document_service import parse_document
from app.services.report_service import build_report_pdf

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(prefix='/analysis', tags=['analysis'])
_agent = ArcAgent()


@router.get('/new')
async def new_analysis(request: Request):
    return TEMPLATES.TemplateResponse(request, 'new_analysis.html', {'request': request, 'acquirer_default': request.query_params.get('acquirer', ''), 'target_default': request.query_params.get('target', '')})


@router.post('/start')
async def start_analysis(
    acquirer: str = Form(...), target: str = Form(...), objective: str = Form(...),
    scopes: list[str] = Form(default=[]), evidence: list[UploadFile] = File(default=[]),
):
    acquirer, target, objective = acquirer.strip(), target.strip(), objective.strip()
    if not acquirer or not target:
        return JSONResponse({'error': 'Acquirer and target are required.'}, status_code=400)
    analysis_id = create_analysis(acquirer, target, objective, scopes or ['financial', 'business', 'cultural', 'integration'])
    analysis = get_analysis(analysis_id)
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
    save_analysis(analysis)
    return RedirectResponse(f'/analysis/{analysis_id}', status_code=303)


@router.get('/{analysis_id}')
async def analysis_detail(request: Request, analysis_id: str):
    try:
        data = get_analysis(analysis_id)
    except KeyError:
        return TEMPLATES.TemplateResponse(request, 'analysis.html', {'request': request, 'error_page': 'Analysis not found.'}, status_code=404)
    return TEMPLATES.TemplateResponse(request, 'analysis.html', {'request': request, **data})


@router.post('/{analysis_id}/run')
async def run_analysis(analysis_id: str):
    try:
        result = await run_investigation(analysis_id)
        return {'analysis_id': analysis_id, 'status': result.get('status'), 'activity': result.get('activity', []), 'overview': result.get('overview', {})}
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
    except Exception as exc:
        return JSONResponse({'error': str(exc), 'status': 'Investigation failed'}, status_code=502)


@router.post('/{analysis_id}/ask')
async def ask_arc(analysis_id: str, question: str = Form(...)):
    try:
        analysis = get_analysis(analysis_id)
        answer = await _agent.ask(question.strip(), analysis)
        return {'answer': answer}
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
    except Exception as exc:
        return JSONResponse({'error': str(exc)}, status_code=502)


@router.get('/{analysis_id}/report.pdf')
async def report_pdf(analysis_id: str):
    try:
        analysis = get_analysis(analysis_id)
        content = build_report_pdf(analysis)
        safe = f"arc-{analysis['acquirer'].replace(' ', '-')}-{analysis['target'].replace(' ', '-')}-brief.pdf"[:180]
        return Response(content, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{safe}"'})
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
    except Exception as exc:
        return JSONResponse({'error': str(exc)}, status_code=500)

@router.get('/{analysis_id}/api')
async def analysis_api(analysis_id: str):
    try:
        return get_analysis(analysis_id)
    except KeyError:
        return JSONResponse({'error': 'Analysis not found'}, status_code=404)
