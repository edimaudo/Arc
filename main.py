from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.routers import dashboard, analyses, discovery

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")

app = FastAPI(title="Arc", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(dashboard.router)
app.include_router(analyses.router)
app.include_router(discovery.router)

@app.get("/", name="landing")
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/login", name="login")
async def login(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request, "mode": "Sign in"})

@app.get("/signup", name="signup")
async def signup(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request, "mode": "Create account"})
