from __future__ import annotations

import io
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors


def build_report_pdf(analysis: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.65*inch, leftMargin=0.65*inch, topMargin=0.65*inch, bottomMargin=0.65*inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ArcTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=22, leading=27, spaceAfter=10))
    styles.add(ParagraphStyle(name='ArcH2', parent=styles['Heading2'], fontSize=13, leading=17, spaceBefore=12, spaceAfter=7))
    styles.add(ParagraphStyle(name='ArcBody', parent=styles['BodyText'], fontSize=9.5, leading=14, spaceAfter=6))
    styles.add(ParagraphStyle(name='ArcSmall', parent=styles['BodyText'], fontSize=7.5, leading=10, textColor=colors.HexColor('#555555')))
    story: list[Any] = []
    acq, tgt = analysis.get('acquirer', ''), analysis.get('target', '')
    story.append(Paragraph('ARC', styles['ArcSmall']))
    story.append(Paragraph('M&A Analysis Report', styles['ArcTitle']))
    story.append(Paragraph(f'{_esc(acq)}  x  {_esc(tgt)}', styles['ArcH2']))
    story.append(Paragraph(_esc((analysis.get('report') or {}).get('executive_summary') or analysis.get('agent_output') or 'No executive summary was returned.'), styles['ArcBody']))
    story.append(Spacer(1, 8))

    scores = analysis.get('overview', {})
    table_data = [['Dimension', 'Assessment']]
    for key, label in [('strategic_fit','Strategic fit'), ('cultural_alignment','Cultural alignment'), ('audience_expansion','Audience expansion'), ('financial_fit','Financial fit'), ('integration_risk','Integration risk')]:
        table_data.append([label, _esc(scores.get(key) if scores.get(key) is not None else 'Insufficient evidence')])
    table = Table(table_data, colWidths=[2.3*inch, 4.2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#111111')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#cccccc')),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(table)

    for title, section in [
        ('Key findings', analysis.get('findings', [])),
        ('Risks', analysis.get('risks', {}).get('items', []) if isinstance(analysis.get('risks'), dict) else analysis.get('risks', [])),
        ('Growth opportunities', analysis.get('opportunities', [])),
        ('Diligence questions', analysis.get('diligence_questions', [])),
    ]:
        story.append(Paragraph(title, styles['ArcH2']))
        items = section or []
        if not items:
            story.append(Paragraph('No supported findings in this section.', styles['ArcBody']))
        for item in items[:12]:
            if isinstance(item, dict):
                heading = item.get('title') or item.get('name') or 'Finding'
                body = item.get('body') or item.get('rationale') or item.get('question') or ''
                story.append(Paragraph(f'<b>{_esc(heading)}</b>', styles['ArcBody']))
                story.append(Paragraph(_esc(body), styles['ArcBody']))
            else:
                story.append(Paragraph(_esc(item), styles['ArcBody']))

    story.append(Paragraph('Cultural intelligence', styles['ArcH2']))
    cultural = analysis.get('cultural') or {}
    story.append(Paragraph(f'<b>Acquirer entities:</b> {_esc(", ".join(_entity_names(cultural.get("acquirer_entities", []))) or "Not available")}', styles['ArcBody']))
    story.append(Paragraph(f'<b>Target entities:</b> {_esc(", ".join(_entity_names(cultural.get("target_entities", []))) or "Not available")}', styles['ArcBody']))
    story.append(Paragraph(f'<b>Shared affinities:</b> {_esc(", ".join(map(str, cultural.get("shared", [])))) or "Not established"}', styles['ArcBody']))
    story.append(Paragraph(f'<b>Distinct territory:</b> {_esc(", ".join(map(str, cultural.get("distinct", [])))) or "Not established"}', styles['ArcBody']))

    story.append(Spacer(1, 12))
    story.append(Paragraph('Diligence boundary: Arc provides decision support. Material findings should be validated through conventional financial, legal, tax, HR, operational and commercial diligence.', styles['ArcSmall']))
    doc.build(story)
    return buffer.getvalue()


def _esc(value: Any) -> str:
    text = str(value if value is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text.replace('\n', '<br/>')


def _entity_names(values: Any) -> list[str]:
    names: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            label = value.get('name') or value.get('title') or value.get('entity_id')
            if label:
                names.append(str(label))
        elif value:
            names.append(str(value))
    return names
