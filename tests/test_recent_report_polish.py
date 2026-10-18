from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_discovery_does_not_render_company_count():
    source = (ROOT / "app/templates/discovery.html").read_text(encoding="utf-8")
    assert 'id="results-count"' not in source
    assert "count.textContent" not in source
    assert "Top 5 aligned companies" in source


def test_recommended_actions_deduplicate_heading_and_detail():
    source = (ROOT / "app/templates/owner.html").read_text(encoding="utf-8")
    assert "const normalize = value =>" in source
    assert "normalize(value) !== normalize(heading)" in source
    assert "const extra = candidates.slice(1).find" in source
    # The former implementation rendered the reason twice: once via textItem and again explicitly.
    assert "${v.reason ? `<p class=\"muted\">${esc(v.reason)}</p>` : ''}" not in source


def test_business_report_has_separate_wrapping_metadata_and_single_timestamp():
    source = (ROOT / "app/templates/owner.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/css/app.css").read_text(encoding="utf-8")
    assert "business-report-meta-main" in source
    assert "business-report-meta-detail" in source
    assert 'grid-template-areas: "title timestamp" "meta meta"' in css
    assert "Research completed ${esc(savedAt" not in source
    assert "Updated ${esc(savedAt)}" in source
    assert "overflow-wrap: anywhere" in css
