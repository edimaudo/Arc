from datetime import datetime, timezone


def run_demo_investigation(analysis_id: str):
    return {
        "analysis_id": analysis_id,
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "message": "Demo investigation completed. Replace this adapter with Gemini tool-calling orchestration and live Qloo calls.",
    }
