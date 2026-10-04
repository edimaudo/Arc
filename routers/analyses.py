from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.services.demo_data import ANALYSIS_DATA
from app.services.analysis_service import run_demo_investigation

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.get("/new")
async def new_analysis(request: Request):
    return templates.TemplateResponse("new_analysis.html", {"request": request})

@router.get("/{analysis_id}")
async def analysis_detail(request: Request, analysis_id: str):
    data = ANALYSIS_DATA.copy()
    data["analysis_id"] = analysis_id
    return templates.TemplateResponse("analysis.html", {"request": request, **data})

@router.post("/{analysis_id}/run")
async def run_analysis(analysis_id: str):
    return run_demo_investigation(analysis_id)
