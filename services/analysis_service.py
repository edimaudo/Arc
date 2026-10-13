from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import MAX_TOOL_TURNS
from app.services.agent_service import ArcAgent

_AGENT = ArcAgent()


def create_analysis(acquirer: str, target: str, objective: str, scopes: list[str], owner_id: str | None = None) -> dict[str, Any]:
    """Create an analysis payload. The browser persists it in IndexedDB."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        'analysis_id': f'analysis-{uuid.uuid4().hex[:10]}',
        'owner_id': owner_id or 'arc-demo-user',
        'acquirer': acquirer,
        'target': target,
        'status': 'Ready to investigate',
        'overview': {
            'strategic_fit': None,
            'cultural_alignment': None,
            'audience_expansion': None,
            'financial_fit': None,
            'integration_risk': 'Pending',
        },
        'findings': [],
        'risks': {'items': []},
        'opportunities': [],
        'diligence_questions': [],
        'cultural': {
            'acquirer_entities': [], 'target_entities': [], 'shared': [], 'distinct': [],
            'qloo_metrics': {}, 'evidence': [],
        },
        'financial': {},
        'business': {},
        'activity': [],
        'objective': objective,
        'scopes': scopes,
        'documents': [],
        'report': None,
        'created_at': now,
        'updated_at': now,
    }


async def run_investigation(source: dict[str, Any]) -> dict[str, Any]:
    """Run against a client-supplied analysis. No server-side persistence is used."""
    analysis = dict(source)
    analysis_id = str(analysis.get('analysis_id') or '')
    if not analysis_id or not str(analysis.get('acquirer') or '').strip() or not str(analysis.get('target') or '').strip():
        raise ValueError('The saved analysis is missing its ID, acquirer, or target. Reopen it from this browser and try again.')
    analysis['status'] = 'Investigation in progress'
    analysis['updated_at'] = datetime.now(timezone.utc).isoformat()
    goal = {
        'acquirer': analysis['acquirer'],
        'target': analysis['target'],
        'objective': analysis.get('objective', 'Full acquisition investigation'),
        'scopes': analysis.get('scopes', ['financial', 'business', 'cultural', 'integration']),
        'documents': analysis.get('documents', []),
    }
    result = await _AGENT.run(goal, max_turns=MAX_TOOL_TURNS)

    analysis['status'] = 'Investigation complete'
    analysis['completed_at'] = datetime.now(timezone.utc).isoformat()
    analysis['updated_at'] = analysis['completed_at']
    analysis['activity'] = result.get('activity', [])
    analysis['agent_output'] = result.get('output', '')
    analysis['findings'] = result.get('findings', analysis.get('findings', []))
    analysis['risks'] = {'items': result.get('risks', analysis.get('risks', {}).get('items', []))}
    analysis['opportunities'] = result.get('opportunities', analysis.get('opportunities', []))
    analysis['diligence_questions'] = result.get('diligence_questions', analysis.get('diligence_questions', []))

    scores = result.get('scores', {}) or {}
    score_map = {
        'strategic_fit': scores.get('strategic_fit'),
        'cultural_alignment': scores.get('cultural_alignment', scores.get('cultural_fit')),
        'audience_expansion': scores.get('audience_expansion'),
        'financial_fit': scores.get('financial_fit'),
        'integration_risk': scores.get('integration_risk', analysis.get('overview', {}).get('integration_risk', 'Pending')),
    }
    analysis.setdefault('overview', {}).update({k: v for k, v in score_map.items() if v is not None})
    analysis['report'] = result.get('report') or {
        'executive_summary': result.get('summary') or result.get('output', ''),
        'deal_fit': {k: v for k, v in score_map.items() if v is not None},
        'key_risks': analysis.get('risks', {}).get('items', []),
        'growth_opportunities': analysis.get('opportunities', []),
        'next_steps': analysis.get('diligence_questions', []),
        'disclaimer': 'AI-generated decision support; validate material findings through conventional diligence.'
    }
    analysis['financial'] = result.get('financial', {})
    analysis['business'] = result.get('business', {})
    analysis['cultural'] = result.get('cultural', analysis.get('cultural', {}))
    analysis['qloo_evidence'] = result.get('qloo_evidence', {})
    return analysis
