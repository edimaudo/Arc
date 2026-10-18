import asyncio
import os
import unittest

os.environ['GEMINI_API_KEY'] = 'test'
os.environ['QLOO_API_KEY'] = 'test'
os.environ['ARC_SESSION_SECRET'] = 'test-session-secret'

from fastapi.testclient import TestClient
from app.main import app
from app.auth import DEMO_EMAIL, DEMO_PASSWORD, authenticate_user
from app.services import analysis_service
from app.services.analysis_service import create_analysis, run_investigation
from app.routers import discovery, dashboard


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


class DiscoveryStub:
    async def find_comparable_companies(self, args):
        return {'comparables': [{'name': 'Peer One', 'sector': args['sector'], 'geography': args['geography'],
                                 'annual_revenue_estimate': '$25 million (FY2025)',
                                 'company_valuation_estimate': 'Not publicly disclosed',
                                 'employee_count_estimate': '120-150',
                                 'business_summary': 'A mid-sized consumer business.',
                                 'comparability_reason': 'Similar sector and scale.',
                                 'sources': [{'title': 'Company website', 'url': 'https://example.com'}]}], 'search_activity': []}


class BusinessInsightsStub:
    async def research_business_insights(self, args):
        return {'insights': {'company': args['company'] or 'Industry overview', 'sector': args.get('sector', ''),
                            'business_overview': 'A public company operating overview.',
                            'current_trends': [{'title': 'Demand shift', 'detail': 'Customers are shifting to online channels.'}],
                            'competitive_landscape': [{'name': 'Peer Co', 'summary': 'A competitor in the same category.'}],
                            'growth_opportunities': [{'title': 'Expand online', 'detail': 'Improve digital distribution.'}],
                            'business_risks': [{'title': 'Margin pressure', 'detail': 'Input cost changes may pressure margins.'}],
                            'recommended_actions': [{'title': 'Track margins', 'action': 'Review unit economics monthly.', 'reason': 'Catch cost changes early.'}],
                            'key_metrics_to_watch': ['Gross margin'],
                            'sources': [{'title': 'Public source', 'url': 'https://example.com'}]}, 'search_activity': []}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.prev_agent = analysis_service._AGENT
        self.prev_dashboard_agent = dashboard._agent
        analysis_service._AGENT = StubAgent()
        self.client = TestClient(app, follow_redirects=False)
        response = self.client.post('/demo-login', data={'next': '/dashboard'})
        if response.status_code != 303:
            raise AssertionError(f'Demo login failed: {response.status_code} {response.text[:200]}')

    def tearDown(self):
        analysis_service._AGENT = self.prev_agent
        dashboard._agent = self.prev_dashboard_agent

    def test_demo_user_authenticates_without_account_storage(self):
        self.assertIsNotNone(authenticate_user(DEMO_EMAIL, DEMO_PASSWORD))
        self.assertIsNone(authenticate_user('other@example.com', 'nope'))
        self.assertEqual(self.client.get('/dashboard').status_code, 200)
        self.assertEqual(self.client.get('/health').json()['storage'], 'browser IndexedDB; no server database')

    def test_discovery_returns_comparable_companies_not_acquisition_scores(self):
        original = discovery._agent
        discovery._agent = DiscoveryStub()
        try:
            response = self.client.post('/discovery/api/comparables', json={
                'reference_company': 'Example Co', 'sector': 'Consumer', 'geography': 'Canada',
                'size_metric': 'revenue', 'size_band': '$10 million–$50 million',
            })
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            peer = payload['comparables'][0]
            self.assertEqual(peer['name'], 'Peer One')
            self.assertEqual(peer['annual_revenue_estimate'], '$25 million (FY2025)')
            self.assertNotIn('overall_fit', peer)
            self.assertNotIn('strategic_fit', peer)
        finally:
            discovery._agent = original
        original = discovery._agent
        discovery._agent = DiscoveryStub()
        try:
            response = self.client.post('/discovery/api/comparables', json={'reference_company': 'Example Co'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['criteria']['reference_company'], 'Example Co')
        finally:
            discovery._agent = original

    def test_business_insights_shows_actionable_provider_error(self):
        class UnavailableInsights:
            async def research_business_insights(self, args):
                raise RuntimeError('Gemini API request failed (429): quota exceeded')
        original = dashboard._agent
        dashboard._agent = UnavailableInsights()
        try:
            response = self.client.post('/owner/api/insights', json={'company': 'Example Co'})
            self.assertEqual(response.status_code, 503)
            self.assertIn('quota', response.json()['error'].lower())
            self.assertTrue(response.json()['retryable'])
        finally:
            dashboard._agent = original

    def test_business_insights_is_independent_company_research(self):
        original = dashboard._agent
        dashboard._agent = BusinessInsightsStub()
        try:
            response = self.client.post('/owner/api/insights', json={
                'company': 'Example Co', 'sector': 'Retail', 'geography': 'Canada', 'focus': 'Market and competitors'
            })
            self.assertEqual(response.status_code, 200)
            report = response.json()['insights']
            self.assertEqual(report['company'], 'Example Co')
            self.assertIn('business_overview', report)
            self.assertIn('competitive_landscape', report)
            self.assertIn('growth_opportunities', report)
            self.assertNotIn('strategic_fit', report)
        finally:
            dashboard._agent = original

    def test_discovery_unclassified_provider_error_has_reference_id_and_safe_message(self):
        class RejectedRequestDiscovery:
            async def find_comparable_companies(self, args):
                raise RuntimeError('Gemini API request failed (400): invalid request payload')
        original = discovery._agent
        discovery._agent = RejectedRequestDiscovery()
        try:
            response = self.client.post(
                '/discovery/api/comparables',
                json={'reference_company': 'Example Co', 'geography': 'North America'},
                headers={'X-Arc-Request-ID': 'DISC-TEST123'},
            )
            self.assertEqual(response.status_code, 503)
            body = response.json()
            self.assertEqual(body['error_code'], 'provider_rejected_request')
            self.assertEqual(body['reference_id'], 'DISC-TEST123')
            self.assertIn('model or API configuration', body['error'])
            self.assertNotIn('API key, model setting, and quota', body['error'])
        finally:
            discovery._agent = original

    def test_discovery_shows_actionable_provider_error(self):
        class UnavailableDiscovery:
            async def find_comparable_companies(self, args):
                raise RuntimeError('Gemini API rejected credentials or permissions (403).')
        original = discovery._agent
        discovery._agent = UnavailableDiscovery()
        try:
            response = self.client.post('/discovery/api/comparables', json={'reference_company': 'Example Co', 'geography': 'North America (Canada and United States)'})
            self.assertEqual(response.status_code, 503)
            self.assertIn('credentials', response.json()['error'].lower())
            self.assertTrue(response.json()['retryable'])
        finally:
            discovery._agent = original

    def test_blank_upload_is_optional_and_does_not_trigger_unknown_file_type(self):
        response = self.client.post('/analysis/start', data={
            'acquirer': 'Acquirer Ltd', 'target': 'Target Ltd', 'objective': 'Full acquisition investigation',
            'scopes': ['financial', 'business'],
        }, files={'evidence': ('', b'', 'application/octet-stream')})
        self.assertEqual(response.status_code, 200, response.text)
        analysis = response.json()['analysis']
        self.assertEqual(analysis['documents'], [])
        self.assertEqual(analysis['upload_errors'], [])

    def test_live_research_outage_returns_limited_analysis(self):
        class UnavailableAgent:
            async def run(self, goal, max_turns=12):
                raise RuntimeError('Gemini API request timed out after 60s.')
        previous = analysis_service._AGENT
        analysis_service._AGENT = UnavailableAgent()
        try:
            analysis = create_analysis('Buyer Ltd', 'Target Ltd', 'Full acquisition investigation', ['financial', 'business'])
            result = asyncio.run(run_investigation(analysis))
            self.assertTrue(result['limited_mode'])
            self.assertIn('limited analysis', result['status'].lower())
            self.assertGreaterEqual(len(result['findings']), 3)
            self.assertGreaterEqual(len(result['risks']['items']), 3)
            self.assertIsNone(result['overview']['strategic_fit'])
            self.assertIn('timed out', result['service_notice'].lower())
        finally:
            analysis_service._AGENT = previous

    def test_uploaded_document_metrics_survive_api_outage(self):
        class UnavailableAgent:
            async def run(self, goal, max_turns=12):
                raise RuntimeError('Gemini API request timed out after 60s.')
        previous = analysis_service._AGENT
        analysis_service._AGENT = UnavailableAgent()
        try:
            analysis = create_analysis('Buyer Ltd', 'Target Ltd', 'Full acquisition investigation', ['financial'])
            analysis['documents'] = [{
                'filename': 'metrics.csv', 'type': 'csv',
                'text': 'Revenue growth 12%; EBITDA margin 22%.',
                'metrics': {'revenue_growth': 0.12, 'ebitda_margin': 0.22},
            }]
            result = asyncio.run(run_investigation(analysis))
            self.assertEqual(result['financial']['revenue_growth'], 0.12)
            self.assertEqual(result['financial']['ebitda_margin'], 0.22)
            self.assertTrue(any('Uploaded material' in item['title'] for item in result['findings']))
            self.assertTrue(result['limited_mode'])
        finally:
            analysis_service._AGENT = previous

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

    def test_analysis_page_does_not_show_redundant_ask_arc_chat(self):
        created = self.client.post('/analysis/start', data={
            'acquirer': 'Example Acquirer', 'target': 'Example Target',
            'objective': 'Full acquisition investigation', 'scopes': ['financial']
        })
        analysis = created.json()['analysis']
        response = self.client.get(f"/analysis/{analysis['analysis_id']}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Ask Arc', response.text)
        self.assertNotIn('open-ask', response.text)

    def test_landing_and_internal_navigation_labels(self):
        body = self.client.get('/').text
        self.assertNotIn('<nav', body)
        self.assertNotIn('Qloo', body)
        for label in ['Acquisition Analysis', 'Business Insights', 'Discovery', 'Start Acquisition Analysis']:
            self.assertIn(label, body)
        for route in ['/dashboard', '/analyst', '/owner', '/discovery', '/analysis/new']:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertIn('<nav aria-label="Primary">', response.text)
            self.assertNotIn('class="eyebrow"', response.text)
            self.assertNotIn('class="kicker"', response.text)
        self.assertIn('Discover the top 5 companies aligned with the company you’re looking at.', self.client.get('/discovery').text)
        self.assertNotIn('Business Insights answers', self.client.get('/owner').text)
        self.assertIn('aria-label="Open app tour"', self.client.get('/dashboard').text)

    def test_unauthenticated_routes_redirect_to_sign_in(self):
        client = TestClient(app, follow_redirects=False)
        for route in ['/analysis/new', '/owner', '/discovery', '/dashboard']:
            response = client.get(route)
            self.assertEqual(response.status_code, 303)
            self.assertIn('/login?next=', response.headers.get('location', ''))
        response = client.post('/discovery/api/comparables', json={'sector': 'Retail'})
        self.assertEqual(response.status_code, 401)

    def test_single_demo_account_uses_normal_signin_fields(self):
        page = TestClient(app, follow_redirects=False).get('/login')
        self.assertEqual(page.status_code, 200)
        self.assertIn('name="email"', page.text)
        self.assertIn('name="password"', page.text)
        self.assertNotIn(DEMO_EMAIL, page.text)
        self.assertNotIn(DEMO_PASSWORD, page.text)
        self.assertNotIn('Continue with demo account', page.text)
        signup = self.client.get('/signup')
        self.assertEqual(signup.status_code, 303)


if __name__ == '__main__':
    unittest.main()


def test_business_insights_api_requires_a_searched_company_and_does_not_pass_hidden_filters():
    original = dashboard._agent
    captured = {}
    class CaptureInsights:
        async def research_business_insights(self, args):
            captured.update(args)
            return {'insights': {'company': args['company'], 'business_overview': 'Overview', 'sources': []}, 'search_activity': []}
    dashboard._agent = CaptureInsights()
    try:
        with TestClient(app, follow_redirects=False) as client:
            client.post('/login', data={'email': DEMO_EMAIL, 'password': DEMO_PASSWORD, 'next': '/owner'})
            response = client.post('/owner/api/insights', json={'company':'Example Co','sector':'Retail','geography':'Canada'})
            blank = client.post('/owner/api/insights', json={})
        assert response.status_code == 200
        assert captured == {'company': 'Example Co'}
        assert blank.status_code == 400
        assert 'previously searched company' in blank.json()['detail']
    finally:
        dashboard._agent = original
