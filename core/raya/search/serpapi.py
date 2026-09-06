"""Google Lens reverse image search via SerpApi.

SerpApi is a paid, terms-of-service-compliant gateway to Google Lens. RAYA uses
it rather than scraping Google directly.

One constraint shapes the whole stage: Lens is given a *URL*, not an upload.
A locally supplied image therefore has to be publicly reachable before it can
be searched at all. `PipelineContext` resolves that by publishing the input to
IPFS first and passing the gateway URL here -- see `pipeline/orchestrator.py`.

We read `visual_matches` (Lens's "found on these pages" list). Product and
shopping blocks are ignored: they describe merchandise, not the provenance of a
photograph.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import Settings, get_settings
from ..errors import SearchProviderError, SearchProviderNotConfiguredError
from .base import ReverseSearchProvider, SearchResponse, SearchResult

SERPAPI_ENDPOINT = "https://serpapi.com/search"


class GoogleLensProvider(ReverseSearchProvider):
    name = "google_lens"
    display_name = "Google Lens (SerpApi)"
    requires_public_url = True

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.settings.serpapi_key)

    async def search(self, image_url: str) -> SearchResponse:
        if not self.configured:
            raise SearchProviderNotConfiguredError(
                "SERPAPI_KEY is not set, so no real reverse image search can run. "
                "RAYA does not substitute placeholder results."
            )

        params = {
            "engine": "google_lens",
            "url": image_url,
            "api_key": self.settings.serpapi_key,
            "hl": "en",
            "country": "us",
        }

        started = time.perf_counter()
        queried_at = time.time()
        payload = await self._request(params)
        duration_ms = self._elapsed_ms(started)

        if "error" in payload:
            raise SearchProviderError(
                f"Google Lens search failed: {payload['error']}",
                provider=self.name,
            )

        raw_matches = _collect_visual_matches(payload)
        results = [
            _to_result(index, match) for index, match in enumerate(raw_matches)
        ]
        results = [r for r in results if r.page_url or r.image_url]
        results = results[: self.settings.max_candidates]

        return SearchResponse(
            provider=self.name,
            query_image_url=image_url,
            results=results,
            queried_at=queried_at,
            duration_ms=duration_ms,
            raw_result_count=len(raw_matches),
            provider_metadata={
                "engine": "google_lens",
                "search_id": (payload.get("search_metadata") or {}).get("id"),
                "google_url": (payload.get("search_metadata") or {}).get("google_lens_url"),
                "status": (payload.get("search_metadata") or {}).get("status"),
            },
        )

    async def _request(self, params: dict) -> dict[str, Any]:
        timeout = httpx.Timeout(self.settings.search_timeout_s)
        try:
            if self._client is not None:
                response = await self._client.get(
                    SERPAPI_ENDPOINT, params=params, timeout=timeout
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(SERPAPI_ENDPOINT, params=params)
        except httpx.TimeoutException:
            raise SearchProviderError(
                f"Google Lens search timed out after {self.settings.search_timeout_s:.0f}s.",
                provider=self.name,
            )
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                f"Could not reach the search provider: {exc}", provider=self.name
            )

        if response.status_code == 401:
            raise SearchProviderNotConfiguredError("SerpApi rejected the API key.")
        if response.status_code == 429:
            raise SearchProviderError(
                "SerpApi rate limit or quota reached.", provider=self.name
            )
        if response.status_code >= 400:
            raise SearchProviderError(
                f"SerpApi returned HTTP {response.status_code}.",
                provider=self.name,
                status=response.status_code,
            )
        try:
            return response.json()
        except ValueError:
            raise SearchProviderError(
                "SerpApi returned a non-JSON response.", provider=self.name
            )


def _collect_visual_matches(payload: dict) -> list[dict]:
    """Pull the provenance-bearing blocks out of a Lens response.

    SerpApi's Lens schema has shifted over time (`visual_matches` today,
    `image_results`/`knowledge_graph` in older layouts). Reading several keys
    keeps the provider working across those revisions instead of silently
    returning zero candidates after an upstream change.
    """
    matches: list[dict] = []
    for key in ("visual_matches", "image_results", "exact_matches", "related_content"):
        block = payload.get(key)
        if isinstance(block, list):
            matches.extend(item for item in block if isinstance(item, dict))
    return matches


def _to_result(index: int, match: dict) -> SearchResult:
    image_url = (
        match.get("image")
        or match.get("original")
        or match.get("original_image")
        or match.get("thumbnail")
    )
    return SearchResult(
        position=int(match.get("position") or index + 1),
        title=match.get("title"),
        page_url=match.get("link") or match.get("source_url"),
        image_url=image_url,
        thumbnail_url=match.get("thumbnail"),
        source_name=match.get("source"),
        raw=match,
    )
