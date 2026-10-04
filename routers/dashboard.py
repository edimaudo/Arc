from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.services.demo_data import DASHBOARD_DATA, ANALYSIS_DATA

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter()

@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, **DASHBOARD_DATA})

@router.get("/owner")
async def owner_workspace(request: Request):
    return templates.TemplateResponse("owner.html", {"request": request, **DASHBOARD_DATA})

@router.get("/analyst")
async def analyst_workspace(request: Request):
    data = {**DASHBOARD_DATA, **ANALYSIS_DATA}
    return templates.TemplateResponse("analyst.html", {"request": request, **data})
