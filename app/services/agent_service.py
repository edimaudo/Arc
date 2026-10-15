from __future__ import annotations

import asyncio
import json
import re
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

import httpx

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS
from app.qloo.client import QlooAPIError, QlooClient

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ArcAgent:
    """Arc's live tool-using acquisition analyst.

    Gemini is responsible for selecting and sequencing tools. The application
    executes those tools server-side. Qloo is the cultural-intelligence source;
    Google Search is used for current public-company research.
    """

    def __init__(self) -> None:
        self.api_key = GEMINI_API_KEY
        self.model = GEMINI_MODEL
        self.qloo = QlooClient()
        self._company_research_cache: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, ToolHandler] = {
            "qloo_lookup_entities": self.qloo_lookup_entities,
            "qloo_cultural_insights": self.qloo_cultural_insights,
            "qloo_compare_footprints": self.qloo_compare_footprints,
            "qloo_trending_signals": self.qloo_trending_signals,
            "search_company_information": self.search_company_information,
            "find_potential_targets": self.find_potential_targets,
            "calculate_financial_fit": self.calculate_financial_fit,
            "score_acquisition_candidate": self.score_acquisition_candidate,
        }

    def _require_gemini(self) -> None:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

    @property
    def tool_declarations(self) -> list[dict[str, Any]]:
        return [
            {"type": "google_search"},
            {
                "type": "function", "name": "qloo_lookup_entities",
                "description": "Resolve company, brand, product, person, place, media or other cultural names into Qloo entity IDs. Use before Qloo analysis. You may provide a company name and several cultural proxy names.",
                "parameters": {"type": "object", "properties": {
                    "queries": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "types": {"type": "array", "items": {"type": "string"}}
                }, "required": ["queries"]},
            },
            {
                "type": "function", "name": "qloo_cultural_insights",
                "description": "Use Qloo Insights for a cultural or audience view grounded in resolved Qloo entity IDs. Use documented filter types only.",
                "parameters": {"type": "object", "properties": {
                    "entity_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "filter_type": {"type": "string", "enum": ["urn:entity:brand", "urn:entity:artist", "urn:entity:book", "urn:entity:movie", "urn:entity:tv_show", "urn:entity:place", "urn:entity:destination", "urn:entity:person"]},
                    "location": {"type": "string"}
                }, "required": ["entity_ids", "filter_type"]},
            },
            {
                "type": "function", "name": "qloo_compare_footprints",
                "description": "Compare two groups of resolved Qloo entities. Use descriptive and, when useful, predictive models to identify shared territory and meaningful audience/cultural differences.",
                "parameters": {"type": "object", "properties": {
                    "acquirer_entity_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "target_entity_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "filter_types": {"type": "array", "items": {"type": "string"}},
                    "model": {"type": "string", "enum": ["descriptive", "predictive"]}
                }, "required": ["acquirer_entity_ids", "target_entity_ids"]},
            },
            {
                "type": "function", "name": "qloo_trending_signals",
                "description": "Use Qloo Trending to inspect the cultural momentum of resolved entities over a recent date window.",
                "parameters": {"type": "object", "properties": {
                    "entity_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "filter_type": {"type": "string"},
                    "start_date": {"type": "string"}, "end_date": {"type": "string"}
                }, "required": ["entity_ids", "filter_type", "start_date", "end_date"]},
            },
            {
                "type": "function", "name": "search_company_information",
                "description": "Research current public information about a company. Use Google Search grounding internally and return business model, products, audience, competitors, geography, financial evidence, brands, and sources. Do not invent missing data.",
                "parameters": {"type": "object", "properties": {
                    "company": {"type": "string"},
                    "questions": {"type": "array", "items": {"type": "string"}, "minItems": 1}
                }, "required": ["company", "questions"]},
            },
            {
                "type": "function", "name": "find_potential_targets",
                "description": "Run a grounded market search for companies that match sector, geography, and stated business criteria. Return real companies only.",
                "parameters": {"type": "object", "properties": {
                    "acquirer": {"type": "string"}, "sector": {"type": "string"}, "geography": {"type": "string"}, "business_criteria": {"type": "string"}
                }, "required": ["acquirer", "sector", "geography", "business_criteria"]},
            },
            {
                "type": "function", "name": "calculate_financial_fit",
                "description": "Calculate a deterministic financial-fit score from supplied evidence. Never fill missing financial metrics with defaults.",
                "parameters": {"type": "object", "properties": {
                    "metrics": {"type": "object", "additionalProperties": {"type": "number"}}
                }, "required": ["metrics"]},
            },
            {
                "type": "function", "name": "score_acquisition_candidate",
                "description": "Calculate an explainable overall acquisition-fit score from component scores. Use only after evidence has been gathered.",
                "parameters": {"type": "object", "properties": {
                    "strategic_fit": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                    "cultural_fit": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                    "audience_expansion": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                    "financial_fit": {"type": ["number", "null"], "minimum": 0, "maximum": 100}
                }, "required": ["strategic_fit", "cultural_fit", "audience_expansion", "financial_fit"]},
            },
        ]

    async def run(self, goal: dict[str, Any], max_turns: int = 12) -> dict[str, Any]:
        """Produce the first-pass acquisition report in one grounded Gemini request.

        Public-source synthesis and the bounded Qloo preflight run concurrently. This
        replaces the previous multi-turn tool-planning loop for the initial report,
        which could require many sequential model round trips before showing results.
        """
        # Let the public-source request fail inside gather so Qloo can still return
        # cultural evidence when Gemini credentials or availability are a problem.
        documents = []
        for item in goal.get("documents", []) or []:
            if not isinstance(item, dict):
                continue
            documents.append({
                "filename": str(item.get("filename") or "Uploaded document"),
                "metrics": item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
                "text": str(item.get("text") or "")[:6000],
            })
        brief = {
            "acquirer": str(goal.get("acquirer") or "").strip(),
            "target": str(goal.get("target") or "").strip(),
            "objective": goal.get("objective") or "Full acquisition investigation",
            "scopes": goal.get("scopes") or ["financial", "business", "cultural", "integration"],
            "documents": documents,
        }
        prompt = (
            "You are Arc, an acquisition diligence analyst. Produce a useful first-pass report about both named companies in one response. "
            "Use current Google Search grounding for each company, its industry, competitive position and publicly disclosed financial evidence. "
            "Uploaded documents are optional. If none are present, research both companies anyway. If documents are present, use their extracted text and "
            "metrics as additional evidence, distinguish management-provided data from public facts, and flag conflicts or missing support. "
            "Never invent facts, figures, URLs, quotations, sources or Qloo results. Keep unsupported numeric scores null and state evidence gaps. "
            "Return valid JSON only with these keys: summary, findings, risks, opportunities, diligence_questions, scores, financial, business, cultural, qloo_evidence, report. "
            "findings must be a list of objects with type, title, body and evidence; risks and opportunities must be concise lists of objects with title, body and evidence where available; "
            "diligence_questions must be a list of practical questions. scores may contain strategic_fit, cultural_fit, audience_expansion, financial_fit and integration_risk, "
            "but use null or 'Not assessed' wherever public evidence is insufficient. financial must contain revenue_growth, ebitda_margin, net_debt_to_ebitda, customer_concentration and assessment, "
            "using only sourced or uploaded values. business must contain model, market, strategic_rationale and open_questions. cultural must be a substantive section, not a placeholder, containing profile_summary, acquirer_profile, target_profile, audience_signals, brand_positioning, shared_cultural_territory, differentiated_cultural_territory, audience_expansion_opportunities, cultural_integration_risks, practical_implications and source_evidence. Each signal should explain what was observed, why it matters commercially, and the evidence limitation. "
            "but do not attribute anything to Qloo; the application will attach Qloo entity evidence separately. report must contain executive_summary, deal_fit, key_risks, "
            "growth_opportunities, next_steps, sources and disclaimer. Make findings specific to these companies rather than generic diligence advice.\n\n"
            "ASSIGNMENT:\n" + json.dumps(brief, ensure_ascii=False)
        )

        async def bounded_qloo_seed() -> dict[str, Any]:
            scopes = {str(scope).lower() for scope in brief["scopes"]}
            if "cultural" not in scopes:
                return {"acquirer": [], "target": [], "comparison": {}, "errors": ["Cultural analysis was not requested."]}
            try:
                return await asyncio.wait_for(self._seed_qloo_context(brief), timeout=6.5)
            except Exception as exc:
                return {"acquirer": [], "target": [], "comparison": {}, "errors": [self._safe_error(exc)]}

        search_result, seed = await asyncio.gather(
            self._web_search_json(prompt), bounded_qloo_seed(), return_exceptions=True
        )
        if isinstance(seed, BaseException) or not isinstance(seed, dict):
            seed = {"acquirer": [], "target": [], "comparison": {}, "errors": ["Qloo context was unavailable."],
                    "acquirer_profile": {}, "target_profile": {}, "shared_affinities": [],
                    "acquirer_distinctive": [], "target_distinctive": [], "cultural_status": "unavailable"}
        if isinstance(search_result, BaseException):
            qloo_has_signals = bool(
                seed.get("comparison", {}).get("results")
                or seed.get("shared_affinities")
                or seed.get("acquirer_profile", {}).get("top_affinities")
                or seed.get("target_profile", {}).get("top_affinities")
            )
            if qloo_has_signals:
                return self._qloo_only_report(brief, seed, self._safe_error(search_result))
            raise search_result
        if not isinstance(search_result, dict) or not isinstance(search_result.get("data"), dict):
            raise RuntimeError("Grounded acquisition research returned no structured result.")
        parsed = search_result["data"]
        activity = list(search_result.get("steps") or [])

        result = self._normalize_result(json.dumps(parsed, ensure_ascii=False), parsed, activity)
        cultural = result.get("cultural") if isinstance(result.get("cultural"), dict) else {}
        cultural["acquirer_entities"] = seed.get("acquirer", [])
        cultural["target_entities"] = seed.get("target", [])
        cultural["qloo_signals"] = {
            "status": seed.get("cultural_status", "unavailable"),
            "acquirer_profile": seed.get("acquirer_profile", {}),
            "target_profile": seed.get("target_profile", {}),
            "comparison": seed.get("comparison", {}),
            "shared_affinities": seed.get("shared_affinities", []),
            "acquirer_distinctive": seed.get("acquirer_distinctive", []),
            "target_distinctive": seed.get("target_distinctive", []),
            "errors": seed.get("errors", []),
            "methodology": "Qloo affinity recommendations and group comparisons are directional cultural signals, not a measure of revenue, market share, or guaranteed customer overlap.",
        }
        result["cultural"] = cultural
        result["qloo_evidence"] = {"preflight": seed, **(result.get("qloo_evidence") or {})}
        if seed.get("acquirer") or seed.get("target") or seed.get("comparison"):
            activity.append({"tool": "qloo_preflight", "status": "complete", "result": "Qloo company-entity and cultural comparison context attached."})
        elif seed.get("errors"):
            activity.append({"tool": "qloo_preflight", "status": "limited", "result": "Qloo context unavailable; cultural findings are limited to public-source evidence."})
        # Qloo returns affinity recommendations, not a single company-to-company
        # compatibility percentage. Keep the old score empty and show observed shared
        # signals in the UI instead of turning recommendation affinities into a fit score.
        result.setdefault("scores", {})["cultural_fit"] = None
        result["scores"]["cultural_alignment"] = None
        result["activity"] = activity
        return result

    def _qloo_only_report(self, goal: dict[str, Any], seed: dict[str, Any], notice: str) -> dict[str, Any]:
        """Keep genuine Qloo culture evidence visible when Gemini is unavailable."""
        acquirer = str(goal.get("acquirer") or "Acquirer")
        target = str(goal.get("target") or "Target")
        shared = list(seed.get("shared_affinities") or [])
        acquirer_only = list(seed.get("acquirer_distinctive") or [])
        target_only = list(seed.get("target_distinctive") or [])
        compare = seed.get("comparison") if isinstance(seed.get("comparison"), dict) else {}
        findings = []
        for item in shared[:6]:
            name = str(item.get("name") or "Shared affinity")
            category = str(item.get("category") or "cultural category")
            findings.append({
                "type": "Finding", "title": f"Shared cultural affinity: {name}",
                "body": f"Qloo returned {name} as an affinity signal for both companies in {category.lower()}. This is a possible audience or brand adjacency to investigate, not proof that customers overlap.",
                "evidence": "Qloo Insights affinity recommendations for the matched company entities.",
            })
        if not findings:
            for profile_name, profile in (("Acquirer", seed.get("acquirer_profile", {})), ("Target", seed.get("target_profile", {}))):
                for item in (profile.get("top_affinities") or [])[:3]:
                    findings.append({
                        "type": "Finding", "title": f"{profile_name} cultural signal: {item.get('name') or 'Affinity'}",
                        "body": f"Qloo returned this affinity for the {profile_name.lower()}. Compare its relevance against the other company and validate with customer and brand evidence.",
                        "evidence": f"Qloo {item.get('category') or item.get('type') or 'affinity'} recommendation; not a direct customer or revenue metric.",
                    })
        if not findings:
            findings = [{"type": "Finding", "title": "Cultural evidence is incomplete", "body": "Qloo entity matches were found, but the provider did not return enough affinity recommendations to describe shared cultural territory. Do not infer alignment from missing data.", "evidence": "Qloo preflight response; public-source research was unavailable."}]
        risks = [
            {"type": "Risk", "title": "Public-company research is unavailable", "body": f"Gemini public-source research could not complete: {notice}. Financial and commercial findings are not verified in this response."},
            {"type": "Risk", "title": "Cultural affinity is not customer overlap", "body": "Qloo signals indicate affinity relationships. Validate them with first-party customer data, brand research and market evidence before estimating revenue impact."},
        ]
        questions = [
            "Which customer segments, communities and cultural interests are actually shared across both customer bases?",
            "Do shared Qloo affinities support a measurable product, brand or channel opportunity?",
            "Which distinctive audience preferences should each brand retain after integration?",
            "What current financial, customer-retention and operating evidence is needed to complete the review?",
        ]
        summary = f"Limited acquisition review for {acquirer} and {target}. Gemini public-source research is unavailable; Arc retained the Qloo cultural signals available for this run. Financial, commercial and integration conclusions remain unverified."
        cultural = {
            "profile_summary": "Qloo cultural data is available, but public-source research could not complete. Treat affinities as directional hypotheses, not verified customer overlap.",
            "acquirer_entities": seed.get("acquirer", []), "target_entities": seed.get("target", []),
            "shared_cultural_territory": shared, "differentiated_cultural_territory": {"acquirer": acquirer_only, "target": target_only},
            "audience_signals": [], "brand_positioning": [], "audience_expansion_opportunities": [],
            "cultural_integration_risks": risks[1:], "practical_implications": questions,
            "qloo_signals": {
                "status": seed.get("cultural_status", "partial"),
                "acquirer_profile": seed.get("acquirer_profile", {}), "target_profile": seed.get("target_profile", {}),
                "comparison": compare, "shared_affinities": shared,
                "acquirer_distinctive": acquirer_only, "target_distinctive": target_only,
                "errors": seed.get("errors", []),
                "methodology": "Qloo affinity recommendations and group comparisons are directional cultural signals, not direct measures of revenue, market share or guaranteed customer overlap.",
            },
        }
        return {
            "status": "limited", "limited_mode": True, "service_notice": notice,
            "output": summary, "summary": summary, "activity": [{"tool": "qloo_preflight", "status": "complete", "result": "Qloo culture preserved while public research is unavailable."}],
            "findings": findings, "risks": risks, "opportunities": [], "diligence_questions": questions,
            "scores": {"strategic_fit": None, "cultural_fit": None, "cultural_alignment": None, "audience_expansion": None, "financial_fit": None, "integration_risk": "Not assessed"},
            "financial": {"assessment": "Not assessed: live public-source research is unavailable."},
            "business": {"model": "Not verified", "market": "Not verified", "strategic_rationale": "Not assessed", "open_questions": questions},
            "cultural": cultural, "qloo_evidence": {"preflight": seed},
            "report": {"executive_summary": summary, "deal_fit": {}, "key_risks": risks, "growth_opportunities": [], "next_steps": questions, "disclaimer": "Limited mode: only available Qloo culture signals are reported. Validate all material business and financial claims with independent sources.", "service_notice": notice},
        }

    async def _resolve_company_entities(self, query: str) -> list[dict[str, Any]]:
        """Prefer Qloo brand entities for companies, then fall back to broader entity search."""
        query = str(query or "").strip()
        if not query:
            return []
        try:
            brand_lookup = await asyncio.wait_for(self.qloo_lookup_entities({"queries": [query], "types": ["urn:entity:brand"]}), timeout=2.4)
            branded = brand_lookup.get("entities", [])
            if branded:
                return branded[:3]
        except Exception:
            pass
        try:
            fallback = await asyncio.wait_for(self.qloo_lookup_entities({"queries": [query]}), timeout=2.4)
            return fallback.get("entities", [])[:3]
        except Exception:
            return []

    async def _seed_qloo_context(self, goal: dict[str, Any]) -> dict[str, Any]:
        """Resolve the companies and fetch Qloo affinity signals across cultural categories."""
        seed: dict[str, Any] = {
            "acquirer": [], "target": [], "comparison": {}, "errors": [],
            "acquirer_profile": {}, "target_profile": {}, "shared_affinities": [],
            "acquirer_distinctive": [], "target_distinctive": [], "cultural_status": "unavailable",
        }
        try:
            acq, tgt = await asyncio.gather(
                self._resolve_company_entities(goal["acquirer"]),
                self._resolve_company_entities(goal["target"]),
                return_exceptions=True,
            )
            if isinstance(acq, BaseException):
                seed["errors"].append(self._safe_error(acq))
            else:
                # _resolve_company_entities returns the normalized list directly.
                seed["acquirer"] = acq[:3]
            if isinstance(tgt, BaseException):
                seed["errors"].append(self._safe_error(tgt))
            else:
                seed["target"] = tgt[:3]

            a_ids = [x["entity_id"] for x in seed["acquirer"] if x.get("entity_id")]
            b_ids = [x["entity_id"] for x in seed["target"] if x.get("entity_id")]
            tasks, names = [], []
            if a_ids:
                tasks.append(self._qloo_affinity_categories(a_ids, goal.get("geography"), timeout=2.8))
                names.append("acquirer_profile")
            if b_ids:
                tasks.append(self._qloo_affinity_categories(b_ids, goal.get("geography"), timeout=2.8))
                names.append("target_profile")
            if a_ids and b_ids:
                tasks.append(asyncio.wait_for(self.qloo.compare(
                    a_ids, b_ids,
                    ["urn:entity:brand", "urn:entity:artist", "urn:entity:place", "urn:entity:movie", "urn:entity:tv_show"],
                    "descriptive", 12,
                ), timeout=3.1))
                names.append("comparison")
            if tasks:
                values = await asyncio.gather(*tasks, return_exceptions=True)
                for name, value in zip(names, values):
                    if isinstance(value, BaseException):
                        seed["errors"].append(f"{name.replace('_', ' ').title()} unavailable: {self._safe_error(value)}")
                    elif name == "comparison":
                        seed[name] = self._compact_qloo(value, include_affinity=True)
                    else:
                        seed[name] = value
            # Retain entity names alongside Qloo IDs so explainability can be rendered
            # in human terms rather than exposing opaque identifiers in the UI.
            seed["acquirer_profile"] = {**seed["acquirer_profile"], "matched_entities": [
                {"entity_id": item.get("entity_id"), "name": item.get("name")} for item in seed["acquirer"]
            ]}
            seed["target_profile"] = {**seed["target_profile"], "matched_entities": [
                {"entity_id": item.get("entity_id"), "name": item.get("name")} for item in seed["target"]
            ]}
            shared, acquirer_only, target_only = self._compare_affinity_profiles(seed["acquirer_profile"], seed["target_profile"])
            seed["shared_affinities"] = shared
            seed["acquirer_distinctive"] = acquirer_only
            seed["target_distinctive"] = target_only
            if shared or acquirer_only or target_only or seed.get("comparison", {}).get("results"):
                seed["cultural_status"] = "available"
            elif seed.get("acquirer_profile", {}).get("available_categories") or seed.get("target_profile", {}).get("available_categories"):
                seed["cultural_status"] = "partial"
        except Exception as exc:
            seed["errors"].append(self._safe_error(exc))
        return seed

    async def _qloo_affinity_categories(
        self, entity_ids: list[str], location: str | None = None,
        timeout: float = 2.8, filter_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get Qloo affinity recommendations across cultural categories concurrently."""
        labels = {
            "urn:entity:brand": "Brands",
            "urn:entity:artist": "Music and artists",
            "urn:entity:place": "Places and destinations",
            "urn:entity:movie": "Films",
            "urn:entity:tv_show": "TV shows",
        }
        selected = filter_types or list(labels)

        async def get_one(entity_type: str) -> dict[str, Any]:
            try:
                raw = await asyncio.wait_for(self.qloo.insights(entity_ids, entity_type, location, 8), timeout=timeout)
                compact = self._compact_qloo(raw, include_affinity=True)
                rows = [{
                    "entity_id": row.get("entity_id"), "name": row.get("name"),
                    "type": row.get("type") or entity_type, "affinity": row.get("affinity"),
                    "explainability": row.get("explainability"),
                } for row in compact.get("results", [])[:8] if row.get("name")]
                query_meta = compact.get("query") if isinstance(compact.get("query"), dict) else {}
                explainability = query_meta.get("explainability")
                return {"entity_type": entity_type, "label": labels.get(entity_type, entity_type), "results": rows,
                        "explainability": explainability, "status": "available" if rows else "empty"}
            except Exception as exc:
                return {"entity_type": entity_type, "label": labels.get(entity_type, entity_type), "results": [], "status": "unavailable", "error": self._safe_error(exc)}

        categories = await asyncio.gather(*(get_one(entity_type) for entity_type in selected))
        flat = [{**row, "category": category["label"]} for category in categories for row in category.get("results", [])]
        flat.sort(key=lambda item: item.get("affinity") if isinstance(item.get("affinity"), (int, float)) else -1, reverse=True)
        available = sum(1 for category in categories if category.get("results"))
        return {
            "status": "available" if available else "unavailable", "categories": categories,
            "top_affinities": flat[:15], "available_categories": available,
            "errors": [category["error"] for category in categories if category.get("error")][:4],
            "basis": "Qloo Insights affinity recommendations based on the resolved input entities.",
        }

    @staticmethod
    def _compare_affinity_profiles(a_profile: dict[str, Any], b_profile: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        def flatten(profile):
            rows = []
            for category in profile.get("categories", []) if isinstance(profile, dict) else []:
                for item in category.get("results", []):
                    name = str(item.get("name") or "").strip()
                    if name:
                        rows.append({"name": name, "category": category.get("label", "Cultural signal"), "affinity": item.get("affinity"), "entity_id": item.get("entity_id")})
            return rows
        a_rows, b_rows = flatten(a_profile), flatten(b_profile)
        def key(item):
            return (str(item.get("category") or "").casefold(), str(item.get("name") or "").casefold())
        a_map, b_map = {key(item): item for item in a_rows}, {key(item): item for item in b_rows}
        shared = [dict(a_map[k], target_affinity=b_map[k].get("affinity")) for k in a_map.keys() & b_map.keys()]
        a_only = [item for k, item in a_map.items() if k not in b_map]
        b_only = [item for k, item in b_map.items() if k not in a_map]
        for values in (shared, a_only, b_only):
            values.sort(key=lambda item: item.get("affinity") if isinstance(item.get("affinity"), (int, float)) else -1, reverse=True)
        return shared[:12], a_only[:12], b_only[:12]

    async def _qloo_profile_for_query(self, query: str, location: str | None = None, filter_types: list[str] | None = None) -> dict[str, Any]:
        """Create a Qloo cultural profile for a company or industry query."""
        query = str(query or "").strip()
        if not query:
            return {"status": "unavailable", "subject": query, "matched_entities": [], "categories": [], "top_affinities": [], "note": "No company or industry was supplied."}
        try:
            entities = (await self._resolve_company_entities(query))[:2]
            ids = [entity["entity_id"] for entity in entities if entity.get("entity_id")]
            if not ids:
                return {"status": "unavailable", "subject": query, "matched_entities": [], "categories": [], "top_affinities": [], "note": "Qloo did not return a confident entity match for this query."}
            profile = await self._qloo_affinity_categories(ids, location, timeout=2.8, filter_types=filter_types)
            return {**profile, "subject": query, "matched_entities": [{"name": item.get("name"), "type": item.get("type"), "entity_id": item.get("entity_id")} for item in entities], "note": "Affinities are directional taste signals for the matched entity, not direct customer or sales measurements."}
        except Exception as exc:
            return {"status": "unavailable", "subject": query, "matched_entities": [], "categories": [], "top_affinities": [], "errors": [self._safe_error(exc)], "note": "Qloo cultural signals could not be loaded for this query."}

    async def _enrich_comparables_with_culture(self, comparables: list[dict[str, Any]], reference: str, geography: str) -> list[dict[str, Any]]:
        """Attach Qloo cultural context to a bounded peer set without inventing a score."""
        if not comparables:
            return comparables
        subset = comparables[:4]
        async def resolve(name: str) -> list[dict[str, Any]]:
            if not name:
                return []
            try:
                return (await self._resolve_company_entities(name))[:2]
            except Exception:
                return []
        lookup_tasks = [resolve(str(item.get("name") or "").strip()) for item in subset]
        if reference:
            reference_task = resolve(reference)
            resolved = await asyncio.gather(reference_task, *lookup_tasks, return_exceptions=True)
            reference_entities = resolved[0] if isinstance(resolved[0], list) else []
            peer_entities = [value if isinstance(value, list) else [] for value in resolved[1:]]
        else:
            reference_entities, peer_entities = [], [value if isinstance(value, list) else [] for value in await asyncio.gather(*lookup_tasks, return_exceptions=True)]
        reference_ids = [item.get("entity_id") for item in reference_entities if item.get("entity_id")]

        async def enrich(item: dict[str, Any], matches: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
            name = str(item.get("name") or "").strip()
            matched_ids = [entry.get("entity_id") for entry in matches if entry.get("entity_id")]
            if not matched_ids:
                return name, {"status": "unavailable", "note": "Qloo did not return a matching company entity. Public-source cultural context remains shown above."}
            try:
                if reference_ids:
                    raw = await asyncio.wait_for(self.qloo.compare(
                        reference_ids, matched_ids,
                        ["urn:entity:brand", "urn:entity:artist", "urn:entity:place", "urn:entity:movie", "urn:entity:tv_show"],
                        "descriptive", 10,
                    ), timeout=2.8)
                    compact = self._compact_qloo(raw, include_affinity=True)
                    signals = [{"name": row.get("name"), "type": row.get("type"), "affinity": row.get("affinity"), "explainability": row.get("explainability")} for row in compact.get("results", []) if row.get("name")][:8]
                    aggregate = compact.get("query", {}).get("explainability") if isinstance(compact.get("query"), dict) else None
                    return name, {"status": "available" if signals else "partial", "reference_match": [entry.get("name") for entry in reference_entities], "company_match": [entry.get("name") for entry in matches], "reference_match_entities": [{"entity_id": entry.get("entity_id"), "name": entry.get("name")} for entry in reference_entities], "company_match_entities": [{"entity_id": entry.get("entity_id"), "name": entry.get("name")} for entry in matches], "signals": signals, "explainability": aggregate, "note": "Qloo compared the resolved reference and peer entities across cultural categories. This is directional taste context, not a score of company value or deal suitability."}
                profile = await self._qloo_affinity_categories(matched_ids, geography, timeout=2.5, filter_types=["urn:entity:brand", "urn:entity:artist", "urn:entity:place"])
                return name, {"status": profile.get("status", "unavailable"), "matched_entities": [{"name": entry.get("name"), "type": entry.get("type")} for entry in matches], "categories": profile.get("categories", []), "top_affinities": profile.get("top_affinities", [])[:8], "note": "Qloo profile for the peer; use as directional cultural context, not evidence of direct customer overlap."}
            except Exception as exc:
                return name, {"status": "unavailable", "signals": [], "note": "Qloo comparison is temporarily unavailable.", "errors": [self._safe_error(exc)]}

        enriched_values = await asyncio.gather(*(enrich(item, peer_entities[index]) for index, item in enumerate(subset)), return_exceptions=True)
        mapped = {value[0].casefold(): value[1] for value in enriched_values if isinstance(value, tuple) and value[0]}
        enriched = []
        for item in comparables:
            copy = dict(item)
            copy["cultural_intelligence"] = mapped.get(str(item.get("name") or "").casefold(), {"status": "not_run", "note": "Public-source cultural context is available; Qloo cross-check was not run for this peer in this pass."})
            enriched.append(copy)
        return enriched

    async def _create_interaction(self, goal: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "system_instruction": self._system_prompt(goal),
            "input": "Investigate this acquisition assignment using public-source research even when no documents are provided. Documents are optional supporting evidence, not a prerequisite. Always produce a useful report from verified public sources; when documents are provided, analyze them, reconcile them with public facts, and clearly flag conflicts or missing evidence. Do not invent company facts, scores, financial metrics, URLs or sources.\n\nUSER GOAL:\n" + json.dumps(goal, ensure_ascii=False),
            "tools": self.tool_declarations,
        }
        return await self._post_interaction(payload)

    async def _continue(self, interaction: dict[str, Any], max_turns: int) -> dict[str, Any]:
        activity: list[dict[str, Any]] = []
        latest = interaction
        seen_call_ids: set[str] = set()

        exhausted = True
        for _ in range(max_turns):
            if latest.get("status") == "failed":
                raise RuntimeError(self._interaction_error(latest))
            calls = [s for s in latest.get("steps", []) if s.get("type") == "function_call" and s.get("id") not in seen_call_ids]
            activity.extend(self._built_in_activity(latest))
            if not calls:
                exhausted = False
                break
            results = []
            for call in calls:
                call_id = call.get("id") or f"call-{len(seen_call_ids)+1}"
                seen_call_ids.add(call_id)
                name = call.get("name")
                args = call.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                handler = self._handlers.get(name)
                try:
                    result = await handler(args) if handler else {"error": f"Unknown tool: {name}"}
                except Exception as exc:
                    result = {"error": self._safe_error(exc)}
                activity.append({
                    "tool": name,
                    "status": "complete" if "error" not in result else "error",
                    "input": args,
                    "result": self._activity_summary(result),
                })
                results.append({
                    "type": "function_result",
                    "name": name,
                    "call_id": call_id,
                    "result": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)[:16000]}],
                })
            latest = await self._post_interaction({
                "model": self.model,
                "previous_interaction_id": latest.get("id"),
                "input": results,
                "tools": self.tool_declarations,
            })

        if exhausted:
            synthesis = await self._post_interaction({
                "model": self.model,
                "previous_interaction_id": latest.get("id"),
                "input": "Synthesize the acquisition assessment now from the evidence already gathered. Do not call additional tools. Return the requested JSON only.",
                "tools": [],
            })
            latest = synthesis
            activity.extend(self._built_in_activity(latest))
        if latest.get("status") == "failed":
            raise RuntimeError(self._interaction_error(latest))
        output = latest.get("output_text") or self._extract_output_text(latest)
        parsed = self._parse_json_object(output)
        if not parsed:
            raise RuntimeError('Gemini returned no valid structured acquisition findings.')
        return self._normalize_result(output, parsed, activity)

    async def _web_search_json(self, prompt: str) -> dict[str, Any]:
        self._require_gemini()
        payload = {
            "model": self.model,
            "input": prompt,
            "tools": [{"type": "google_search"}],
        }
        interaction = await self._post_interaction(payload)
        if interaction.get("status") == "failed":
            raise RuntimeError(self._interaction_error(interaction))
        output = interaction.get("output_text") or self._extract_output_text(interaction)
        parsed = self._parse_json_object(output)
        if not parsed:
            raise RuntimeError("Grounded company research returned no valid structured result.")
        return {"data": parsed, "steps": self._built_in_activity(interaction)}

    async def search_company_information(self, args: dict[str, Any]) -> dict[str, Any]:
        company = str(args.get("company", "")).strip()
        if not company:
            raise ValueError("Company name is required for public-company research.")
        question_values = [str(q).strip() for q in args.get("questions", []) if str(q).strip()]
        cache_key = company.casefold() + "::" + "|".join(question_values).casefold()
        if cache_key in self._company_research_cache:
            cached = dict(self._company_research_cache[cache_key])
            cached["cached"] = True
            return cached
        questions = "\n".join(f"- {q}" for q in question_values) or "- Provide a broad company profile and current public financial evidence."
        prompt = (
            "Research the following company using Google Search grounding and answer only with verifiable public information. "
            "Return JSON only with keys company, summary, business_model, products, customers_or_audience, competitors, geography, "
            "financial_metrics, brands, sources. financial_metrics must contain only values directly supported by a source. "
            "sources must be a list of objects with title and url. Do not infer missing financial numbers.\n"
            f"COMPANY: {company}\nQUESTIONS:\n{questions}"
        )
        result = {"company": company, **(await self._web_search_json(prompt))["data"]}
        self._company_research_cache[cache_key] = dict(result)
        return result

    async def research_business_insights(self, args: dict[str, Any]) -> dict[str, Any]:
        """Research a business as an operating company, independent of an acquisition assignment."""
        company = str(args.get("company") or "").strip()
        sector = str(args.get("sector") or "").strip()
        geography = str(args.get("geography") or "Canada").strip() or "Canada"
        prompt = (
            "Produce practical, current BUSINESS INSIGHTS about the named company and/or industry. "
            "This is ordinary business research, not acquisition analysis: do not discuss acquisitions, deal fit, integration, buyers, sellers, or transaction rationale. "
            "Use Google Search grounding and return JSON only with keys: company, sector, geography, business_overview, business_model, "
            "market_position, current_trends, competitive_landscape, customer_and_product_signals, growth_opportunities, "
            "business_risks, recommended_actions, key_metrics_to_watch, cultural_context, sources. "
            "current_trends, customer_and_product_signals, growth_opportunities, business_risks, recommended_actions, and key_metrics_to_watch "
            "must be concise arrays; arrays of findings should use objects with title and detail, and recommendations should include action and reason. "
            "competitive_landscape should be an array of objects with name, summary, and website where known. "
            "cultural_context must be substantive and contain consumer_identity_signals, brand_positioning, culturally relevant trends, audience_implications, and evidence. "
            "Explain how culture, lifestyle, media, places, music, creators or community preferences affect customer behavior, brand relevance, positioning and product/marketing choices. "
            "Distinguish sourced observations from hypotheses and never stereotype demographics. "
            "sources must be a list of objects containing title and url. Ground factual claims in public sources, include useful sources, "
            "separate facts from interpretation, and never invent revenue, market share, financial metrics, URLs, or sources. "
            "For unavailable information, state that it is not publicly disclosed rather than guessing. Prioritize actionable observations over generic advice.\n"
            f"COMPANY: {company or 'Not specified'}\nSECTOR: {sector or 'Infer from company if supported'}\n"
            f"GEOGRAPHY: {geography}\n"
            "Cover every business area in the schema on every run; do not narrow the report to a single selected focus. "
        )
        subject = company or sector
        async def bounded_qloo_profile():
            try:
                return await asyncio.wait_for(self._qloo_profile_for_query(subject, geography), timeout=6.0)
            except Exception as exc:
                return {"status": "unavailable", "subject": subject, "matched_entities": [], "categories": [], "top_affinities": [], "note": "Qloo cultural signals are temporarily unavailable.", "errors": [self._safe_error(exc)]}
        search, qloo_profile = await asyncio.gather(self._web_search_json(prompt), bounded_qloo_profile(), return_exceptions=True)
        if isinstance(search, BaseException):
            if isinstance(qloo_profile, dict) and qloo_profile.get("status") == "available":
                limited_note = "Live public-source research is temporarily unavailable. Company-specific operating facts, competitor details and market claims were not verified in this response."
                return {"insights": {
                    "company": company or "Industry overview", "sector": sector, "geography": geography,
                    "business_overview": limited_note, "business_model": "Not verified", "market_position": "Not verified",
                    "current_trends": [], "competitive_landscape": [], "customer_and_product_signals": [],
                    "growth_opportunities": [], "business_risks": [], "recommended_actions": [], "key_metrics_to_watch": [],
                    "cultural_context": {},
                    "cultural_intelligence": {"public_context": {}, "qloo_profile": qloo_profile,
                        "interpretation_note": "Public-source research was unavailable. Qloo affinity recommendations are directional taste signals, not a direct measure of customer overlap, revenue or market share."},
                    "sources": [], "research_status": "limited",
                }, "search_activity": [{"tool": "qloo_business_profile", "status": "complete", "result": "Qloo culture preserved while public-source research is unavailable."}]}
            raise search
        insights = search["data"]
        insights.setdefault("company", company or "Industry overview")
        insights.setdefault("sector", sector)
        insights.setdefault("geography", geography)
        public_culture = insights.get("cultural_context") if isinstance(insights.get("cultural_context"), dict) else {}
        if isinstance(qloo_profile, BaseException):
            qloo_profile = {"status": "unavailable", "subject": subject, "matched_entities": [], "categories": [], "top_affinities": [], "note": "Qloo cultural signals are temporarily unavailable."}
        insights["cultural_intelligence"] = {"public_context": public_culture, "qloo_profile": qloo_profile, "interpretation_note": "Public-source cultural research and Qloo affinity recommendations are complementary evidence. Qloo affinity is directional and should not be read as a direct measure of customer overlap, revenue, or market share."}
        return {"insights": insights, "search_activity": search.get("steps", [])}

    async def find_comparable_companies(self, args: dict[str, Any]) -> dict[str, Any]:
        """Find the five closest peer businesses by scale, industry and cultural context."""
        reference = str(args.get("reference_company") or "").strip()
        sector = str(args.get("sector") or "").strip()
        geography = str(args.get("geography") or "North America (Canada and United States)").strip() or "North America (Canada and United States)"
        if "north america" in geography.casefold():
            geography_scope = "Canada and the United States; include either country and label each company's country."
        else:
            geography_scope = geography
        prompt = (
            "Discover EXACTLY the top 5 real operating companies aligned with the reference company. "
            "Use the reference company as the main signal and evaluate similarity across ALL available scale indicators together: annual revenue, "
            "company valuation or enterprise value, and employee count. Do not ask the user to choose one measure, and do not require all three values "
            "to be publicly disclosed. Also compare industry, business model, products and customers, then use public cultural and audience context as an "
            "important dimension. Do not rank acquisition fit, recommend an acquisition, or create a cultural-fit score. "
            "Use current Google Search grounding. Return JSON only with keys reference_company, sector, geography, comparables. Each comparable must contain "
            "name, sector, geography, website, annual_revenue_estimate, company_valuation_estimate, employee_count_estimate, business_summary, "
            "comparability_reason, cultural_context, and sources (a list of title/url objects). cultural_context should summarize sourced brand positioning, "
            "audience characteristics, relevant cultural categories and customer communities, while making clear where evidence is limited. Qloo-based cultural "
            "signals will be added separately when available. Each estimate must include currency/units and period when known; use null or 'Not publicly disclosed' "
            "when no reliable public figure exists. Never fabricate financial estimates, cultural signals, or URLs. Prefer official company sources, filings, "
            "credible financial press, or reputable databases. Explain why each company is aligned based on real scale, industry, offerings and audience, not deal logic. "
            "Return the five strongest supported peers, excluding the reference company.\n"
            f"REFERENCE COMPANY: {reference or 'Not specified'}\nINDUSTRY (infer from company when empty): {sector or 'Infer from the reference company'}\n"
            f"GEOGRAPHY SCOPE: {geography_scope}\n"
            "If a reference company is not resolvable, use available public sources to identify its industry and size; if neither can be established, state the limitation rather than guessing."
        )
        search = await self._web_search_json(prompt)
        values = search["data"].get("comparables", [])
        if not isinstance(values, list):
            values = []
        cleaned = []
        ref_normalized = reference.casefold()
        for item in values:
            if not isinstance(item, dict):
                continue
            if reference and str(item.get("name") or "").casefold() == ref_normalized:
                continue
            cleaned.append(item)
        # Return only five candidates and add cultural context to every displayed peer.
        peers = cleaned[:5]
        try:
            enriched = await asyncio.wait_for(self._enrich_comparables_with_culture(peers, reference, geography), timeout=6.5)
        except Exception:
            enriched = [dict(item, cultural_intelligence={"status": "unavailable", "note": "Cultural comparison did not complete in this pass."}) for item in peers]
        return {
            "criteria": {"reference_company": reference, "sector": sector, "geography": geography, "size_metric": "all", "size_band": "All available scale indicators"},
            "comparables": enriched[:5],
            "search_activity": search["steps"],
        }

    async def find_potential_targets(self, args: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Identify 6-8 real, currently operating companies that could plausibly match the stated business criteria. "
            "Use Google Search grounding. Prefer candidates with a verifiable public footprint and enough public financial information to screen. "
            "Return JSON only: {candidates:[{name, sector, geography, rationale, website, public_or_private, financial_data_available}]}. "
            "Do not invent companies, facts or URLs.\n"
            f"ACQUIRER: {args['acquirer']}\nSECTOR: {args['sector']}\nGEOGRAPHY: {args['geography']}\nBUSINESS CRITERIA: {args.get('business_criteria', '')}"
        )
        search = await self._web_search_json(prompt)
        return {"acquirer": args["acquirer"], "criteria": args, "candidates": search["data"].get("candidates", []), "search_activity": search["steps"]}

    async def qloo_lookup_entities(self, args: dict[str, Any]) -> dict[str, Any]:
        entities: list[dict[str, Any]] = []
        errors: list[str] = []
        for query in args.get("queries", []):
            try:
                result = await self.qloo.search(query, args.get("types"))
                entities.extend(self._normalize_qloo_entities(result, query))
            except QlooAPIError as exc:
                errors.append(str(exc))
        return {"entities": entities[:40], "errors": errors}

    async def qloo_cultural_insights(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._compact_qloo(await self.qloo.insights(args["entity_ids"], args["filter_type"], args.get("location"), 20))

    async def qloo_compare_footprints(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = await self.qloo.compare(args["acquirer_entity_ids"], args["target_entity_ids"], args.get("filter_types"), args.get("model", "descriptive"), 20)
        return self._compact_qloo(raw, include_affinity=True)

    async def qloo_trending_signals(self, args: dict[str, Any]) -> dict[str, Any]:
        raw = await self.qloo.trending(args["entity_ids"], args["filter_type"], args["start_date"], args["end_date"], 20)
        return self._compact_qloo(raw, include_affinity=True)

    async def calculate_financial_fit(self, args: dict[str, Any]) -> dict[str, Any]:
        metrics = args.get("metrics", {}) or {}
        required = ["revenue_growth", "ebitda_margin"]
        missing = [k for k in required if metrics.get(k) is None]
        if missing:
            return {"financial_fit": None, "components": {}, "status": "insufficient_evidence", "missing": missing}
        revenue_growth = max(0.0, min(1.0, float(metrics["revenue_growth"]) / 0.30))
        margin = max(0.0, min(1.0, float(metrics["ebitda_margin"]) / 0.30))
        leverage = None if metrics.get("net_debt_to_ebitda") is None else max(0.0, min(1.0, 1.0 - float(metrics["net_debt_to_ebitda"]) / 6.0))
        concentration = None if metrics.get("customer_concentration") is None else max(0.0, min(1.0, 1.0 - float(metrics["customer_concentration"]) / 100.0))
        components = {"growth": round(revenue_growth * 100), "margin": round(margin * 100)}
        if leverage is not None:
            components["leverage"] = round(leverage * 100)
        if concentration is not None:
            components["concentration"] = round(concentration * 100)
        weights = {"growth": 0.40, "margin": 0.40, "leverage": 0.15, "concentration": 0.05}
        terms = [(components["growth"], weights["growth"]), (components["margin"], weights["margin"])]
        if leverage is not None:
            terms.append((components["leverage"], weights["leverage"]))
        if concentration is not None:
            terms.append((components["concentration"], weights["concentration"]))
        weight_total = sum(w for _, w in terms)
        score = round(sum(v * w for v, w in terms) / weight_total) if weight_total else None
        return {"financial_fit": score, "components": components, "status": "complete", "weights_used": weights}

    async def score_acquisition_candidate(self, args: dict[str, Any]) -> dict[str, Any]:
        keys = ("strategic_fit", "cultural_fit", "audience_expansion", "financial_fit")
        scores = {k: args.get(k) for k in keys}
        if any(v is None for v in scores.values()):
            return {"overall_fit": None, "components": scores, "status": "insufficient_evidence"}
        weights = {"strategic_fit": 0.30, "cultural_fit": 0.30, "audience_expansion": 0.20, "financial_fit": 0.20}
        overall = round(sum(float(scores[k]) * weights[k] for k in keys))
        return {"overall_fit": overall, "components": {k: round(float(scores[k])) for k in keys}, "weights": weights, "status": "complete"}

    async def screen_target(self, acquirer: str, candidate: dict[str, Any], business_criteria: str) -> dict[str, Any]:
        """Research + Qloo-screen one discovered target and return an explainable score set."""
        target_name = str(candidate.get("name", "")).strip()
        if not target_name:
            raise ValueError("Candidate company is missing a name.")
        research = await self.search_company_information({
            "company": target_name,
            "questions": [
                f"How does this company fit the stated business criteria: {business_criteria}?",
                "What are the company's brands, products and audience?",
                "What financial metrics are publicly disclosed?",
            ],
        })
        acq_research = await self.search_company_information({
            "company": acquirer,
            "questions": ["What are the company's major brands, products and audience?", "What products, services, or customer segments could complement the company's current business?"],
        })
        a_queries = [acquirer] + [str(x) for x in (acq_research.get("brands") or [])[:3]]
        t_queries = [target_name] + [str(x) for x in (research.get("brands") or [])[:4]]
        a_lookup = await self.qloo_lookup_entities({"queries": a_queries})
        t_lookup = await self.qloo_lookup_entities({"queries": t_queries})
        a_ids = list(dict.fromkeys(x["entity_id"] for x in a_lookup.get("entities", [])))[:8]
        t_ids = list(dict.fromkeys(x["entity_id"] for x in t_lookup.get("entities", [])))[:8]
        compare: dict[str, Any] = {"results": [], "qloo_score": None}
        if a_ids and t_ids:
            compare = await self.qloo_compare_footprints({
                "acquirer_entity_ids": a_ids,
                "target_entity_ids": t_ids,
                "filter_types": ["urn:entity:brand", "urn:entity:place", "urn:entity:artist"],
                "model": "predictive",
            })
        strategic = await self._score_strategy(acquirer, target_name, business_criteria, acq_research, research)
        cultural = self._qloo_score(compare)
        audience = self._audience_expansion_score(compare)
        financial = await self.calculate_financial_fit({"metrics": research.get("financial_metrics") or {}})
        score = await self.score_acquisition_candidate({
            "strategic_fit": strategic,
            "cultural_fit": cultural,
            "audience_expansion": audience,
            "financial_fit": financial.get("financial_fit"),
        })
        components = score.get("components", {}) or {}
        return {
            **candidate,
            "strategic_fit": components.get("strategic_fit"),
            "cultural_fit": components.get("cultural_fit"),
            "audience_expansion": components.get("audience_expansion"),
            "financial_fit": components.get("financial_fit"),
            "research": research,
            "acquirer_research": acq_research,
            "qloo": {"acquirer_entities": a_lookup.get("entities", []), "target_entities": t_lookup.get("entities", []), "comparison": compare},
            "scores": components,
            "overall_fit": score.get("overall_fit"),
            "score_status": score.get("status"),
            "financial_detail": financial,
        }

    async def _score_strategy(self, acquirer: str, target: str, business_criteria: str, acq: dict[str, Any], tgt: dict[str, Any]) -> int:
        prompt = (
            "Return JSON only: {strategic_fit: number, rationale: string}. Score 0-100 for strategic acquisition fit based strictly on the supplied evidence. "
            "Do not invent facts. Consider product adjacency, customer overlap/complementarity, geography, competitive position and stated business criteria.\n"
            f"ACQUIRER: {acquirer}\nTARGET: {target}\nBUSINESS CRITERIA: {business_criteria}\nACQUIRER EVIDENCE:\n{json.dumps(acq, ensure_ascii=False)[:16000]}\nTARGET EVIDENCE:\n{json.dumps(tgt, ensure_ascii=False)[:16000]}"
        )
        result = await self._post_interaction({"model": self.model, "input": prompt, "response_format": {"type": "text", "mime_type": "application/json", "schema": {"type": "object", "properties": {"strategic_fit": {"type": "number"}, "rationale": {"type": "string"}}, "required": ["strategic_fit", "rationale"]}}})
        parsed = self._parse_json_object(result.get("output_text") or self._extract_output_text(result)) or {}
        return max(0, min(100, round(float(parsed.get("strategic_fit", 0)))))

    @staticmethod
    def _normalize_qloo_entities(result: dict[str, Any], query: str) -> list[dict[str, Any]]:
        raw = result.get("entities") or result.get("results") or []
        if isinstance(raw, dict):
            raw = raw.get("entities") or raw.get("results") or []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            entity_id = item.get("entity_id") or item.get("id") or item.get("qid")
            if entity_id:
                out.append({
                    "entity_id": entity_id,
                    "name": item.get("name") or item.get("title") or query,
                    "type": item.get("type"),
                    "properties": item.get("properties", {}),
                })
        return out

    @classmethod
    def _compact_qloo(cls, result: dict[str, Any], include_affinity: bool = False) -> dict[str, Any]:
        raw = result.get("results") or result.get("entities") or []
        query_meta = result.get("query") if isinstance(result.get("query"), dict) else {}
        if isinstance(raw, dict):
            query_meta = raw.get("query") if isinstance(raw.get("query"), dict) else query_meta
            raw = raw.get("entities") or raw.get("results") or []
        rows = []
        for item in raw[:30]:
            if not isinstance(item, dict):
                continue
            row = {
                "entity_id": item.get("entity_id") or item.get("id") or item.get("qid"),
                "name": item.get("name") or item.get("title"),
                "type": item.get("type"),
                "properties": item.get("properties", {}),
            }
            raw_affinity = item.get("affinity")
            if raw_affinity is None:
                raw_affinity = item.get("score")
            if raw_affinity is None:
                raw_affinity = (item.get("query") or {}).get("affinity")
            row["affinity"] = cls._numeric(raw_affinity)
            query_meta = item.get("query") if isinstance(item.get("query"), dict) else {}
            explanation = item.get("explainability") or query_meta.get("explainability")
            if explanation is not None:
                row["explainability"] = explanation
            rows.append(row)
        return {"count": len(rows), "results": rows, "query": query_meta, "raw_excerpt": json.dumps(result, ensure_ascii=False)[:12000]}

    @staticmethod
    def _numeric(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _qloo_score(cls, comparison: dict[str, Any]) -> int | None:
        vals = [x["affinity"] for x in comparison.get("results", []) if isinstance(x, dict) and x.get("affinity") is not None]
        if not vals:
            return None
        # Qloo affinities may be normalized 0-1 or presented as percentages.
        avg = sum(vals) / len(vals)
        return max(0, min(100, round(avg * 100 if avg <= 1 else avg)))

    @classmethod
    def _audience_expansion_score(cls, comparison: dict[str, Any]) -> int | None:
        return cls._qloo_score(comparison)

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any] | None:
        value = (text or "").strip()
        if not value:
            return None
        if value.startswith("```"):
            match = re.search(r"\{.*\}", value, re.S)
            value = match.group(0) if match else value.strip("`")
        try:
            data = json.loads(value)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            match = re.search(r"\{.*\}", value, re.S)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return data if isinstance(data, dict) else None
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _extract_output_text(interaction: dict[str, Any]) -> str:
        for step in reversed(interaction.get("steps", [])):
            if step.get("type") == "model_output":
                content = step.get("content") or step.get("output") or []
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts = [item.get("text") for item in content if isinstance(item, dict) and item.get("text")]
                    if texts:
                        return "\n".join(texts)
        return ""

    @staticmethod
    def _built_in_activity(interaction: dict[str, Any]) -> list[dict[str, Any]]:
        activity = []
        for step in interaction.get("steps", []):
            if step.get("type") == "google_search_call":
                activity.append({"tool": "google_search", "status": "complete", "input": step.get("queries") or []})
            elif step.get("type") == "google_search_result":
                activity.append({"tool": "google_search", "status": "complete", "result": "Search results received"})
        return activity

    @staticmethod
    def _activity_summary(result: dict[str, Any]) -> str:
        if "error" in result:
            return str(result["error"])
        if "entities" in result:
            return f"Resolved {len(result['entities'])} Qloo entities."
        if "results" in result:
            return f"Returned {len(result['results'])} Qloo results."
        if "candidates" in result:
            return f"Discovered {len(result['candidates'])} candidate companies."
        if "overall_fit" in result:
            return f"Calculated acquisition fit: {result['overall_fit'] if result['overall_fit'] is not None else 'insufficient evidence'}."
        if "financial_fit" in result:
            return f"Calculated financial fit: {result['financial_fit'] if result['financial_fit'] is not None else 'insufficient evidence'}."
        return "Tool completed."

    async def _post_interaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        last_network_error: Exception | None = None
        # One short retry helps with transient gateway/network errors without hiding quota or auth failures.
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_SECONDS) as client:
                    response = await client.post(url, headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, json=payload)
                if response.status_code in {500, 502, 503, 504} and attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                if response.status_code == 429:
                    raise RuntimeError("Gemini API rate limit or quota exceeded (429).")
                if response.status_code in {401, 403}:
                    raise RuntimeError(f"Gemini API rejected credentials or permissions ({response.status_code}).")
                if response.status_code == 404:
                    raise RuntimeError(f"Gemini model or Interactions API endpoint not found (404); configured model: {self.model}.")
                if response.status_code >= 400:
                    detail = ""
                    try:
                        body = response.json()
                        detail = str((body.get("error") or {}).get("message") or body.get("message") or "")
                    except Exception:
                        detail = response.text[:300]
                    raise RuntimeError(f"Gemini API request failed ({response.status_code}): {detail or 'provider returned an error'}")
                data = response.json()
                if data.get("status") == "failed":
                    raise RuntimeError(self._interaction_error(data))
                return data
            except httpx.TimeoutException as exc:
                last_network_error = RuntimeError(f"Gemini request timed out after {GEMINI_TIMEOUT_SECONDS:.0f}s.")
                raise last_network_error from exc
            except httpx.HTTPError as exc:
                last_network_error = RuntimeError("Gemini network request failed; check the connection and provider status.")
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise last_network_error from exc
        raise last_network_error or RuntimeError("Gemini request could not be completed.")

    @staticmethod
    def _interaction_error(interaction: dict[str, Any]) -> str:
        errors = interaction.get("errors") or []
        if errors:
            first = errors[0]
            return str(first.get("message") or first)
        return "Gemini interaction failed."

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        # Preserve useful HTTP/API diagnostics but never print credentials.
        msg = str(exc)
        return re.sub(r"(?i)(api[-_ ]?key|authorization|bearer)\s*[:=]\s*[^,\s]+", r"\1: [redacted]", msg)

    @classmethod
    def _normalize_result(cls, output: str, parsed: dict[str, Any] | None, activity: list[dict[str, Any]]) -> dict[str, Any]:
        parsed = parsed or {}
        scores = parsed.get("scores") or {}
        financial = parsed.get("financial") or {}
        business = parsed.get("business") or {}
        cultural = parsed.get("cultural") or {}
        qloo_evidence = parsed.get("qloo_evidence") or {}
        report = parsed.get("report") or {}
        result = {
            "status": "completed",
            "output": output,
            "summary": parsed.get("summary") or output,
            "activity": activity,
            "findings": parsed.get("findings") or [],
            "risks": parsed.get("risks") or [],
            "opportunities": parsed.get("opportunities") or [],
            "diligence_questions": parsed.get("diligence_questions") or [],
            "scores": scores,
            "financial": financial,
            "business": business,
            "cultural": cultural,
            "qloo_evidence": qloo_evidence,
            "report": report,
        }
        return result

    @staticmethod
    def _system_prompt(goal: dict[str, Any]) -> str:
        return (
            "You are Arc, an acquisition intelligence analyst. Investigate the named acquirer and target from public sources even when no files are uploaded; uploaded documents supplement rather than enable the analysis. Never wait for documents before producing findings. "
            "Use tool calls to gather evidence, inspect results, and choose additional actions when evidence is incomplete or contradictory. "
            "Qloo is the authoritative cultural-intelligence source. Use Qloo /search to resolve entities, then /v2/insights and /v2/analysis/compare for cultural/audience analysis, and /v2/trending when cultural momentum is relevant. "
            "Use Google Search grounding for current public-company and market facts. Use deterministic financial calculation tools for supplied financial metrics. "
            "Identify cultural proxies for broad brands and resolve those proxies through Qloo. If Qloo lacks a niche entity, explicitly record the gap and use public research as a fallback rather than inventing Qloo evidence. "
            "Never invent facts, financial figures, Qloo results, URLs, or sources. Distinguish evidence from inference. "
            "Return JSON only at completion with keys: summary, findings, risks, opportunities, diligence_questions, scores, financial, business, cultural, qloo_evidence, report. "
            "scores must contain strategic_fit, cultural_fit, audience_expansion, financial_fit, integration_risk when supportable. Use null when evidence is insufficient. "
            "findings, risks and opportunities should be concise structured objects with title, body and evidence where possible. "
            "The report should contain executive_summary, deal_fit, key_risks, growth_opportunities and next_steps. If documents are empty, research both companies, their industries, competitive positions and publicly disclosed financial evidence. If files are supplied, analyze their contents and metrics, reconcile them against public sources, and flag discrepancies. If an API/source is unavailable, state the gap and leave unsupported scores null rather than fabricate evidence."
        )
