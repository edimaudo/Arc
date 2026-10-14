from __future__ import annotations


def friendly_api_error(exc: Exception, provider: str = "live research service") -> str:
    """Translate provider/network exceptions into actionable, non-sensitive UI copy."""
    message = str(exc or "").strip()
    lowered = message.lower()
    name = provider.strip() or "live research service"

    if "not configured" in lowered or "api_key" in lowered and "not" in lowered:
        if "qloo" in lowered:
            return "Cultural data is not configured. Add QLOO_API_KEY to the deployment environment to enable cultural signals."
        return "Live research is not configured. Add GEMINI_API_KEY to the deployment environment and redeploy."
    if "429" in lowered or "rate limit" in lowered or "quota" in lowered or "resource_exhausted" in lowered:
        return f"{name.capitalize()} rate limit or quota reached. Check the provider's quota and billing, then retry."
    if "401" in lowered or "403" in lowered or "unauthorized" in lowered or "permission_denied" in lowered or "invalid api key" in lowered:
        return "The research provider rejected its credentials. Verify GEMINI_API_KEY in Vercel Environment Variables and redeploy."
    if "404" in lowered or "model not found" in lowered or "not found" in lowered:
        return "The configured Gemini model or API endpoint is unavailable. Check GEMINI_MODEL against the supported model IDs, then redeploy."
    if "timeout" in lowered or "timed out" in lowered:
        return f"{name.capitalize()} timed out before returning results. Your inputs are preserved; retry in a moment."
    if any(token in lowered for token in ("network", "connection", "dns", "temporarily unavailable", "502", "503", "504", "500")):
        return f"{name.capitalize()} is temporarily unavailable. Your inputs are preserved; retry shortly."
    return f"{name.capitalize()} could not complete the request. Your inputs are preserved. Retry shortly; if it continues, check the API key, model setting, and quota in Vercel."
