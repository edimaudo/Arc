"""Regression tests to ensure the corrected Arc UX ships with demo auth."""
import os
from pathlib import Path

os.environ.setdefault('GEMINI_API_KEY', 'test-key')
os.environ.setdefault('QLOO_API_KEY', 'test-key')

from fastapi.testclient import TestClient
from app.main import app
from app.auth import DEMO_EMAIL, DEMO_PASSWORD


def test_public_landing_uses_correct_product_cards_and_no_internal_navigation():
    with TestClient(app, follow_redirects=False) as client:
        response = client.get('/')
    assert response.status_code == 200
    html = response.text
    for expected in ['Start Acquisition Analysis', 'Acquisition Analysis', 'Business Insights', 'Discovery']:
        assert expected in html
    for forbidden in ['Find Companies', 'Business Owner', 'Financial Intelligence', 'Business Intelligence', 'Cultural Intelligence', 'Acquisition Intelligence', 'Qloo Intelligence']:
        assert forbidden not in html
    # Public page exposes account access, but not internal workspace nav labels.
    assert '>Sign in<' in html
    assert 'href="/dashboard"' not in html
    assert '>Dashboard<' not in html
    assert '>Analyst<' not in html


def test_templates_have_no_eyebrow_or_kicker_elements():
    template_root = Path(__file__).parents[1] / 'app' / 'templates'
    for path in template_root.glob('*.html'):
        source = path.read_text(encoding='utf-8').lower()
        assert 'class="eyebrow' not in source, path.name
        assert 'class="kicker' not in source, path.name


def test_signin_is_a_normal_email_and_password_form():
    with TestClient(app, follow_redirects=False) as client:
        page = client.get('/login')
        assert page.status_code == 200
        assert 'name="email"' in page.text
        assert 'name="password"' in page.text
        assert 'Continue with demo account' not in page.text
        assert DEMO_EMAIL not in page.text
        assert DEMO_PASSWORD not in page.text
        signed_in = client.post('/login', data={'email':DEMO_EMAIL, 'password':DEMO_PASSWORD, 'next':'/dashboard'})
        assert signed_in.status_code == 303
        assert signed_in.headers['location'] == '/dashboard'
        dashboard = client.get('/dashboard')
        assert dashboard.status_code == 200
        assert 'Dashboard' in dashboard.text


def test_protected_analysis_redirects_to_signin_with_return_path():
    with TestClient(app, follow_redirects=False) as client:
        response = client.get('/analysis/new')
    assert response.status_code == 303
    assert response.headers['location'].startswith('/login?next=')


def test_analysis_document_upload_is_optional_and_no_storage_implementation_leaks_into_ui():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        response = client.get('/analysis/new')
        assert response.status_code == 200
        assert 'Supporting documents (optional)' in response.text
        assert 'Run investigation' not in response.text
        assert 'PDF, XLSX, XLSM, or CSV' in response.text
        assert 'Optional · PDF' not in response.text
        assert 'You can run an analysis without uploading any documents' not in response.text
        assert 'IndexedDB' not in response.text
        detail = client.get('/analysis/example')
        assert 'IndexedDB' not in detail.text


def test_discovery_is_standalone_comparable_company_research():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        response = client.get('/discovery')
    assert response.status_code == 200
    html = response.text
    assert 'Find comparable companies' in html
    assert 'ArcStore.allAnalyses()' in html
    assert 'source_context_id' in html
    assert 'id=\"reference-company\"' in html
    assert 'id=\"geography\"' in html
    assert 'North America (Canada and United States)' in html
    assert 'id=\"size-metric\"' not in html
    assert 'id=\"size-band\"' not in html
    assert 'Comparable size' not in html
    assert 'Acquisition thesis' not in html
    assert 'Start Acquisition Analysis' not in html
    assert 'Investigate' not in html


def test_business_insights_is_company_research_not_mna_summary():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        response = client.get('/owner')
    assert response.status_code == 200
    html = response.text
    for expected in ['Business Insights', 'Market trends', 'Research business', 'Growth opportunities', 'Business risks']:
        assert expected in html
    assert 'IndexedDB' not in html
    assert 'Strategic fit' not in html
    assert 'Acquisition thesis' not in html
    assert 'ArcStore.allAnalyses()' in html
    assert 'Researching the business' in html


def test_walkthrough_is_available_in_public_and_signed_in_layouts():
    with TestClient(app, follow_redirects=False) as client:
        public = client.get('/')
        client.post('/demo-login', data={'next': '/dashboard'})
        signed_in = client.get('/dashboard')
    for html in [public.text, signed_in.text]:
        assert 'data-tour-open' in html
        assert 'id="arc-tour"' in html
        assert 'Skip walkthrough' in html



def test_dashboard_lists_all_analyses_and_provides_delete_control():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        html = client.get('/dashboard').text
    assert 'Recent acquisition analyses' in html
    assert 'data-delete-analysis' in html
    assert 'Open company research, review recent Acquisition analyses, or discover comparable businesses.' not in html


def test_mna_and_cultural_ui_does_not_expose_provider_or_shared_provider_metric():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        created = client.post('/analysis/start', data={'acquirer':'Example Buyer','target':'Example Target','objective':'Full acquisition investigation','scopes':['financial']})
        analysis_id = created.json()['analysis']['analysis_id']
        pages = [client.get(f'/analysis/{analysis_id}').text, client.get('/discovery').text, client.get('/owner').text]
    for html in pages:
        assert 'Qloo' not in html
    assert 'Shared Qloo signals' not in pages[0]
    assert 'Cultural categories' in pages[0]


def test_business_insights_uses_one_company_field_and_does_not_auto_research_on_load():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        html = client.get('/owner').text
    assert 'id=\"insight-company\"' in html
    assert 'insight-company-select' not in html
    assert 'Previously searched company' not in html
    assert 'Business Insights answers' not in html
    assert 'Best for understanding one business' not in html
    assert 'Research report' not in html
    assert 'prefillCompanyContext' in html
    assert 'form.requestSubmit()' in html  # only the explicit retry control uses this; load does not submit


def test_discovery_does_not_show_or_run_saved_results_on_page_load():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        html = client.get('/discovery').text
    assert 'Need a business diagnosis?' not in html
    assert 'id=\"reference-company\"' in html
    assert 'id=\"discovery-results\" hidden' in html
    assert 'showResults(result.comparables,criteria)' in html
    assert 'showResults(latestDiscovery.comparables' not in html
    assert 'form.requestSubmit()' in html  # explicit retry after a failed user-triggered search


def test_acquisition_analysis_labels_sticky_tabs_and_no_print_controls():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        landing = client.get('/').text
        nav = client.get('/analyst').text
        created = client.post('/analysis/start', data={'acquirer':'Example Buyer','target':'Example Target','objective':'Full acquisition investigation','scopes':['financial']})
        detail = client.get(f"/analysis/{created.json()['analysis']['analysis_id']}").text
    assert 'Acquisition Analysis' in landing and 'Acquisition Analysis' in nav
    assert 'M&amp;A Analysis' not in landing + nav + detail
    assert 'analysis-tabs' in detail
    assert 'data-culture-tab="acquirer"' in detail
    assert 'data-culture-tab="target"' in detail
    assert 'data-culture-tab="cross-company"' in detail
    assert 'data-culture-tab="implications"' in detail
    assert 'initAnalysisNavigation' in detail
    assert 'Analyst activity' not in detail
    assert 'Diligence boundary' not in detail
    report_service = (Path(__file__).parents[1] / 'app' / 'services' / 'report_service.py').read_text(encoding='utf-8')
    assert 'Diligence boundary' not in report_service
    assert 'activity' not in detail
    assert '/100' not in detail
    assert 'position: sticky' in (Path(__file__).parents[1] / 'app' / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    for forbidden in ['id="print-analysis"', 'Print report', '>Print<', 'window.print()']:
        assert forbidden not in detail


def test_company_dropdowns_only_use_companies_from_saved_search_results():
    root = Path(__file__).parents[1] / 'app' / 'templates'
    owner = (root / 'owner.html').read_text(encoding='utf-8')
    discovery = (root / 'discovery.html').read_text(encoding='utf-8')
    assert '<select id="insight-company"' in owner
    assert "addCompany(c.company, context)" in owner
    assert "addCompany(c.company || item.insights?.company" not in owner
    assert '<select id="reference-company"' in discovery
    assert 'id="refresh-shortlist" type="submit" disabled' in discovery
    assert "if (!a.completed_at) continue;" in discovery
    assert "__custom__" not in discovery
    assert "custom-company" not in discovery
    assert "Enter another company" not in discovery
    assert "item.insights?.company" not in discovery
    # Result-only competitors and suggested peers must not leak into either company picker.
    assert "for (const competitor of array(item.insights?.competitive_landscape)) addCompany" not in discovery
    assert "for (const peer of array(item.comparables)) addCompany" not in discovery
    assert "for (const competitor of array(item.insights?.competitive_landscape)) addCompany" not in owner
    assert "for (const peer of array(item.comparables)) addCompany" not in owner
    assert "addCompany(c.company,context)" in discovery
    assert "addCompany(c.reference_company,context)" in discovery
    assert "addCompany(c.company, context)" in owner
    assert "addCompany(c.reference_company, context)" in owner


def test_acquisition_cultural_tabs_hide_nonselected_panels_and_track_section_scroll():
    root = Path(__file__).parents[1] / 'app' / 'templates'
    analysis = (root / 'analysis.html').read_text(encoding='utf-8')
    css = (Path(__file__).parents[1] / 'app' / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert 'data-culture-tab="acquirer"' in analysis
    assert 'data-culture-tab="target"' in analysis
    assert 'data-culture-tab="cross-company"' in analysis
    assert 'data-culture-tab="implications"' in analysis
    assert "panel.hidden = panel.dataset.culturePanel !== key" in analysis
    assert "new IntersectionObserver" in analysis
    assert ".analysis-tabs a.active" in css
    assert "Math.round(n >= 0 && n <= 1 ? n * 100 : n)}%`" in analysis
    assert "text.match(/^(-?\\d+(?:\\.\\d+)?)\\s*\\/\\s*100(?:\\s+affinity)?$/i)" in analysis
    assert "const scoreNumber = value =>" in analysis
    assert "`${Math.round(score)}%`" in analysis
