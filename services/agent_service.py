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
    """Arc's live tool-using M&A analyst.

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
                "description": "Run a grounded market search for companies that could plausibly fit an acquisition thesis. Return real companies only; candidates are then screened separately.",
                "parameters": {"type": "object", "properties": {
                    "acquirer": {"type": "string"}, "sector": {"type": "string"}, "geography": {"type": "string"}, "thesis": {"type": "string"}
                }, "required": ["acquirer", "sector", "geography", "thesis"]},
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
        self._require_gemini()
        seed = await self._seed_qloo_context(goal)
        goal_with_seed = {**goal, "preloaded_qloo_context": seed}
        first = await self._create_interaction(goal_with_seed)
        result = await self._continue(first, max_turns=max_turns)
        result["qloo_evidence"] = {"preflight": seed, **(result.get("qloo_evidence") or {})}
        return result

    async def _seed_qloo_context(self, goal: dict[str, Any]) -> dict[str, Any]:
        """Establish an initial Qloo footprint so Qloo remains material to every investigation."""
        seed: dict[str, Any] = {"acquirer": [], "target": [], "comparison": {}, "errors": []}
        try:
            acq = await self.qloo_lookup_entities({"queries": [goal["acquirer"]]})
            tgt = await self.qloo_lookup_entities({"queries": [goal["target"]]})
            seed["acquirer"] = acq.get("entities", [])[:5]
            seed["target"] = tgt.get("entities", [])[:5]
            a_ids = [x["entity_id"] for x in seed["acquirer"]]
            b_ids = [x["entity_id"] for x in seed["target"]]
            if a_ids and b_ids:
                seed["comparison"] = await self.qloo_compare_footprints({
                    "acquirer_entity_ids": a_ids,
                    "target_entity_ids": b_ids,
                    "filter_types": ["urn:entity:brand", "urn:entity:place"],
                    "model": "descriptive",
                })
        except Exception as exc:
            seed["errors"].append(str(exc))
        return seed

    async def _create_interaction(self, goal: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "system_instruction": self._system_prompt(goal),
            "input": "Investigate this M&A assignment. Decide which tools you need and continue until you have sufficient evidence for a defensible acquisition assessment.\n\nUSER GOAL:\n" + json.dumps(goal, ensure_ascii=False),
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
        return self._normalize_result(output, parsed, activity)

    async def ask(self, question: str, context: dict[str, Any]) -> str:
        self._require_gemini()
        payload = {
            "model": self.model,
            "system_instruction": (
                "You are Arc, an M&A analyst. Answer the user's follow-up question using only the supplied investigation context. "
                "You may use Qloo or Google Search tools if the existing evidence is insufficient. Do not invent facts. "
                "Write concise analyst-grade prose and distinguish evidence from inference."
            ),
            "input": "INVESTIGATION CONTEXT:\n" + json.dumps(context, ensure_ascii=False)[:50000] + "\n\nQUESTION:\n" + question,
            "tools": self.tool_declarations,
        }
        interaction = await self._post_interaction(payload)
        result = await self._continue(interaction, max_turns=6)
        return result.get("output") or "Arc did not return an answer."

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

    async def find_potential_targets(self, args: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Identify 6-8 real, currently operating companies that could plausibly be acquisition targets for the stated acquirer. "
            "Use Google Search grounding. Prefer candidates with a verifiable public footprint and enough public financial information to screen. "
            "Return JSON only: {candidates:[{name, sector, geography, rationale, website, public_or_private, financial_data_available}]}. "
            "Do not invent companies, facts or URLs.\n"
            f"ACQUIRER: {args['acquirer']}\nSECTOR: {args['sector']}\nGEOGRAPHY: {args['geography']}\nTHESIS: {args['thesis']}"
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

    async def screen_target(self, acquirer: str, candidate: dict[str, Any], thesis: str) -> dict[str, Any]:
        """Research + Qloo-screen one discovered target and return an explainable score set."""
        target_name = str(candidate.get("name", "")).strip()
        if not target_name:
            raise ValueError("Candidate company is missing a name.")
        research = await self.search_company_information({
            "company": target_name,
            "questions": [
                f"How does this company fit the acquisition thesis: {thesis}?",
                "What are the company's brands, products and audience?",
                "What financial metrics are publicly disclosed?",
            ],
        })
        acq_research = await self.search_company_information({
            "company": acquirer,
            "questions": ["What are the company's major brands, products and audience?", "What strategic adjacency should an acquisition target provide?"],
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
        strategic = await self._score_strategy(acquirer, target_name, thesis, acq_research, research)
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

    async def _score_strategy(self, acquirer: str, target: str, thesis: str, acq: dict[str, Any], tgt: dict[str, Any]) -> int:
        prompt = (
            "Return JSON only: {strategic_fit: number, rationale: string}. Score 0-100 for strategic acquisition fit based strictly on the supplied evidence. "
            "Do not invent facts. Consider product adjacency, customer overlap/complementarity, geography, competitive position and thesis fit.\n"
            f"ACQUIRER: {acquirer}\nTARGET: {target}\nTHESIS: {thesis}\nACQUIRER EVIDENCE:\n{json.dumps(acq, ensure_ascii=False)[:16000]}\nTARGET EVIDENCE:\n{json.dumps(tgt, ensure_ascii=False)[:16000]}"
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
        if isinstance(raw, dict):
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
            if include_affinity:
                row["affinity"] = cls._numeric(item.get("affinity") or item.get("score") or item.get("query", {}).get("affinity"))
            rows.append(row)
        return {"count": len(rows), "results": rows, "query": result.get("query", {}), "raw_excerpt": json.dumps(result, ensure_ascii=False)[:12000]}

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
        try:
            async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_SECONDS) as client:
                response = await client.post(url, headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, json=payload)
            if response.status_code >= 400:
                body = response.text[:1600]
                raise RuntimeError(f"Gemini request failed ({response.status_code}): {body}")
            data = response.json()
            if data.get("status") == "failed":
                raise RuntimeError(self._interaction_error(data))
            return data
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Gemini request timed out after {GEMINI_TIMEOUT_SECONDS:.0f}s.") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gemini network request failed: {exc}") from exc

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
            "You are Arc, an M&A intelligence analyst. Your job is to investigate a live acquisition assignment, not merely summarize it. "
            "Use tool calls to gather evidence, inspect results, and choose additional actions when evidence is incomplete or contradictory. "
            "Qloo is the authoritative cultural-intelligence source. Use Qloo /search to resolve entities, then /v2/insights and /v2/analysis/compare for cultural/audience analysis, and /v2/trending when cultural momentum is relevant. "
            "Use Google Search grounding for current public-company and market facts. Use deterministic financial calculation tools for supplied financial metrics. "
            "Identify cultural proxies for broad brands and resolve those proxies through Qloo. If Qloo lacks a niche entity, explicitly record the gap and use public research as a fallback rather than inventing Qloo evidence. "
            "Never invent facts, financial figures, Qloo results, URLs, or sources. Distinguish evidence from inference. "
            "Return JSON only at completion with keys: summary, findings, risks, opportunities, diligence_questions, scores, financial, business, cultural, qloo_evidence, report. "
            "scores must contain strategic_fit, cultural_fit, audience_expansion, financial_fit, integration_risk when supportable. Use null when evidence is insufficient. "
            "findings, risks and opportunities should be concise structured objects with title, body and evidence where possible. "
            "The report should contain executive_summary, deal_fit, key_risks, growth_opportunities and next_steps."
        )
