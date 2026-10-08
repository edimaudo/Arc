# Arc — M&A Cultural & Business Intelligence

Arc is a FastAPI + Jinja2 application for M&A analysts and business decision-makers. It combines deterministic financial/business logic, Qloo cultural intelligence, and Gemini tool use to investigate acquisition questions.

## Product surfaces
- **Analyst** — detailed investigation workspace, evidence, cultural intelligence, activity and report.
- **Business Insights** — executive view focused on fit, risks, growth opportunities and acquisition candidates.
- **Find potential companies** — grounded company discovery with transparent component scores when sufficient evidence is available.

## Qloo integration
- Hackathon base URL: `https://hackathon.api.qloo.com`
- Header: `X-Api-Key`
- Entity resolution: `/search`
- Cultural intelligence: `/v2/insights`
- Cross-company comparison: `/v2/analysis/compare`
- Cultural momentum: `/v2/trending`
- **Do not use `/recommendations` or `/recs`.**

## Gemini integration
Gemini 2.5 Pro is used through the Gemini Interactions API with custom function tools. Gemini can also use Google Search grounding for current public-company research. The application executes custom tool calls server-side and returns results to Gemini for subsequent steps.

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
