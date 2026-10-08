import os
import asyncio
import tempfile
import unittest
from pathlib import Path

os.environ['GEMINI_API_KEY'] = 'test'
os.environ['QLOO_API_KEY'] = 'test'
os.environ['ARC_DB_PATH'] = str(Path(tempfile.gettempdir()) / 'arc_integration.sqlite3')

from app.main import app
from app.services import analysis_service
from app.services.agent_service import ArcAgent
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
        self.client = TestClient(app)

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
        aid = analysis_service.create_analysis('Acquirer', 'Target', 'Assess fit', ['financial','business','cultural','integration'])
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


if __name__ == '__main__':
    unittest.main()
