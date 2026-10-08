# Arc — M&A Cultural & Business Intelligence

Arc is a tool for M&A analysts and business owners. It combines business insights with Qloo cultural intelligence and an AI analyst layer.
It looks at M&A information through these lenses

- Analyst: investigation controls, evidence, findings, source/evidence drill-down, agent activity.
- Business  workspace: executive overview, risk/synergy summary, potential company targets and fit scores.
- Company discovery: candidate companies ranked on Strategic Fit, Cultural Fit, Audience Expansion, Financial Fit, Risk, and Overall Fit.

## Architecture
- Backend: FastAPI
- Frontend: Jinja2 + vanilla JavaScript + CSS
- Cultural intelligence: Qloo APIs (`/search`, `/v2/insights`, analysis/compare, trends)
- AI: Gemini Flash
~~- Storage for MVP: in-memory/demo data. Swap for SQLite/Postgres later.~~

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Environment
Create `.env` with:
- `QLOO_API_KEY`
- `QLOO_BASE_URL=https://hackathon.api.qloo.com`
- `GEMINI_API_KEY`
- `GEMINI_MODEL=gemini-2.5-pro`

The application has no demo mode or seeded demo dataset. Missing credentials fail explicitly instead of falling back to fabricated or simulated data.
