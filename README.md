# Arc — Business Acquisition Intelligence

Looking to acquire a new business or see what businesses align too your values? Arc is the tool for you. 
It combines business insights with cultural intelligence.  It achieves this by leveraging Qloo cultural intelligence and an analyst layer.

It Analyzes information through these lenses

- Acquisition Analysis: investigation controls, evidence, findings, source/evidence drill-down, cultural insights.
- Business Insights: executive overview, risk/synergy summary, potential company targets and fit scores.
- Company discovery: Top 5 companies similar to the company aligned to what you are looking for. candidate companies ranked on Strategic Fit, Cultural Fit, Audience Expansion, Financial Fit, Risk, and Overall Fit.

## Architecture
- Backend: FastAPI
- Frontend: Jinja2 + vanilla JavaScript + CSS
- Cultural intelligence: Qloo APIs (`/search`, `/v2/insights`, analysis/compare, trends)
- AI: Gemini 3.6 Flash

## Login
Default demo credentials:
- Email: `demo@arc.app`
- Password: `ArcDemo2026!`


## Environment
Create `.env` with:
- `QLOO_API_KEY`
- `QLOO_BASE_URL=https://hackathon.api.qloo.com`
- `GEMINI_API_KEY`
- `GEMINI_MODEL=gemini-3.6-flash`

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000
