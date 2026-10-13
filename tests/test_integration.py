import os
import unittest

os.environ['GEMINI_API_KEY'] = 'test'
os.environ['QLOO_API_KEY'] = 'test'
os.environ['ARC_SESSION_SECRET'] = 'test-session-secret'

from fastapi.testclient import TestClient
from app.main import app
from app.auth import DEMO_EMAIL, DEMO_PASSWORD, authenticate_user
from app.services import analysis_service
from app.routers import analyses, discovery


class StubAgent:
    async def run(self, goal, max_turns=12):
        return {
            'output': 'Structured acquisition assessment.',
            'activity': [{'tool': 'qloo_lookup_entities', 'status': 'complete', 'result': 'Resolved 4 entities.'}],
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

    async def ask(self, question, context):
        return 'Arc answer grounded in the investigation.'


class DiscoveryStub:
    async def find_potential_targets(self, args):
        return {'candidates': [{'name': 'Target One', 'sector': args['sector'], 'geography': args['geography'], 'rationale': 'Adjacent', 'website': 'https://example.com', 'public_or_private': 'Public'}], 'search_activity': []}

    async def screen_target(self, acquirer, candidate, thesis):
        return {**candidate, 'strategic_fit': 80, 'cultural_fit': 90, 'audience_expansion': 70, 'financial_fit': 60,
                'scores': {'strategic_fit': 80, 'cultural_fit': 90, 'audience_expansion': 70, 'financial_fit': 60},
                'overall_fit': 77, 'score_status': 'complete'}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.prev_agent = analysis_service._AGENT
        self.prev_route_agent = analyses._agent
        analysis_service._AGENT = StubAgent()
        analyses._agent = StubAgent()
        self.client = TestClient(app, follow_redirects=False)
        response = self.client.post('/demo-login', data={'next': '/dashboard'})
        if response.status_code != 303:
            raise AssertionError(f'Demo login failed: {response.status_code} {response.text[:200]}')

    def tearDown(self):
        analysis_service._AGENT = self.prev_agent
        analyses._agent = self.prev_route_agent

    def test_demo_user_authenticates_without_account_storage(self):
        self.assertIsNotNone(authenticate_user(DEMO_EMAIL, DEMO_PASSWORD))
        self.assertIsNone(authenticate_user('other@example.com', 'nope'))
        self.assertEqual(self.client.get('/dashboard').status_code, 200)
        self.assertEqual(self.client.get('/health').json()['storage'], 'browser IndexedDB; no server database')

    def test_discovery_contract(self):
        original = discovery._agent
        discovery._agent = DiscoveryStub()
        try:
            response = self.client.get('/discovery/api/candidates?acquirer=Acquirer&sector=Consumer&geography=Canada&thesis=Adjacency')
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload['candidates'][0]['overall_fit'], 77)
            self.assertEqual(payload['candidates'][0]['components']['cultural_fit'], 90)
        finally:
            discovery._agent = original

    def test_analysis_flow_is_stateless_from_the_server(self):
        created = self.client.post('/analysis/start', data={
            'acquirer': 'Acquirer Ltd', 'target': 'Target Ltd', 'objective': 'Full acquisition investigation',
            'scopes': ['financial', 'business', 'cultural', 'integration'],
        })
        self.assertEqual(created.status_code, 200)
        analysis = created.json()['analysis']
        analysis_id = analysis['analysis_id']
        self.assertEqual(analysis['acquirer'], 'Acquirer Ltd')
        detail = self.client.get(f'/analysis/{analysis_id}')
        self.assertEqual(detail.status_code, 200)
        self.assertIn(f'data-analysis-id="{analysis_id}"', detail.text)
        run = self.client.post(f'/analysis/{analysis_id}/run', json={'analysis': analysis})
        self.assertEqual(run.status_code, 200, run.text)
        completed = run.json()['analysis']
        self.assertEqual(completed['status'], 'Investigation complete')
        self.assertEqual(completed['overview']['cultural_alignment'], 79)
        self.assertEqual(completed['overview']['audience_expansion'], 88)
        self.assertEqual(completed['overview']['integration_risk'], 'Moderate')
        self.assertEqual(completed['report']['executive_summary'], 'Executive summary.')
        pdf = self.client.post(f'/analysis/{analysis_id}/report.pdf', json={'analysis': completed})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_ask_arc_receives_client_stored_analysis(self):
        created = self.client.post('/analysis/start', data={'acquirer': 'A', 'target': 'B', 'objective': 'Full acquisition investigation', 'scopes': ['financial']})
        analysis = created.json()['analysis']
        response = self.client.post(f"/analysis/{analysis['analysis_id']}/ask", json={'question': 'What matters?', 'analysis': analysis})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], 'Arc answer grounded in the investigation.')

    def test_landing_and_internal_navigation_labels(self):
        body = self.client.get('/').text
        self.assertNotIn('<nav', body)
        self.assertNotIn('Qloo', body)
        for label in ['M&amp;A Analysis', 'Business Insights', 'Discovery', 'Start M&amp;A analysis']:
            self.assertIn(label, body)
        for route in ['/dashboard', '/analyst', '/owner', '/discovery', '/analysis/new']:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertIn('<nav aria-label="Primary">', response.text)
            self.assertNotIn('class="eyebrow"', response.text)
            self.assertNotIn('class="kicker"', response.text)

    def test_unauthenticated_routes_redirect_to_sign_in(self):
        client = TestClient(app, follow_redirects=False)
        for route in ['/analysis/new', '/owner', '/discovery', '/dashboard']:
            response = client.get(route)
            self.assertEqual(response.status_code, 303)
            self.assertIn('/login?next=', response.headers.get('location', ''))
        response = client.get('/discovery/api/candidates?acquirer=A&sector=Retail')
        self.assertEqual(response.status_code, 401)

    def test_single_demo_account_not_signup(self):
        page = TestClient(app, follow_redirects=False).get('/login')
        self.assertEqual(page.status_code, 200)
        self.assertIn(DEMO_EMAIL, page.text)
        self.assertIn(DEMO_PASSWORD, page.text)
        self.assertIn('Continue with demo account', page.text)
        signup = self.client.get('/signup')
        self.assertEqual(signup.status_code, 303)


if __name__ == '__main__':
    unittest.main()
