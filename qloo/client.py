import os
from typing import Any
import httpx


class QlooClient:
    """Thin adapter for Qloo's hackathon API. Demo mode avoids external calls."""

    def __init__(self):
        self.base_url = os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com").rstrip("/")
        self.api_key = os.getenv("QLOO_API_KEY", "")
        self.demo_mode = os.getenv("DEMO_MODE", "true").lower() == "true"

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key, "Content-Type": "application/json"}

    async def search(self, query: str) -> dict[str, Any]:
        if self.demo_mode:
            return {"demo": True, "query": query, "entities": []}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self.base_url}/search", params={"query": query}, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def insights(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.demo_mode:
            return {"demo": True, "params": params, "results": []}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/v2/insights", params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def compare(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.demo_mode:
            return {"demo": True, "params": params, "results": []}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}/v2/analysis/compare", params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def trending(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.demo_mode:
            return {"demo": True, "params": params, "results": []}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self.base_url}/v2/trending", params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()
