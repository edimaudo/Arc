import os
import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path

os.environ['GEMINI_API_KEY'] = 'test'
os.environ['QLOO_API_KEY'] = 'test'
os.environ['ARC_DB_PATH'] = str(Path(tempfile.gettempdir()) / 'arc_integration.sqlite3')

from app.main import app
from app.services import analysis_service
from app.services.agent_service import ArcAgent
from app.db import get_user_by_email
from app.routers import discovery
from fastapi.testclient import TestClient


class StubAgent:
    async def run(self, goal, max_turns=12):
        return {
            'output': 'Structured acquisition assessment.',
            'activity': [{'tool':'qloo_lookup_entities','status':'complete','result':'Resolved 4 entities.'}],
            'findings': [{'type':'Opportunity','title':'Audience adjacency','body':'Target opens adjacent audience territory.'}],
            'risks': [{'type':'Risk','title':'Brand positioning','body':'Positioning requires diligence.'}],
            'opportunities': [{'title':'Cross-sell','body':'Potential cross-sell opportunity.'}],
            'diligence_questions': ['Validate customer concentration.'],
            'scores': {'strategic_fit':82,'cultural_fit':79,'audience_expansion':88,'financial_fit':74,'integration_risk':'Moderate'},
            'financial': {'revenue_growth':0.12,'ebitda_margin':0.22,'net_debt_to_ebitda':1.8,'customer_concentration':24,'assessment':'Public metrics support further diligence.'},
            'business': {'model':'Consumer subscription','market':'North America','strategic_rationale':'Adjacency','open_questions':['Retention']},
            'cultural': {'acquirer_entities':[{'name':'A'}],'target_entities':[{'name':'B'}],'shared':['Design'],'distinct':['Outdoor'],'qloo_metrics':{}},
            'qloo_evidence': {'preflight': {'acquirer': [], 'target': []}},
            'report': {'executive_summary':'Executive summary.', 'disclaimer':'Validate material findings.'},
        }

    async def ask(self, question, context):
        return 'Arc answer grounded in the investigation.'


class DiscoveryStub:
    async def find_potential_targets(self, args):
        return {
            'candidates': [
                {'name': 'Target One', 'sector': args['sector'], 'geography': args['geography'], 'rationale': 'Adjacent', 'website': 'https://example.com', 'public_or_private': 'Public'}
            ],
            'search_activity': [{'tool': 'google_search', 'status': 'complete'}],
        }

    async def screen_target(self, acquirer, candidate, thesis):
        return {
            **candidate,
            'strategic_fit': 80, 'cultural_fit': 90, 'audience_expansion': 70, 'financial_fit': 60,
            'scores': {'strategic_fit': 80, 'cultural_fit': 90, 'audience_expansion': 70, 'financial_fit': 60},
            'overall_fit': 77, 'score_status': 'complete'
        }


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.original = analysis_service._AGENT
        analysis_service._AGENT = StubAgent()
        self.client = TestClient(app, follow_redirects=False)
        email = f"arc-test-{uuid.uuid4().hex[:10]}@example.com"
        response = self.client.post('/signup', data={
            'email': email, 'password': 'correct-horse-battery-staple',
            'display_name': 'Test Analyst', 'next': '/dashboard',
        })
        if response.status_code != 303:
            raise AssertionError(f"Test account registration failed: {response.status_code} {response.text[:300]}")
        self.user_id = get_user_by_email(email)['user_id']

    def tearDown(self):
        analysis_service._AGENT = self.original

    def test_discovery_contract(self):
        original = discovery._agent
        discovery._agent = DiscoveryStub()
        try:
            r = self.client.get('/discovery/api/candidates?acquirer=Acquirer&sector=Consumer&geography=Canada&thesis=Adjacency')
            self.assertEqual(r.status_code, 200)
            payload = r.json()
            self.assertEqual(payload['candidates'][0]['overall_fit'], 77)
            self.assertEqual(payload['candidates'][0]['components']['cultural_fit'], 90)
        finally:
            discovery._agent = original

    def test_analysis_full_flow(self):
        aid = analysis_service.create_analysis('Acquirer', 'Target', 'Assess fit', ['financial','business','cultural','integration'], owner_id=self.user_id)
        r = self.client.post(f'/analysis/{aid}/run')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'Investigation complete')
        loaded = analysis_service.get_analysis(aid)
        self.assertEqual(loaded['overview']['cultural_alignment'], 79)
        self.assertEqual(loaded['overview']['audience_expansion'], 88)
        self.assertEqual(loaded['overview']['integration_risk'], 'Moderate')
        self.assertEqual(loaded['report']['executive_summary'], 'Executive summary.')
        pdf = self.client.get(f'/analysis/{aid}/report.pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b'%PDF'))


    def test_landing_uses_public_shell_and_product_names(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        body = response.text
        # The public entry point uses a separate base template, so internal navigation cannot leak onto it.
        self.assertNotIn('<nav', body)
        self.assertNotIn('Dashboard', body)
        self.assertNotIn('Analyst', body)
        self.assertNotIn('Business Owner', body)
        self.assertNotIn('Find Companies', body)
        self.assertNotIn('Financial Intelligence', body)
        self.assertNotIn('Business Intelligence', body)
        self.assertNotIn('Cultural Intelligence', body)
        self.assertNotIn('Qloo', body)
        self.assertNotIn('Acquisition Intelligence', body)
        self.assertNotIn('workflow', body.lower())
        for title in ['M&amp;A Analysis', 'Business Insights', 'Discovery', 'Start M&amp;A analysis']:
            self.assertIn(title, body)

    def test_internal_navigation_uses_consistent_product_names(self):
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('<nav aria-label="Primary">', body)
        self.assertIn('Dashboard</a>', body)
        self.assertIn('M&amp;A Analysis</a>', body)
        self.assertIn('Business Insights</a>', body)
        self.assertIn('Discovery</a>', body)
        self.assertNotIn('Business Owner', body)
        self.assertNotIn('Find Companies', body)
        self.assertNotIn('class="source-pill"', body)
        self.assertNotIn('class="eyebrow"', body)
        self.assertNotIn('class="kicker"', body)

    def test_shared_internal_shell_and_no_eyebrow_components(self):
        internal_routes = ['/dashboard', '/analyst', '/owner', '/discovery', '/analysis/new']
        for route in internal_routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                body = response.text
                self.assertIn('<nav aria-label="Primary">', body)
                self.assertIn('Business Insights</a>', body)
                self.assertIn('M&amp;A Analysis</a>', body)
                self.assertIn('Discovery</a>', body)
                self.assertNotIn('class="eyebrow"', body)
                self.assertNotIn('class="kicker"', body)
                self.assertNotIn('class="source-pill"', body)
        anonymous = TestClient(app, follow_redirects=False)
        for route in ['/login', '/signup']:
            with self.subTest(public_auth_route=route):
                response = anonymous.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('<nav aria-label="Primary">', response.text)
                self.assertNotIn('class="eyebrow"', response.text)
                self.assertNotIn('class="kicker"', response.text)

    def test_unauthenticated_app_links_redirect_to_sign_in(self):
        anonymous = TestClient(app, follow_redirects=False)
        for route in ['/analysis/new', '/owner', '/discovery', '/dashboard']:
            with self.subTest(route=route):
                response = anonymous.get(route)
                self.assertEqual(response.status_code, 303)
                self.assertIn('/login?next=', response.headers.get('location', ''))
        api = anonymous.get('/discovery/api/candidates?acquirer=A&sector=Retail')
        self.assertEqual(api.status_code, 401)
        self.assertEqual(api.json()['detail']['message'], 'Sign in to continue.')

    def test_signup_login_logout_and_return_to_requested_page(self):
        anonymous = TestClient(app, follow_redirects=False)
        email = f"arc-auth-{uuid.uuid4().hex[:10]}@example.com"
        signup = anonymous.post('/signup', data={
            'email': email, 'password': 'a-secure-test-password',
            'display_name': 'Product Tester', 'next': '/analysis/new',
        })
        self.assertEqual(signup.status_code, 303)
        self.assertEqual(signup.headers.get('location'), '/analysis/new')
        self.assertEqual(anonymous.get('/analysis/new').status_code, 200)
        anonymous.post('/logout')
        after_logout = anonymous.get('/analysis/new')
        self.assertEqual(after_logout.status_code, 303)
        self.assertIn('/login?next=', after_logout.headers.get('location', ''))
        bad_login = anonymous.post('/login', data={'email': email, 'password': 'incorrect-password', 'next': '/dashboard'})
        self.assertEqual(bad_login.status_code, 401)
        good_login = anonymous.post('/login', data={'email': email, 'password': 'a-secure-test-password', 'next': '/dashboard'})
        self.assertEqual(good_login.status_code, 303)
        self.assertEqual(good_login.headers.get('location'), '/dashboard')
        self.assertEqual(anonymous.get('/dashboard').status_code, 200)

    def test_start_analysis_form_redirects_to_a_valid_analysis_page(self):
        response = self.client.get('/analysis/new')
        self.assertEqual(response.status_code, 200)
        created = self.client.post('/analysis/start', data={
            'acquirer': 'Acquirer Ltd', 'target': 'Target Ltd',
            'objective': 'Full acquisition investigation',
            'scopes': ['financial', 'business', 'cultural', 'integration'],
        })
        self.assertEqual(created.status_code, 303)
        location = created.headers.get('location', '')
        self.assertRegex(location, r'^/analysis/analysis-[a-f0-9]+$')
        detail = self.client.get(location)
        self.assertEqual(detail.status_code, 200)
        self.assertIn('Acquirer Ltd', detail.text)
        self.assertIn('Target Ltd', detail.text)

    def test_landing_cta_requires_signin_then_starts_analysis(self):
        anonymous = TestClient(app, follow_redirects=False)
        landing = anonymous.get('/')
        self.assertEqual(landing.status_code, 200)
        self.assertIn('href="/analysis/new"', landing.text)
        gate = anonymous.get('/analysis/new')
        self.assertEqual(gate.status_code, 303)
        self.assertIn('/login?next=/analysis/new', gate.headers['location'])
        email = f"arc-flow-{uuid.uuid4().hex[:10]}@example.com"
        account = anonymous.post('/signup', data={
            'email': email, 'password': 'another-secure-password',
            'display_name': 'M&A Analyst', 'next': '/analysis/new',
        })
        self.assertEqual(account.status_code, 303)
        self.assertEqual(anonymous.get('/analysis/new').status_code, 200)
        created = anonymous.post('/analysis/start', data={
            'acquirer': 'Company One', 'target': 'Company Two',
            'objective': 'Full acquisition investigation',
            'scopes': ['financial', 'business', 'cultural', 'integration'],
        })
        self.assertEqual(created.status_code, 303)
        self.assertEqual(anonymous.get(created.headers['location']).status_code, 200)

    def test_users_cannot_open_another_users_analysis(self):
        aid = analysis_service.create_analysis(
            'Private Acquirer', 'Private Target', 'Confidential assessment', ['financial'], owner_id=self.user_id
        )
        other = TestClient(app, follow_redirects=False)
        email = f"arc-other-{uuid.uuid4().hex[:10]}@example.com"
        registered = other.post('/signup', data={
            'email': email, 'password': 'another-secure-password', 'next': '/dashboard'
        })
        self.assertEqual(registered.status_code, 303)
        denied = other.get(f'/analysis/{aid}')
        self.assertEqual(denied.status_code, 404)
        response = other.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Private Acquirer', response.text)


if __name__ == '__main__':
    unittest.main()
