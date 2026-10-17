from pathlib import Path

ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / 'app' / 'templates'


def test_discovery_does_not_display_company_count_after_search():
    html = (TEMPLATES / 'discovery.html').read_text(encoding='utf-8')
    assert 'id="results-count"' not in html
    assert "count.textContent" not in html
    assert 'Top 5 aligned companies' in html


def test_business_insights_does_not_repeat_recommended_action_reason():
    html = (TEMPLATES / 'owner.html').read_text(encoding='utf-8')
    assert 'function normalizedText(value)' in html
    assert 'normalizedText(v.reason) !== normalizedText(detail)' in html
    assert 'normalizedText(detail) !== normalizedText(heading)' in html


def test_business_insights_has_separate_wrapping_identity_and_timestamp():
    html = (TEMPLATES / 'owner.html').read_text(encoding='utf-8')
    css = (ROOT / 'app' / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert 'business-report-identity' in html
    assert 'business-report-subtitle' in html
    assert 'business-report-meta' in html
    assert 'Research completed' not in html
    assert 'grid-template-columns: minmax(0, 1fr) max-content' in css
    assert 'overflow-wrap: anywhere' in css
    assert 'white-space: normal' in css
