# Arc

Arc is a tool for M&A analysts and business owners. It combines business insights with Qloo cultural intelligence and an AI analyst layer.
It looks at M&A information through these lenses

- Analyst: investigation controls, evidence, findings, source/evidence drill-down, agent activity.
- Business: executive overview, risk/synergy summary, potential company targets and fit scores.
- Discovery: candidate companies ranked on Strategic Fit, Cultural Fit, Audience Expansion, Financial Fit, Risk, and Overall Fit.

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
