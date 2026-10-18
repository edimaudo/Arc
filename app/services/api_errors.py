from __future__ import annotations

from typing import Any


def classify_api_error(exc: Exception) -> tuple[str, str]:
    """Return a stable diagnostic category and safe, actionable UI copy.

    Provider details stay in server logs; callers should never send raw exception
    strings or response bodies to the browser.
    """
    message = str(exc or "").strip()
    lowered = message.lower()

    if any(token in lowered for token in ("not configured", "missing api key", "api_key is required", "api key is not set")):
        return (
            "provider_configuration",
            "Arc's research connection is not configured correctly. The app administrator needs to check the provider API key in Vercel Environment Variables and redeploy.",
        )
    if any(token in lowered for token in ("429", "rate limit", "quota", "resource_exhausted", "too many requests")):
        return (
            "provider_quota",
            "Arc's research service has reached its current usage limit. Please wait a few minutes and try again. The app administrator can check provider quota and billing if this continues.",
        )
    if any(token in lowered for token in ("401", "403", "unauthorized", "permission_denied", "invalid api key", "api_key_invalid", "api key invalid", "api key expired", "key not valid", "credentials", "authentication failed")):
        return (
            "provider_authentication",
            "Arc could not authenticate with its research provider. The app administrator should verify the API credentials and provider access in Vercel.",
        )
    if (
        "404" in lowered or "model not found" in lowered or "model is unavailable" in lowered
        or "unsupported model" in lowered or "unknown model" in lowered
        or ("model" in lowered and any(token in lowered for token in ("invalid", "unsupported", "not available")))
    ):
        return (
            "provider_model_configuration",
            "Arc's research model setting was rejected by the provider. The app administrator should verify the configured model and API access in Vercel, then redeploy.",
        )
    if any(token in lowered for token in ("timed out", "timeout", "deadline exceeded", "function_invocation_timeout", "504 gateway time-out")):
        return (
            "research_timeout",
            "This search took longer than expected and timed out. Your selected company is preserved; please try again. If it keeps happening, the app administrator should review Vercel function duration and provider response time.",
        )
    if any(token in lowered for token in ("grounded company research returned no valid structured result", "no valid structured result", "invalid json", "jsondecodeerror", "could not parse json", "malformed json", "empty model response")):
        return (
            "provider_invalid_response",
            "The research service returned an incomplete result that Arc could not safely use. Your selected company is preserved; please retry in a moment.",
        )
    if any(token in lowered for token in ("400", "bad request", "invalid_argument", "unsupported parameter", "invalid request")):
        return (
            "provider_rejected_request",
            "The research provider rejected the request Arc sent, which can indicate a model or API configuration issue. Your selected company is preserved. Please retry; if it repeats, the app administrator should review the research settings in Vercel.",
        )
    if any(token in lowered for token in ("network", "connection", "dns", "temporarily unavailable", "502", "503", "500", "service unavailable", "connection refused")):
        return (
            "provider_unavailable",
            "Arc could not reach the research service just now. Your selected company is preserved; please try again shortly.",
        )
    if any(token in lowered for token in ("vercel", "function crashed", "function invocation", "function_invocation", "internal server error", "internal_server_error")):
        return (
            "deployment_error",
            "Arc encountered a temporary server error. Your selected company is preserved; please retry. If it continues, the app administrator should review the Vercel Function Logs.",
        )
    return (
        "unexpected_research_error",
        "Arc could not complete the company search. Your selected company is preserved. Please retry. If the issue keeps happening, share the reference ID with the app administrator so they can find the cause in the server logs.",
    )


def friendly_api_error(exc: Exception, provider: str = "live research service", reference_id: str | None = None) -> str:
    """Translate provider/network exceptions into actionable, non-sensitive UI copy."""
    _, message = classify_api_error(exc)
    if reference_id:
        return f"{message} Reference ID: {reference_id}."
    return message


def error_payload(exc: Exception, provider: str, reference_id: str) -> dict[str, Any]:
    category, _ = classify_api_error(exc)
    return {
        "error": friendly_api_error(exc, provider, reference_id),
        "error_code": category,
        "reference_id": reference_id,
        # The UI can always retry after a transient issue or after the app admin
        # corrects configuration and redeploys.
        "retryable": True,
    }
