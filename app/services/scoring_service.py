"""Normalize and derive directional acquisition scores from available evidence.

Scores are 0-100 directional assessments, not success probabilities. A neutral
midpoint is used only as a clearly marked, low-confidence fallback for a completed
report; unavailable API runs stay unscored. Missing financial metrics are never
silently treated as zero.
"""
from __future__ import annotations

import re
from typing import Any


_SCORE_KEYS = (
    "score", "fit_score", "overall_score", "score_percent", "percentage",
    "percent", "numeric_score", "value", "rating_value",
)
_TEXT_KEYS = ("rating", "level", "assessment", "label", "status", "summary", "result")


def _clamp_score(value: float) -> int:
    return int(round(max(0.0, min(100.0, value))))


def _as_score(value: Any) -> int | None:
    """Read a numeric score from scalar or structured model output."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        for key in _SCORE_KEYS:
            if key in value:
                parsed = _as_score(value.get(key))
                if parsed is not None:
                    return parsed
        for key in _TEXT_KEYS:
            if key in value:
                parsed = _qualitative_score(value.get(key))
                if parsed is not None:
                    return parsed
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text or re.search(r"not assessed|insufficient evidence|unavailable|unknown|pending", text, re.I):
            return None
        percent_match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
        ratio_match = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*100", text)
        scalar_match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*", text)
        match = percent_match or ratio_match or scalar_match
        if not match:
            return _qualitative_score(text)
        number = float(match.group(1))
    else:
        return None
    if 0 <= number <= 1:
        number *= 100
    return _clamp_score(number)


def _qualitative_score(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in _TEXT_KEYS:
            if key in value:
                return _qualitative_score(value.get(key))
        return None
    text = str(value or "").strip().lower()
    if not text or re.search(r"not assessed|insufficient evidence|unavailable|unknown|pending|not verified", text):
        return None
    if re.search(r"excellent|very strong|highly favorable|strong fit|well aligned", text):
        return 88
    if re.search(r"\b(strong|favorable|good|positive|high fit|high alignment|well positioned|high)\b", text) and not re.search(r"\bhigh risk\b", text):
        return 78
    if re.search(r"\b(moderate|mixed|partial|balanced|some alignment|promising with caveats)\b", text):
        return 60
    if re.search(r"\b(critical|severe|very high risk|poor|weak|unfavorable|incompatible)\b", text):
        return 25
    if re.search(r"\b(high risk|challenging|limited|low fit|low alignment|misaligned)\b", text):
        return 38
    if re.search(r"\blow risk\b", text):
        return 85
    return None


def _risk_to_fit(value: Any) -> int | None:
    """Convert a risk level/score to the inverse fit scale."""
    if isinstance(value, dict):
        for key in ("fit_score", "integration_fit", "fit"):
            if key in value:
                return _as_score(value[key])
        for key in ("risk_score", "score", "risk", "level", "rating", "assessment", "status"):
            if key in value:
                result = _risk_to_fit(value[key]) if key in ("risk", "level", "rating", "assessment", "status") else _as_score(value[key])
                if result is not None:
                    if key in ("risk_score", "score"):
                        return _clamp_score(100 - result)
                    return result
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        score = _as_score(value)
        return None if score is None else _clamp_score(100 - score)
    text = str(value or "").strip().lower()
    if not text or re.search(r"not assessed|insufficient evidence|unavailable|unknown|pending", text):
        return None
    if re.search(r"\b(critical|severe|very high)\b", text):
        return 15
    if re.search(r"\b(high|challenging|elevated)\b", text):
        return 35
    if re.search(r"\b(moderate|medium|mixed)\b", text):
        return 60
    if re.search(r"\b(low|minimal)\b", text):
        return 85
    return None


def _first_score(containers: list[tuple[dict[str, Any], tuple[str, ...]]], dimension: str) -> tuple[int | None, dict[str, Any]]:
    for container, keys in containers:
        if not isinstance(container, dict):
            continue
        for key in keys:
            if key not in container or container[key] is None:
                continue
            raw = container[key]
            if dimension == "integration_fit" and key in {"integration_risk", "risk"}:
                score = _risk_to_fit(raw)
            else:
                score = _as_score(raw)
            if score is not None:
                details: dict[str, Any] = {"method": "model_assessment", "confidence": "medium"}
                if isinstance(raw, dict):
                    rationale = raw.get("rationale") or raw.get("explanation") or raw.get("reason") or raw.get("basis")
                    confidence = raw.get("confidence")
                    evidence = raw.get("evidence") or raw.get("evidence_basis")
                    if rationale:
                        details["rationale"] = str(rationale)
                    if confidence:
                        details["confidence"] = str(confidence).lower()
                    if evidence:
                        details["evidence"] = evidence
                return score, details
    return None, {}


def _metric_value(value: Any, key: str) -> float | None:
    unit = ""
    raw = value
    for _ in range(5):
        if not isinstance(raw, dict):
            break
        unit = str(raw.get("unit") or raw.get("units") or raw.get("format") or unit).lower()
        next_key = next((candidate for candidate in ("value", "amount", "estimate", "percentage", "percent", "display", "formatted", "text") if raw.get(candidate) not in (None, "")), None)
        if next_key is None:
            return None
        raw = raw[next_key]
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        match = re.search(r"-?\d+(?:\.\d+)?", str(raw).replace(",", ""))
        if not match:
            return None
        number = float(match.group(0))
        if "%" in str(raw) or "percent" in unit or unit.strip() == "%":
            if key in {"revenue_growth", "ebitda_margin"}:
                return number / 100
            if key == "customer_concentration":
                return number
    if key in {"revenue_growth", "ebitda_margin"}:
        if abs(number) > 1 or "%" in unit or "percent" in unit or unit.strip() == "%":
            number /= 100
    elif key == "customer_concentration":
        if 0 <= number <= 1:
            number *= 100
    return number


def score_financial_metrics(metrics: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
    """Calculate a directional score from available disclosed metrics only."""
    if not isinstance(metrics, dict):
        return None, {}
    extracted = {key: _metric_value(metrics.get(key), key) for key in ("revenue_growth", "ebitda_margin", "net_debt_to_ebitda", "customer_concentration")}
    components: dict[str, int] = {}
    weights = {"revenue_growth": 0.40, "ebitda_margin": 0.40, "net_debt_to_ebitda": 0.15, "customer_concentration": 0.05}
    for key, value in extracted.items():
        if value is None:
            continue
        if key == "revenue_growth":
            # -20% growth maps to 0; +30% or better maps to 100.
            components[key] = _clamp_score(((value + 0.20) / 0.50) * 100)
        elif key == "ebitda_margin":
            components[key] = _clamp_score((value / 0.30) * 100)
        elif key == "net_debt_to_ebitda":
            components[key] = _clamp_score((1 - value / 6.0) * 100)
        elif key == "customer_concentration":
            components[key] = _clamp_score(100 - value)
    if not components:
        return None, {}
    weight_total = sum(weights[key] for key in components)
    score = _clamp_score(sum(components[key] * weights[key] for key in components) / weight_total)
    coverage = len(components)
    return score, {
        "method": "financial_metric_rubric",
        "confidence": "medium" if coverage >= 3 else "low",
        "rationale": "Calculated from disclosed financial indicators only. Missing metrics were excluded, not treated as zero.",
        "evidence": {key: extracted[key] for key in components},
        "components": components,
        "coverage": f"{coverage}/4 metrics available",
    }


def _text_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        ignored = {"source", "sources", "url", "urls", "citation", "citations", "evidence_url", "updated_at", "timestamp", "entity_id", "id"}
        parts: list[str] = []
        for key, item in value.items():
            if str(key).casefold() in ignored:
                continue
            parts.extend(_text_items(item))
        return parts
    if isinstance(value, (list, tuple)):
        return [part for item in value for part in _text_items(item)]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    return []


def _directional_text_score(text: str, positives: tuple[str, ...], negatives: tuple[str, ...], label: str) -> tuple[int | None, dict[str, Any]]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if len(normalized) < 35:
        return None, {}
    positive_hits = [term for term in positives if term in normalized]
    negative_hits = [term for term in negatives if term in normalized]
    delta = max(-4, min(4, len(positive_hits) - len(negative_hits)))
    score = _clamp_score(50 + delta * 7)
    if positive_hits or negative_hits:
        rationale = f"Directional reading of the report identified {len(positive_hits)} positive and {len(negative_hits)} cautionary signal types. This is a low-confidence summary, not a probability of success."
    else:
        rationale = "The report contains relevant discussion but no clear directional signal for this dimension. A neutral midpoint is used provisionally; this does not imply proven fit."
    return score, {
        "method": "qualitative_fallback", "confidence": "low", "rationale": rationale,
        "positive_signal_types": positive_hits[:6], "cautionary_signal_types": negative_hits[:6],
    }


def _qloo_audience_score(cultural: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
    signals = cultural.get("qloo_signals") if isinstance(cultural.get("qloo_signals"), dict) else {}
    target_distinct = signals.get("target_distinctive") or cultural.get("target_distinctive") or []
    shared = signals.get("shared_affinities") or cultural.get("shared") or []
    target_profile = signals.get("target_profile") if isinstance(signals.get("target_profile"), dict) else {}
    acquirer_profile = signals.get("acquirer_profile") if isinstance(signals.get("acquirer_profile"), dict) else {}

    def names(items: Any) -> set[str]:
        values: set[str] = set()
        if not isinstance(items, list):
            return values
        for item in items:
            if isinstance(item, dict):
                name = item.get("name") or item.get("title") or item.get("signal")
                category = item.get("category") or item.get("label") or ""
                if name:
                    values.add(f"{str(category).casefold()}::{str(name).casefold()}")
            elif item:
                values.add(str(item).casefold())
        return values

    distinct_names = names(target_distinct)
    shared_names = names(shared)
    target_top = target_profile.get("top_affinities") if isinstance(target_profile, dict) else []
    acquirer_top = acquirer_profile.get("top_affinities") if isinstance(acquirer_profile, dict) else []
    # A shared-signal list alone says nothing about expansion unless the target's
    # own affinity profile is present too.
    if not distinct_names and not target_top:
        return None, {}
    if not distinct_names and not shared_names:
        t_names, a_names = names(target_top), names(acquirer_top)
        if t_names and a_names:
            shared_names = t_names & a_names
            distinct_names = t_names - a_names
        elif t_names:
            distinct_names = t_names
    total = len(distinct_names | shared_names)
    if total == 0:
        return None, {}
    score = _clamp_score((len(distinct_names) / total) * 100)
    return score, {
        "method": "cultural_affinity_comparison", "confidence": "low" if total < 8 else "medium",
        "rationale": "Directional audience-expansion indicator based on the share of target cultural affinity signals that are distinctive in the returned profiles. It is not a forecast of customer acquisition or revenue.",
        "evidence": {"distinctive_target_signals": len(distinct_names), "shared_signals": len(shared_names), "signals_compared": total},
    }


def _fallback_text(result: dict[str, Any], groups: tuple[str, ...]) -> str:
    parts: list[str] = []
    report = result.get("report") if isinstance(result.get("report"), dict) else {}
    business = result.get("business") if isinstance(result.get("business"), dict) else {}
    cultural = result.get("cultural") if isinstance(result.get("cultural"), dict) else {}
    financial = result.get("financial") if isinstance(result.get("financial"), dict) else {}
    for group in groups:
        if group == "business":
            parts.extend(_text_items(business))
        elif group == "cultural":
            parts.extend(_text_items(cultural))
        elif group == "financial":
            parts.extend(_text_items(financial))
        elif group == "report":
            parts.extend(_text_items(report))
        elif group in result:
            parts.extend(_text_items(result.get(group)))
    return " ".join(parts)


def build_assessment_scores(result: dict[str, Any], documents: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return normalized overview scores, score explanations, and merged finance evidence."""
    scores = result.get("scores") if isinstance(result.get("scores"), dict) else {}
    report = result.get("report") if isinstance(result.get("report"), dict) else {}
    deal_fit = report.get("deal_fit") if isinstance(report.get("deal_fit"), dict) else {}
    financial = dict(result.get("financial") if isinstance(result.get("financial"), dict) else {})
    for document in documents or []:
        if not isinstance(document, dict) or not isinstance(document.get("metrics"), dict):
            continue
        for key, value in document["metrics"].items():
            if value is not None and financial.get(key) in (None, ""):
                financial[key] = value

    cultural = result.get("cultural") if isinstance(result.get("cultural"), dict) else {}
    qloo_audience, qloo_audience_detail = _qloo_audience_score(cultural)
    output: dict[str, Any] = {}
    details: dict[str, Any] = {}

    source_groups = {
        "strategic_fit": ((scores, ("strategic_fit", "strategic_fit_score")), (deal_fit, ("strategic_fit", "strategic_fit_score"))),
        "cultural_alignment": ((scores, ("cultural_alignment", "cultural_fit", "cultural_alignment_score")), (deal_fit, ("cultural_alignment", "cultural_fit", "cultural_alignment_score"))),
        "audience_expansion": ((scores, ("audience_expansion", "audience_expansion_score")), (deal_fit, ("audience_expansion", "audience_expansion_score"))),
        "financial_fit": ((scores, ("financial_fit", "financial_fit_score")), (deal_fit, ("financial_fit", "financial_fit_score"))),
        "integration_fit": ((scores, ("integration_fit", "integration_fit_score")), (deal_fit, ("integration_fit", "integration_fit_score"))),
    }
    for dimension, containers in source_groups.items():
        value, detail = _first_score(list(containers), dimension)
        output[dimension] = value
        if value is not None:
            details[dimension] = detail

    # Prefer Qloo-derived audience expansion where actual profiles are available.
    if qloo_audience is not None:
        output["audience_expansion"] = qloo_audience
        details["audience_expansion"] = qloo_audience_detail

    # Explicit model-provided confidence/rationale should survive normalization.
    supplied_details = result.get("score_details") if isinstance(result.get("score_details"), dict) else {}
    if isinstance(report.get("score_details"), dict):
        supplied_details = {**report.get("score_details", {}), **supplied_details}
    for dimension, detail in supplied_details.items():
        if dimension in details and isinstance(detail, dict):
            details[dimension].update({k: v for k, v in detail.items() if v not in (None, "")})
    if qloo_audience is not None:
        details["audience_expansion"] = qloo_audience_detail

    # If integration fit wasn't returned explicitly, invert the model's integration-risk assessment.
    if output.get("integration_fit") is None:
        risk_container = next((container for container in (scores, deal_fit) if isinstance(container, dict) and container.get("integration_risk") is not None), None)
        if risk_container is not None:
            risk_score = _risk_to_fit(risk_container.get("integration_risk"))
            if risk_score is not None:
                output["integration_fit"] = risk_score
                details["integration_fit"] = {"method": "inverted_integration_risk", "confidence": "medium", "rationale": "Converted the reported integration-risk assessment to the corresponding fit scale."}

    # Use a partial, weighted financial calculation when disclosed metrics exist.
    metric_score, metric_detail = score_financial_metrics(financial)
    if metric_score is not None:
        output["financial_fit"] = metric_score
        details["financial_fit"] = metric_detail

    # A detailed synthesis should produce directional assessments. If a model omitted a
    # numeric score, derive a transparent low-confidence fallback rather than silently
    # showing "Not assessed" for every dimension.
    substantive = bool(report or result.get("findings") or result.get("summary") or result.get("business") or result.get("cultural"))
    if substantive and not result.get("limited_mode"):
        strategic_text = _fallback_text(result, ("business", "findings", "opportunities", "risks", "report", "summary"))
        audience_text = _fallback_text(result, ("cultural", "business", "findings", "opportunities", "report", "summary"))
        financial_text = _fallback_text(result, ("financial", "findings", "risks", "report", "summary"))
        integration_text = _fallback_text(result, ("cultural", "business", "risks", "findings", "report", "summary"))
        fallback_specs = {
            "strategic_fit": (strategic_text,
                ("complementary", "complements", "adjacent", "cross-sell", "expand", "expansion", "synergy", "capability", "market access", "distribution", "aligned", "strategic rationale"),
                ("mismatch", "misaligned", "cannibalization", "conflict", "duplicative", "incompatible", "limited fit", "competes directly")),
            "audience_expansion": (audience_text,
                ("new audience", "audience expansion", "distinctive", "unserved segment", "reach new", "adjacent audience", "different audience", "audience opportunity", "brand adjacency"),
                ("same audience", "limited expansion", "little expansion", "high overlap", "no new audience")),
            "financial_fit": (financial_text,
                ("revenue growth", "growing revenue", "profitability", "positive ebitda", "strong margins", "cash generation", "low leverage", "recurring revenue", "improving margins"),
                ("declining revenue", "loss-making", "negative cash flow", "high leverage", "liquidity pressure", "margin pressure", "debt burden", "financial distress")),
            "integration_fit": (integration_text,
                ("compatible", "aligned operating model", "shared values", "complementary capabilities", "compatible systems", "clear integration path", "common culture", "operating model alignment"),
                ("cultural gap", "integration risk", "system incompatibility", "retention risk", "operational complexity", "regulatory complexity", "misaligned", "integration challenge")),
        }
        for dimension, (text, positive, negative) in fallback_specs.items():
            if output.get(dimension) is not None:
                continue
            fallback, detail = _directional_text_score(text, positive, negative, dimension)
            if fallback is None:
                # A detailed report exists, but this dimension has little explicit data.
                # Use a neutral placeholder with low confidence instead of pretending it
                # was a measured result. The explanation makes the limitation visible.
                fallback = 50
                detail = {
                    "method": "neutral_low_confidence_fallback", "confidence": "low",
                    "rationale": "Neutral midpoint used because no numeric or sufficiently directional evidence was returned for this dimension. This is provisional, not proof of fit; validate with diligence.",
                }
            output[dimension] = fallback
            details[dimension] = detail

    return output, details, financial
