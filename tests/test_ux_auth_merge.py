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
    for expected in ['Start M&amp;A analysis', 'M&amp;A Analysis', 'Business Insights', 'Discovery']:
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
    assert 'Annual revenue' in html
    assert 'Estimated company valuation' in html
    assert 'Number of employees' in html
    assert 'Acquisition thesis' not in html
    assert 'Start M&amp;A analysis' not in html
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
    assert 'Recent M&amp;A analyses' in html
    assert 'data-delete-analysis' in html
    assert 'Open company research, review recent M&amp;A analyses, or discover comparable businesses.' not in html


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


def test_business_insights_history_dropdown_and_no_auto_research_on_load():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        html = client.get('/owner').text
    assert 'insight-company-select' in html
    assert 'Research report' not in html
    assert 'populateCompanyHistory' in html
    assert 'restore();' not in html


def test_discovery_does_not_show_or_run_saved_results_on_page_load():
    with TestClient(app, follow_redirects=False) as client:
        client.post('/demo-login', data={'next': '/dashboard'})
        html = client.get('/discovery').text
    assert 'Need a business diagnosis?' not in html
    boot = html[html.find('  (async () => {', html.find('function fillCriteria')): ]
    assert 'form.requestSubmit()' not in boot
    assert 'showResults(latestDiscovery.comparables' not in html
