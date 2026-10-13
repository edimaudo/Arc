from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import QLOO_API_KEY, QLOO_BASE_URL, QLOO_TIMEOUT_SECONDS


class QlooAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: str = '') -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class QlooClient:
    """Small async client for the Qloo hackathon API."""

    def __init__(self) -> None:
        self.base_url = QLOO_BASE_URL
        self.api_key = QLOO_API_KEY
        self.timeout = QLOO_TIMEOUT_SECONDS

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise QlooAPIError('QLOO_API_KEY is not configured')
        return {'X-Api-Key': self.api_key, 'Accept': 'application/json'}

    async def _get(self, path: str, params: list[tuple[str, Any]] | dict[str, Any], retries: int = 2) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f'{self.base_url}{path}', params=params, headers=self._headers())
                if response.status_code == 429 and attempt < retries:
                    retry_after = float(response.headers.get('retry-after', '1'))
                    await asyncio.sleep(min(max(retry_after, 0.5), 8))
                    continue
                if response.status_code >= 500 and attempt < retries:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                if response.status_code >= 400:
                    raise QlooAPIError(
                        f'Qloo request failed ({response.status_code}).',
                        status_code=response.status_code,
                        body=response.text[:1200],
                    )
                try:
                    return response.json()
                except ValueError as exc:
                    raise QlooAPIError('Qloo returned a non-JSON response.', status_code=response.status_code, body=response.text[:1200]) from exc
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                raise QlooAPIError(f'Qloo request timed out after {self.timeout:.0f}s.') from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                raise QlooAPIError(f'Qloo network request failed: {exc}') from exc
        raise QlooAPIError(f'Qloo request failed: {last_error or "unknown error"}')

    async def search(self, query: str, types: list[str] | None = None, take: int = 8) -> dict[str, Any]:
        params: list[tuple[str, Any]] = [('query', query), ('take', max(1, min(take, 50))), ('sort_by', 'match')]
        for entity_type in types or []:
            params.append(('types', entity_type))
        return await self._get('/search', params)

    async def insights(self, entity_ids: list[str], filter_type: str,
                       location: str | None = None, take: int = 20) -> dict[str, Any]:
        if not entity_ids:
            raise QlooAPIError('At least one Qloo entity is required for Insights.')
        params: list[tuple[str, Any]] = [
            ('filter.type', filter_type),
            ('feature.explainability', 'true'),
            ('take', max(1, min(take, 50))),
            ('sort_by', 'affinity'),
        ]
        if location:
            params.append(('filter.location.query', location))
        for entity_id in entity_ids:
            params.append(('signal.interests.entities', entity_id))
        return await self._get('/v2/insights', params)

    async def compare(self, a_entities: list[str], b_entities: list[str], filter_types: list[str] | None = None,
                      model: str = 'descriptive', take: int = 20) -> dict[str, Any]:
        if not a_entities or not b_entities:
            raise QlooAPIError('Both entity groups are required for Qloo Compare.')
        params: list[tuple[str, Any]] = []
        for entity in a_entities:
            params.append(('a.signal.interests.entities', entity))
        for entity in b_entities:
            params.append(('b.signal.interests.entities', entity))
        for filter_type in filter_types or ['urn:entity:brand', 'urn:entity:artist', 'urn:entity:place']:
            params.append(('filter.type', filter_type))
        params.extend([('model', model), ('take', max(1, min(take, 50)))])
        return await self._get('/v2/analysis/compare', params)

    async def trending(self, entities: list[str], filter_type: str, start_date: str,
                       end_date: str, take: int = 20) -> dict[str, Any]:
        if not entities:
            raise QlooAPIError('At least one Qloo entity is required for Trends.')
        params: list[tuple[str, Any]] = [
            ('filter.type', filter_type),
            ('filter.start_date', start_date),
            ('filter.end_date', end_date),
            ('take', max(1, min(take, 50))),
        ]
        for entity in entities:
            params.append(('signal.interests.entities', entity))
        return await self._get('/v2/trending', params)
