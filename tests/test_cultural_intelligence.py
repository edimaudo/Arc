"""Regression tests for Qloo-led cultural intelligence across Arc workspaces."""
import asyncio
import os
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("QLOO_API_KEY", "test-key")

from app.services.agent_service import ArcAgent


class FakeQloo:
    async def search(self, query, types=None, take=8):
        return {"entities": [{
            "entity_id": f"brand:{query.lower().replace(' ', '-')}",
            "name": query,
            "type": "urn:entity:brand",
            "properties": {},
        }]}

    async def insights(self, entity_ids, filter_type, location=None, take=20):
        label = filter_type.rsplit(":", 1)[-1].replace("_", " ").title()
        unique = entity_ids[0].split(":", 1)[-1]
        return {
            "query": {"explainability": {"input_entity_influence": {entity_ids[0]: 0.82}, "top_5": 0.78}},
            "results": [
                {"entity_id": f"shared:{label}", "name": f"Shared {label} Interest", "type": filter_type, "affinity": 0.84,
                 "query": {"explainability": {"input_entity_influence": {entity_ids[0]: 0.84}}}},
                {"entity_id": f"unique:{unique}:{label}", "name": f"Distinct {unique} {label}", "type": filter_type, "affinity": 0.71,
                 "query": {"explainability": {"input_entity_influence": {entity_ids[0]: 0.71}}}},
            ],
        }

    async def compare(self, a_entities, b_entities, filter_types=None, model="descriptive", take=20):
        return {"results": [
            {"entity_id": "compare:shared-audience", "name": "Cross-company affinity", "type": "urn:entity:brand", "affinity": 0.78},
        ]}


def test_mna_qloo_preflight_resolves_company_entities_and_builds_shared_distinct_profiles():
    agent = ArcAgent()
    agent.qloo = FakeQloo()
    seed = asyncio.run(agent._seed_qloo_context({"acquirer": "Northstar Foods", "target": "Maple Market", "geography": "Canada"}))

    assert seed["acquirer"][0]["name"] == "Northstar Foods"
    assert seed["target"][0]["name"] == "Maple Market"
    assert seed["cultural_status"] == "available"
    assert seed["shared_affinities"]
    assert seed["acquirer_distinctive"]
    assert seed["target_distinctive"]
    assert seed["comparison"]["results"][0]["affinity"] == 0.78


def test_mna_does_not_turn_qloo_recommendation_affinities_into_a_fit_score():
    agent = ArcAgent()
    agent.api_key = "test-key"
    agent.qloo = FakeQloo()

    async def grounded(prompt):
        return {
            "data": {
                "summary": "Evidence-based initial report.",
                "findings": [{"type": "Finding", "title": "Market context", "body": "Public sources reviewed.", "evidence": "Grounded search"}],
                "risks": [], "opportunities": [], "diligence_questions": [],
                "scores": {"cultural_fit": 99, "cultural_alignment": 99},
                "financial": {}, "business": {}, "cultural": {"profile_summary": "Cultural summary."},
                "qloo_evidence": {}, "report": {"executive_summary": "Evidence-based initial report."},
            },
            "steps": [],
        }

    agent._web_search_json = grounded
    result = asyncio.run(agent.run({"acquirer": "Northstar Foods", "target": "Maple Market", "scopes": ["cultural"]}))

    assert result["scores"]["cultural_fit"] is None
    assert result["scores"]["cultural_alignment"] is None
    assert result["cultural"]["qloo_signals"]["status"] == "available"
    assert result["cultural"]["qloo_signals"]["shared_affinities"]
    first_category = result["cultural"]["qloo_signals"]["acquirer_profile"]["categories"][0]
    assert first_category["explainability"]["input_entity_influence"]
    assert first_category["results"][0]["explainability"]["input_entity_influence"]


def test_qloo_cultural_signals_survive_gemini_outage():
    agent = ArcAgent()
    agent.api_key = "test-key"
    agent.qloo = FakeQloo()

    async def unavailable(prompt):
        raise RuntimeError("Gemini API is temporarily unavailable")

    agent._web_search_json = unavailable
    result = asyncio.run(agent.run({"acquirer": "Northstar Foods", "target": "Maple Market", "scopes": ["cultural"]}))

    assert result["limited_mode"] is True
    assert result["cultural"]["qloo_signals"]["status"] == "available"
    assert result["cultural"]["qloo_signals"]["shared_affinities"]
    assert result["scores"]["cultural_fit"] is None
    assert "public-source research is unavailable" in result["summary"]


def test_business_insights_and_discovery_both_include_qloo_culture():
    agent = ArcAgent()
    agent.api_key = "test-key"
    agent.qloo = FakeQloo()

    async def grounded(prompt):
        if 'Discover EXACTLY the top 5 real operating companies' in prompt:
            data = {"comparables": [{
                "name": "Comparable One", "sector": "Consumer", "geography": "Canada",
                "business_summary": "Consumer brand.", "comparability_reason": "Similar scale and sector.",
                "cultural_context": {"brand_positioning": "Community oriented"}, "sources": [],
            }]}
        else:
            data = {"company": "Northstar Foods", "sector": "Consumer", "business_overview": "A consumer business.",
                    "cultural_context": {"consumer_identity_signals": ["Interest in local food culture"]}, "sources": []}
        return {"data": data, "steps": []}

    agent._web_search_json = grounded
    business = asyncio.run(agent.research_business_insights({"company": "Northstar Foods", "geography": "Canada"}))
    discovery = asyncio.run(agent.find_comparable_companies({"reference_company": "Northstar Foods", "sector": "Consumer", "geography": "Canada"}))

    assert business["insights"]["cultural_intelligence"]["qloo_profile"]["status"] == "available"
    assert business["insights"]["cultural_intelligence"]["public_context"]["consumer_identity_signals"]
    peer = discovery["comparables"][0]
    assert peer["cultural_context"]["brand_positioning"] == "Community oriented"
    assert peer["cultural_intelligence"]["status"] == "available"
    assert peer["cultural_intelligence"]["signals"]


def test_all_three_workspaces_show_disabled_getting_results_and_cultural_sections():
    root = Path(__file__).parents[1] / "app" / "templates"
    analysis = (root / "analysis.html").read_text(encoding="utf-8")
    business = (root / "owner.html").read_text(encoding="utf-8")
    discovery = (root / "discovery.html").read_text(encoding="utf-8")

    assert "runButton.disabled = true" in analysis
    assert "runButton.textContent = 'Getting results…'" in analysis
    assert "Common cultural affinities" in analysis
    assert "Cultural categories" in analysis
    assert "Shared Qloo signals" not in analysis
    assert "Why Qloo surfaced this" not in analysis
    assert "qloo_signals" in analysis  # internal data key only; the vendor is not named in visible copy
    assert "Qloo" not in analysis
    assert "button.disabled = true; button.setAttribute('aria-busy', 'true'); button.textContent = 'Getting results…'" in business
    assert "Culture, audience and brand affinity" in business
    assert "button.disabled = true; button.setAttribute('aria-busy','true'); button.classList.add('is-loading'); button.textContent = 'Getting results…'" in discovery
    assert "Cultural profile" in discovery
    assert "Cross-company cultural signals" not in discovery  # Discovery is about peer lists, not the backend mechanism
    assert "Qloo" not in business
    assert "Qloo" not in discovery


def test_business_insights_keeps_qloo_culture_when_gemini_is_unavailable():
    agent = ArcAgent()
    agent.api_key = "test-key"
    agent.qloo = FakeQloo()

    async def unavailable(prompt):
        raise RuntimeError("Gemini API is temporarily unavailable")

    agent._web_search_json = unavailable
    result = asyncio.run(agent.research_business_insights({"company": "Northstar Foods", "geography": "Canada"}))
    report = result["insights"]

    assert report["research_status"] == "limited"
    assert "not verified" in report["business_overview"]
    assert report["cultural_intelligence"]["qloo_profile"]["status"] == "available"
    assert report["cultural_intelligence"]["qloo_profile"]["categories"]


def test_discovery_returns_top_five_and_considers_all_scale_criteria():
    agent = ArcAgent()
    agent.api_key = "test-key"
    captured = {}

    async def grounded(prompt):
        captured["prompt"] = prompt
        return {"data": {"comparables": [
            {"name": f"Peer {i}", "annual_revenue_estimate": f"${i} million", "company_valuation_estimate": f"${i * 2} million", "employee_count_estimate": i * 10, "sources": []}
            for i in range(1, 8)
        ]}, "steps": []}

    async def enrich(peers, reference, geography):
        captured["enriched_count"] = len(peers)
        captured["geography"] = geography
        return [dict(peer, cultural_intelligence={"status": "available"}) for peer in peers]

    agent._web_search_json = grounded
    agent._enrich_comparables_with_culture = enrich
    result = asyncio.run(agent.find_comparable_companies({
        "reference_company": "Reference Co",
        "geography": "North America (Canada and United States)",
    }))

    assert len(result["comparables"]) == 5
    assert captured["enriched_count"] == 5
    assert captured["geography"] == "North America (Canada and United States)"
    prompt = captured["prompt"]
    assert "EXACTLY the top 5" in prompt
    assert "annual revenue" in prompt and "company valuation" in prompt and "employee count" in prompt
    assert "Canada and the United States" in prompt


def test_business_insights_prompt_always_covers_all_focus_areas():
    agent = ArcAgent()
    agent.api_key = "test-key"
    captured = {}

    async def grounded(prompt):
        captured["prompt"] = prompt
        return {"data": {"company": "Northstar Foods", "business_overview": "Overview", "current_trends": [],
                         "competitive_landscape": [], "customer_and_product_signals": [], "growth_opportunities": [],
                         "business_risks": [], "recommended_actions": [], "key_metrics_to_watch": [], "sources": []}, "steps": []}

    async def qloo_profile(subject, geography):
        return {"status": "available", "subject": subject, "matched_entities": [], "categories": [], "top_affinities": []}

    agent._web_search_json = grounded
    agent._qloo_profile_for_query = qloo_profile
    asyncio.run(agent.research_business_insights({"company": "Northstar Foods", "geography": "Canada", "focus": "Market and competitors"}))
    prompt = captured["prompt"]
    assert "Cover every business area in the schema on every run" in prompt
    assert "FOCUS:" not in prompt
    for required in ["business_overview", "current_trends", "competitive_landscape", "customer_and_product_signals", "growth_opportunities", "business_risks", "recommended_actions", "key_metrics_to_watch", "cultural_context"]:
        assert required in prompt
