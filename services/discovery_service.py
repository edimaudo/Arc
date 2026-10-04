from typing import Any


def get_demo_candidates() -> list[dict[str, Any]]:
    return [
        {
            "name": "PeakTrail Outdoors",
            "sector": "Consumer / Outdoor",
            "overall_fit": 86,
            "strategic_fit": 89,
            "cultural_fit": 92,
            "audience_expansion": 91,
            "financial_fit": 73,
            "risk": "Moderate",
            "thesis": "Strong cultural adjacency with meaningful access to outdoor, travel and technical-lifestyle audiences.",
        },
        {
            "name": "Harbour & Co.",
            "sector": "Consumer / Lifestyle",
            "overall_fit": 81,
            "strategic_fit": 85,
            "cultural_fit": 84,
            "audience_expansion": 79,
            "financial_fit": 80,
            "risk": "Low",
            "thesis": "High brand and audience compatibility with lower integration complexity.",
        },
        {
            "name": "Lumen Home",
            "sector": "Consumer / Home",
            "overall_fit": 76,
            "strategic_fit": 75,
            "cultural_fit": 83,
            "audience_expansion": 81,
            "financial_fit": 68,
            "risk": "Moderate",
            "thesis": "Strong design and lifestyle adjacency, offset by weaker financial fit in the demo scenario.",
        },
        {
            "name": "Northline Mobility",
            "sector": "Mobility / Technology",
            "overall_fit": 69,
            "strategic_fit": 72,
            "cultural_fit": 64,
            "audience_expansion": 77,
            "financial_fit": 62,
            "risk": "High",
            "thesis": "Potential strategic upside, but the cultural and operating distance raises integration questions.",
        },
    ]


WEIGHTS = {
    "strategic_fit": 0.30,
    "cultural_fit": 0.30,
    "audience_expansion": 0.20,
    "financial_fit": 0.20,
}

def calculate_overall_fit(scores: dict[str, int]) -> int:
    return round(sum(scores[k] * w for k, w in WEIGHTS.items()))

def explain_score(candidate: dict[str, Any]) -> dict[str, Any]:
    component_scores = {k: candidate[k] for k in WEIGHTS}
    return {
        "overall_fit": calculate_overall_fit(component_scores),
        "components": component_scores,
        "weights": WEIGHTS,
    }
