import asyncio
import os
import tempfile
import unittest
from pathlib import Path

os.environ['GEMINI_API_KEY'] = 'unit-test'
os.environ['QLOO_API_KEY'] = 'unit-test'
os.environ['ARC_DB_PATH'] = str(Path(tempfile.gettempdir()) / 'arc_unit.sqlite3')

from app.db import init_db
from app.services.agent_service import ArcAgent
from app.services.analysis_service import create_analysis, get_analysis
from app.services.document_service import parse_document
from app.services.discovery_service import explain_score


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_financial_requires_evidence(self):
        result = asyncio.run(ArcAgent().calculate_financial_fit({'metrics': {'ebitda_margin': 0.22}}))
        self.assertIsNone(result['financial_fit'])
        self.assertEqual(result['status'], 'insufficient_evidence')

    def test_candidate_score(self):
        result = explain_score({'strategic_fit': 80, 'cultural_fit': 90, 'audience_expansion': 70, 'financial_fit': 60})
        self.assertEqual(result['overall_fit'], 77)
        self.assertEqual(result['components']['cultural_fit'], 90)

    def test_document_metrics(self):
        data = b'revenue growth,12%\nebitda margin,22%\nnet debt / ebitda,1.8\ncustomer concentration,24%\n'
        parsed = parse_document('metrics.csv', data)
        self.assertEqual(parsed['metrics']['revenue_growth'], 0.12)
        self.assertEqual(parsed['metrics']['ebitda_margin'], 0.22)
        self.assertEqual(parsed['metrics']['net_debt_to_ebitda'], 1.8)

    def test_persistence(self):
        aid = create_analysis('A', 'B', 'Test', ['financial'])
        loaded = get_analysis(aid)
        self.assertEqual(loaded['acquirer'], 'A')
        self.assertIsNone(loaded['overview']['strategic_fit'])


if __name__ == '__main__':
    unittest.main()
