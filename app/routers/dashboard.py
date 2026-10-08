from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.services.analysis_service import get_latest_analysis, list_analyses

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter()


def _dashboard_snapshot() -> dict:
    analyses = list_analyses()
    return {
        "investigations": [
            {
                "analysis_id": a["analysis_id"],
                "acquirer": a["acquirer"],
                "target": a["target"],
                "status": a["status"],
                "fit": a.get("overview", {}).get("strategic_fit") or "—",
            }
            for a in analyses
        ],
        "latest": get_latest_analysis(),
    }


@router.get("/dashboard")
async def dashboard(request: Request):
    return TEMPLATES.TemplateResponse("dashboard.html", {"request": request, **_dashboard_snapshot()})


@router.get("/business")
async def business_workspace(request: Request):
    latest = get_latest_analysis()
    snapshot = {
        "company": latest["acquirer"] if latest else "No acquisition selected",
        "strategic_fit": latest.get("overview", {}).get("strategic_fit", 0) if latest else 0,
        "cultural_alignment": latest.get("overview", {}).get("cultural_alignment", 0) if latest else 0,
        "audience_expansion": latest.get("overview", {}).get("audience_expansion", 0) if latest else 0,
        "financial_fit": latest.get("overview", {}).get("financial_fit", 0) if latest else 0,
        "integration_risk": latest.get("overview", {}).get("integration_risk", "Pending") if latest else "Pending",
        "target": latest["target"] if latest else None,
    }
    return TEMPLATES.TemplateResponse("owner.html", {"request": request, "business_snapshot": snapshot, "latest": latest})


@router.get("/owner")
async def owner_compatibility():
    return RedirectResponse("/business", status_code=307)


@router.get("/analyst")
async def analyst_workspace(request: Request):
    latest = get_latest_analysis()
    if not latest:
        return TEMPLATES.TemplateResponse("analyst.html", {"request": request, "analysis": None})
    return TEMPLATES.TemplateResponse("analyst.html", {"request": request, "analysis": latest})
