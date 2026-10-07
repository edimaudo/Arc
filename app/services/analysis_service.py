from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import MAX_TOOL_TURNS
from app.db import init_db, load_analyses, load_analysis, save_analysis
from app.services.agent_service import ArcAgent

init_db()
_AGENT = ArcAgent()


def list_analyses() -> list[dict[str, Any]]:
    return load_analyses()


def get_analysis(analysis_id: str) -> dict[str, Any]:
    analysis = load_analysis(analysis_id)
    if not analysis:
        raise KeyError(analysis_id)
    return analysis


def get_latest_analysis() -> dict[str, Any] | None:
    items = list_analyses()
    return items[0] if items else None


def create_analysis(acquirer: str, target: str, objective: str, scopes: list[str]) -> str:
    analysis_id = f'analysis-{uuid.uuid4().hex[:10]}'
    now = datetime.now(timezone.utc).isoformat()
    base = {
        'analysis_id': analysis_id,
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
    save_analysis(base)
    return analysis_id


async def run_investigation(analysis_id: str) -> dict[str, Any]:
    analysis = get_analysis(analysis_id)
    analysis['status'] = 'Investigation in progress'
    save_analysis(analysis)
    goal = {
        'acquirer': analysis['acquirer'],
        'target': analysis['target'],
        'objective': analysis.get('objective', 'Full acquisition investigation'),
        'scopes': analysis.get('scopes', ['financial', 'business', 'cultural', 'integration']),
        'documents': analysis.get('documents', []),
    }
    try:
        result = await _AGENT.run(goal, max_turns=MAX_TOOL_TURNS)
    except Exception as exc:
        analysis['status'] = 'Investigation failed'
        analysis['error'] = str(exc)
        save_analysis(analysis)
        raise

    analysis['status'] = 'Investigation complete'
    analysis['completed_at'] = datetime.now(timezone.utc).isoformat()
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
        'integration_risk': scores.get('integration_risk', analysis['overview'].get('integration_risk')),
    }
    analysis['overview'].update({k: v for k, v in score_map.items() if v is not None})
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
    analysis['cultural'] = result.get('cultural', analysis['cultural'])
    analysis['qloo_evidence'] = result.get('qloo_evidence', {})
    save_analysis(analysis)
    return analysis
