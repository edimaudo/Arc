from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.services.discovery_service import get_demo_candidates, explain_score

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
router = APIRouter(prefix="/discovery", tags=["discovery"])

@router.get("")
async def discovery_page(request: Request):
    candidates = get_demo_candidates()
    for c in candidates:
        c["score_detail"] = explain_score(c)
    return templates.TemplateResponse("discovery.html", {"request": request, "candidates": candidates})

@router.get("/api/candidates")
async def discovery_api():
    candidates = get_demo_candidates()
    return {"candidates": [{**c, "score_detail": explain_score(c)} for c in candidates]}
