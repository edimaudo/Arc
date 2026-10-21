import asyncio
import os
import unittest
from unittest.mock import AsyncMock

os.environ['GEMINI_API_KEY'] = 'unit-test'
os.environ['QLOO_API_KEY'] = 'unit-test'

from app.services.agent_service import ArcAgent
from app.services.analysis_service import create_analysis, run_investigation
from app.services.document_service import parse_document
from app.services.discovery_service import explain_score


class StubAgent:
    async def run(self, goal, max_turns=12):
        return {
            'output': 'Structured acquisition assessment.',
            'activity': [{'tool': 'qloo_lookup_entities', 'status': 'complete'}],
            'findings': [{'type': 'Opportunity', 'title': 'Audience adjacency', 'body': 'Target opens adjacent audience territory.'}],
            'risks': [{'type': 'Risk', 'title': 'Brand positioning', 'body': 'Positioning requires diligence.'}],
            'opportunities': [{'title': 'Cross-sell', 'body': 'Potential cross-sell opportunity.'}],
            'diligence_questions': ['Validate customer concentration.'],
            'scores': {'strategic_fit': 82, 'cultural_fit': 79, 'audience_expansion': 88, 'financial_fit': 74, 'integration_risk': 'Moderate'},
            'financial': {'revenue_growth': 0.12, 'ebitda_margin': 0.22, 'net_debt_to_ebitda': 1.8, 'customer_concentration': 24, 'assessment': 'Public metrics support further diligence.'},
            'business': {'model': 'Consumer subscription', 'market': 'North America', 'strategic_rationale': 'Adjacency', 'open_questions': ['Retention']},
            'cultural': {'acquirer_entities': [{'name': 'A'}], 'target_entities': [{'name': 'B'}], 'shared': ['Design'], 'distinct': ['Outdoor'], 'qloo_metrics': {}},
            'qloo_evidence': {},
            'report': {'executive_summary': 'Executive summary.', 'disclaimer': 'Validate material findings.'},
        }


class CoreTests(unittest.TestCase):
    def test_financial_fit_uses_partial_verified_evidence(self):
        result = asyncio.run(ArcAgent().calculate_financial_fit({'metrics': {'ebitda_margin': 0.22}}))
        self.assertEqual(result['financial_fit'], 73)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['coverage'], '1/4 metrics available')

    def test_financial_fit_remains_unscored_without_any_metrics(self):
        result = asyncio.run(ArcAgent().calculate_financial_fit({'metrics': {}}))
        self.assertIsNone(result['financial_fit'])
        self.assertEqual(result['status'], 'insufficient_evidence')

    def test_candidate_score(self):
        result = explain_score({'strategic_fit': 80, 'cultural_fit': 90, 'audience_expansion': 70, 'financial_fit': 60})
        self.assertEqual(result['overall_fit'], 77)
        self.assertEqual(result['components']['cultural_fit'], 90)

    def test_first_pass_mna_research_uses_one_grounded_gemini_request(self):
        agent = ArcAgent()
        agent._require_gemini = lambda: None
        agent._web_search_json = AsyncMock(return_value={
            'data': {
                'summary': 'Preliminary assessment.',
                'findings': [{'type': 'Finding', 'title': 'Market position', 'body': 'Research-backed observation.', 'evidence': 'Public sources'}],
                'risks': [], 'opportunities': [], 'diligence_questions': [], 'scores': {},
                'financial': {}, 'business': {}, 'cultural': {}, 'qloo_evidence': {},
                'report': {'executive_summary': 'Preliminary assessment.'},
            },
            'steps': [{'tool': 'google_search', 'status': 'complete'}],
        })
        agent._seed_qloo_context = AsyncMock(return_value={
            'acquirer': [], 'target': [], 'comparison': {}, 'errors': ['Qloo unavailable']
        })
        result = asyncio.run(agent.run({'acquirer': 'Buyer Co', 'target': 'Target Co', 'documents': []}))
        self.assertEqual(agent._web_search_json.await_count, 1)
        self.assertEqual(agent._seed_qloo_context.await_count, 1)
        prompt = agent._web_search_json.await_args.args[0]
        self.assertIn('If none are present, research both companies anyway.', prompt)
        self.assertEqual(result['findings'][0]['title'], 'Market position')

    def test_document_metrics(self):
        data = b'revenue growth,12%\nebitda margin,22%\nnet debt / ebitda,1.8\ncustomer concentration,24%\n'
        parsed = parse_document('metrics.csv', data)
        self.assertEqual(parsed['metrics']['revenue_growth'], 0.12)
        self.assertEqual(parsed['metrics']['ebitda_margin'], 0.22)
        self.assertEqual(parsed['metrics']['net_debt_to_ebitda'], 1.8)

    def test_analysis_payload_is_created_without_a_database(self):
        analysis = create_analysis('A', 'B', 'Test', ['financial'])
        self.assertRegex(analysis['analysis_id'], r'^analysis-[a-f0-9]+$')
        self.assertEqual(analysis['acquirer'], 'A')
        self.assertIsNone(analysis['overview']['strategic_fit'])

    def test_investigation_transforms_payload_without_persisting(self):
        from app.services import analysis_service
        previous = analysis_service._AGENT
        analysis_service._AGENT = StubAgent()
        try:
            analysis = create_analysis('A', 'B', 'Test', ['financial', 'business'])
            result = asyncio.run(run_investigation(analysis))
            self.assertEqual(result['status'], 'Investigation complete')
            self.assertEqual(result['overview']['cultural_alignment'], 79)
            self.assertEqual(result['overview']['audience_expansion'], 88)
            self.assertEqual(result['overview']['integration_risk'], 'Moderate')
            self.assertEqual(result['report']['executive_summary'], 'Executive summary.')
        finally:
            analysis_service._AGENT = previous


if __name__ == '__main__':
    unittest.main()
