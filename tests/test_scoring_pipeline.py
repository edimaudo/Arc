import asyncio
import unittest

from app.services import analysis_service
from app.services.analysis_service import create_analysis, run_investigation
from app.services.scoring_service import build_assessment_scores, score_financial_metrics


class ScoringPipelineTests(unittest.TestCase):
    def test_nested_model_scores_are_normalized(self):
        result = {
            "scores": {
                "strategic_fit": {"score": 82, "rationale": "Strong product complementarity.", "confidence": "medium"},
                "audience_expansion": {"percentage": "76%", "rationale": "New audience territory."},
                "integration_risk": {"level": "Moderate", "rationale": "Some systems diligence needed."},
            },
            "report": {"executive_summary": "A substantive assessment of both companies."},
            "findings": [{"title": "Market complementarity", "body": "They serve adjacent segments."}],
            "financial": {"revenue_growth": "12%", "ebitda_margin": "22%"},
        }
        scores, details, financial = build_assessment_scores(result)
        self.assertEqual(scores["strategic_fit"], 82)
        self.assertEqual(scores["audience_expansion"], 76)
        self.assertEqual(scores["integration_fit"], 60)
        self.assertIsNotNone(scores["financial_fit"])
        self.assertEqual(details["strategic_fit"]["rationale"], "Strong product complementarity.")
        self.assertIn("revenue_growth", financial)

    def test_qloo_distinctive_signals_drive_audience_expansion_score(self):
        result = {
            "scores": {"audience_expansion": 12},
            "cultural": {"qloo_signals": {
                "target_distinctive": [{"name": "New genre", "category": "Music"}, {"name": "New place", "category": "Places"}],
                "shared_affinities": [{"name": "Shared brand", "category": "Brands"}],
                "target_profile": {}, "acquirer_profile": {},
            }},
            "report": {"executive_summary": "Assessment."},
        }
        scores, details, _ = build_assessment_scores(result)
        self.assertEqual(scores["audience_expansion"], 67)
        self.assertEqual(details["audience_expansion"]["method"], "cultural_affinity_comparison")

    def test_detailed_report_gets_directional_scores_when_model_omits_them(self):
        result = {
            "scores": {},
            "summary": "The companies have complementary products and a potential cross-sell opportunity, but operational complexity needs review.",
            "report": {"executive_summary": "A full review of financial, market and integration considerations."},
            "business": {"strategic_rationale": "Complementary products and market access could expand distribution."},
            "financial": {"assessment": "Public financial disclosure is limited; validate margins and cash generation."},
            "cultural": {"profile_summary": "Distinctive interests may support access to new audiences."},
            "findings": [{"title": "Product adjacency", "body": "Complementary product ranges may expand cross-sell opportunities."}],
            "risks": [{"title": "Integration risk", "body": "Operational complexity and system compatibility need review."}],
            "opportunities": [{"title": "Expansion", "body": "Reach a new audience through distribution."}],
        }
        scores, details, _ = build_assessment_scores(result)
        for key in ("strategic_fit", "audience_expansion", "financial_fit", "integration_fit"):
            self.assertIsInstance(scores[key], int)
            self.assertGreaterEqual(scores[key], 0)
            self.assertLessEqual(scores[key], 100)
            self.assertIn("confidence", details[key])
        self.assertEqual(details["financial_fit"]["method"], "qualitative_fallback")

    def test_partial_financial_metrics_are_scored_without_zero_filling_missing_values(self):
        score, details = score_financial_metrics({"ebitda_margin": 0.24})
        self.assertEqual(score, 80)
        self.assertEqual(details["coverage"], "1/4 metrics available")
        self.assertEqual(details["confidence"], "low")

    def test_missing_financial_metrics_are_not_treated_as_zero(self):
        score, details = score_financial_metrics({})
        self.assertIsNone(score)
        self.assertEqual(details, {})

    def test_run_investigation_populates_overview_scores_from_nested_and_partial_evidence(self):
        class StubAgent:
            received_scopes = None

            async def run(self, goal, max_turns=12):
                StubAgent.received_scopes = goal.get("scopes")
                return {
                    "summary": "A substantive report: complementary products could expand distribution, though operating complexity needs review.",
                    "scores": {
                        "strategic_fit": {"score": 81, "rationale": "Product complementarity and market access."},
                        "integration_risk": {"level": "Moderate", "rationale": "Systems alignment requires diligence."},
                    },
                    "score_details": {"strategic_fit": {"confidence": "medium"}},
                    "findings": [{"title": "Product adjacency", "body": "Complementary products create cross-sell opportunities."}],
                    "risks": [{"title": "Operating complexity", "body": "Systems compatibility needs review."}],
                    "opportunities": [{"title": "New markets", "body": "Expand distribution to a new audience."}],
                    "diligence_questions": ["Validate margins."],
                    "financial": {"ebitda_margin": 0.24},
                    "business": {"strategic_rationale": "Complementary products and market access."},
                    "cultural": {"profile_summary": "Distinctive interests may support audience expansion.", "qloo_signals": {
                        "status": "available",
                        "target_distinctive": [{"name": "Target-only music", "category": "Music"}],
                        "shared_affinities": [{"name": "Shared brand", "category": "Brands"}],
                        "target_profile": {}, "acquirer_profile": {},
                    }},
                    "report": {"executive_summary": "Review strategy, financials and integration."},
                }

        previous = analysis_service._AGENT
        analysis_service._AGENT = StubAgent()
        try:
            analysis = create_analysis("Buyer Co", "Target Co", "Full acquisition review", ["financial", "business", "cultural", "integration"])
            # A previously saved IndexedDB record could still contain only one selected scope.
            analysis["scopes"] = ["financial"]
            completed = asyncio.run(run_investigation(analysis))
            overview = completed["overview"]
            self.assertEqual(completed["scopes"], ["financial", "business", "cultural", "integration"])
            self.assertEqual(StubAgent.received_scopes, ["financial", "business", "cultural", "integration"])
            for key in ("strategic_fit", "audience_expansion", "financial_fit", "integration_fit"):
                self.assertIsInstance(overview[key], int, key)
                self.assertGreaterEqual(overview[key], 0)
                self.assertLessEqual(overview[key], 100)
            self.assertEqual(overview["strategic_fit"], 81)
            self.assertEqual(overview["audience_expansion"], 50)
            self.assertEqual(overview["financial_fit"], 80)
            self.assertEqual(overview["integration_fit"], 60)
            self.assertEqual(completed["score_details"]["financial_fit"]["confidence"], "low")
        finally:
            analysis_service._AGENT = previous


if __name__ == "__main__":
    unittest.main()
