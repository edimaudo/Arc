from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import MAX_TOOL_TURNS
from app.services.agent_service import ArcAgent
from app.services.api_errors import friendly_api_error

_AGENT = ArcAgent()
logger = logging.getLogger(__name__)


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
    try:
        # Documents enrich the investigation; they never gate public-source research.
        result = await _AGENT.run(goal, max_turns=MAX_TOOL_TURNS)
        if not any(result.get(section) for section in ('findings', 'risks', 'opportunities', 'report')):
            raise RuntimeError('The research provider returned no usable structured findings.')
        if not result.get('findings'):
            summary = str((result.get('report') or {}).get('executive_summary') or result.get('summary') or '').strip()
            if summary and not summary.startswith('{'):
                result['findings'] = [{'type': 'Finding', 'title': 'Executive summary', 'body': summary, 'evidence': 'See report and available source evidence for supporting detail.'}]
            else:
                item = next(iter(result.get('opportunities') or result.get('risks') or []), None)
                if isinstance(item, dict):
                    result['findings'] = [{'type': item.get('type', 'Finding'), 'title': item.get('title', 'Preliminary finding'), 'body': item.get('body') or item.get('detail') or item.get('rationale') or 'Review the supporting evidence and open questions.', 'evidence': item.get('evidence', 'See supporting report sections.')}]
    except Exception as exc:
        logger.exception('Live acquisition research failed; returning a clearly labelled starter analysis.')
        result = _limited_investigation(analysis, friendly_api_error(exc, 'Live research service'))

    analysis['status'] = 'Limited analysis — live research unavailable' if result.get('limited_mode') else 'Investigation complete'
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
        'integration_risk': scores.get('integration_risk', 'Pending'),
    }
    analysis.setdefault('overview', {}).update(score_map)
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
    analysis['limited_mode'] = bool(result.get('limited_mode'))
    if result.get('limited_mode'):
        analysis['service_notice'] = result.get('service_notice', 'Live research is temporarily unavailable.')
        analysis.setdefault('overview', {})['integration_risk'] = 'Not assessed'
    else:
        analysis.pop('service_notice', None)
    return analysis


def _limited_investigation(analysis: dict[str, Any], notice: str) -> dict[str, Any]:
    """Create useful, non-fabricated diligence guidance when live research is down."""
    acquirer = str(analysis.get('acquirer') or 'Acquirer')
    target = str(analysis.get('target') or 'Target')
    documents = analysis.get('documents') or []
    has_documents = bool(documents)
    extracted_metrics: dict[str, Any] = {}
    document_excerpts: list[str] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        if isinstance(document.get('metrics'), dict):
            extracted_metrics.update({k: v for k, v in document['metrics'].items() if v is not None})
        snippet = str(document.get('text') or '').strip()
        if snippet:
            document_excerpts.append(f"{document.get('filename') or 'Uploaded document'}: {snippet[:900]}")
    source_note = (
        'Uploaded documents are available for review, but the live research service did not return a report. '
        'The document text is retained in the saved analysis; retry to complete automated synthesis.'
        if has_documents else
        'No supporting documents were uploaded and live public research could not be reached. This is a starter diligence framework, not a verified company-specific assessment.'
    )
    findings = [
        {'type': 'Finding', 'title': 'Establish the financial baseline', 'body': f'Compare {acquirer} and {target} on revenue scale, growth, gross and EBITDA margins, cash conversion, debt, working capital and customer concentration. No current figures have been verified in this limited run.', 'evidence': 'Requires financial statements or reliable public filings.'},
        {'type': 'Finding', 'title': 'Compare products, customers and markets', 'body': 'Map each company’s core products, customer segments, sales channels, geographic reach and competitive position before concluding whether the businesses are complementary or overlapping.', 'evidence': 'Requires verified company and market sources.'},
        {'type': 'Finding', 'title': 'Check cultural and audience overlap', 'body': 'Assess brand perception, customer interests, employee expectations and differences in operating style. No cultural alignment score is assigned without supporting evidence.', 'evidence': 'Cultural assessment not completed in this run.'},
    ]
    risks = [
        {'type': 'Risk', 'title': 'Financial comparability is unverified', 'body': 'Growth, margins, leverage, cash conversion and working-capital needs remain unconfirmed. Do not treat the missing values as zero or infer a financial-fit score.'},
        {'type': 'Risk', 'title': 'Commercial overlap is not established', 'body': 'Customer overlap, product substitutability, channel conflict and geographic fit require evidence before any synergy estimate can be relied on.'},
        {'type': 'Risk', 'title': 'Integration effort is not assessed', 'body': 'Technology, people, culture, systems, regulatory obligations and customer retention have not been evaluated in this limited run.'},
    ]
    opportunities = [
        {'title': 'Test product and channel complementarity', 'body': 'Determine whether either company can reach new customers or improve distribution through the other’s products and channels; estimate benefits only after validating the underlying assumptions.'},
        {'title': 'Identify scale and capability gaps', 'body': 'Compare capabilities, supplier leverage, geography and operational maturity to identify areas worth deeper investigation, without presuming that savings or growth will materialize.'},
    ]
    if document_excerpts:
        findings.insert(0, {'type': 'Finding', 'title': 'Uploaded material retained for review', 'body': 'The following extracted content is available in the browser-saved analysis, but the live research provider was unavailable for full synthesis: ' + ' | '.join(document_excerpts[:3]), 'evidence': 'Uploaded source documents; verify extracted text against the original files.'})
    questions = [
        'What are each company’s latest revenue, gross margin, EBITDA, free cash flow, net debt and working-capital requirements?',
        'Which customer groups, products, regions and sales channels overlap or complement one another?',
        'What evidence supports expected growth, cost efficiencies or revenue opportunities?',
        'What technology, talent, culture, legal or operational changes would be required to combine the businesses?',
        'Which assumptions need confirmation from management, public filings or independent diligence?',
    ]
    summary = f'Preliminary review of {acquirer} and {target}: live company research is unavailable. Arc has prepared the key financial, commercial, cultural and integration questions to validate next. No company-specific scores or factual claims have been fabricated.'
    return {
        'limited_mode': True, 'service_notice': notice, 'status': 'limited', 'output': summary, 'summary': summary,
        'activity': [], 'findings': findings, 'risks': risks, 'opportunities': opportunities, 'diligence_questions': questions,
        'scores': {'strategic_fit': None, 'cultural_fit': None, 'audience_expansion': None, 'financial_fit': None, 'integration_risk': 'Not assessed'},
        'financial': {'revenue_growth': extracted_metrics.get('revenue_growth'), 'ebitda_margin': extracted_metrics.get('ebitda_margin'), 'net_debt_to_ebitda': extracted_metrics.get('net_debt_to_ebitda'), 'customer_concentration': extracted_metrics.get('customer_concentration'), 'assessment': 'Live synthesis is unavailable. Values shown here were extracted from uploaded documents only; confirm them against the source files.' if extracted_metrics else 'No verified financial evidence was available in this run.'},
        'business': {'model': 'Not yet verified', 'market': 'Not yet verified', 'strategic_rationale': 'Assess product adjacency, customer overlap, channel complementarity and geography after public-source research is available.', 'open_questions': questions[:3]},
        'cultural': {'acquirer_entities': [], 'target_entities': [], 'shared': [], 'distinct': [], 'qloo_metrics': {}, 'evidence': []},
        'qloo_evidence': {},
        'report': {'executive_summary': summary + ' ' + source_note, 'deal_fit': {}, 'key_risks': risks, 'growth_opportunities': opportunities, 'next_steps': questions, 'disclaimer': 'Limited mode: this report contains a diligence framework only. Validate all material findings through reliable sources and conventional diligence.', 'service_notice': notice},
    }
