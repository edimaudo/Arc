from __future__ import annotations

from typing import Any

WEIGHTS = {
    "strategic_fit": 0.30,
    "cultural_fit": 0.30,
    "audience_expansion": 0.20,
    "financial_fit": 0.20,
}


def calculate_overall_fit(scores: dict[str, float | None]) -> int | None:
    if any(scores.get(k) is None for k in WEIGHTS):
        return None
    return round(sum(float(scores[k]) * weight for k, weight in WEIGHTS.items()))


def explain_score(candidate: dict[str, Any]) -> dict[str, Any]:
    component_scores = {k: (float(candidate.get(k)) if candidate.get(k) is not None else None) for k in WEIGHTS}
    return {
        "overall_fit": calculate_overall_fit(component_scores),
        "components": {k: round(v) if v is not None else None for k, v in component_scores.items()},
        "weights": WEIGHTS,
        "status": "complete" if all(v is not None for v in component_scores.values()) else "insufficient_evidence",
    }
