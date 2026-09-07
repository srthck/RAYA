"""Google Lens reverse image search via SerpApi.

SerpApi is a paid, terms-of-service-compliant gateway to Google Lens. RAYA uses
it rather than scraping Google directly.

Two ways in, and the difference matters:

* **Direct upload (preferred).** `POST https://serpapi.com/image` takes the
  image bytes as multipart form data and returns an `image_id`, which the Lens
  engine accepts in place of `url`. Nothing is published anywhere. The id
  expires after about ten minutes, and the endpoint caps uploads at 500 KB --
  which is why `searchcopy.py` produces a bounded derivative rather than
  sending the original.
* **URL (fallback).** Lens will also take a publicly reachable image URL. Used
  only when `PUBLIC_BASE_URL` is configured and the API is internet-reachable.

What leaves the machine is the bounded search copy, never the original bytes
and never the face embedding.

We read `visual_matches` (Lens's "found on these pages" list). Product and
shopping blocks are ignored: they describe merchandise, not the provenance of a
photograph.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import Settings, get_settings
from ..errors import (
    SearchCredentialRejectedError,
    SearchProviderError,
    SearchProviderNotConfiguredError,
)
from .base import ReverseSearchProvider, SearchResponse, SearchResult

SERPAPI_ENDPOINT = "https://serpapi.com/search"
SERPAPI_UPLOAD_ENDPOINT = "https://serpapi.com/image"

# The upload endpoint's documented ceiling. `searchcopy` targets below this.
SERPAPI_MAX_UPLOAD_BYTES = 500_000
SERPAPI_UPLOAD_MIMES = ("image/jpeg", "image/jpg", "image/png", "image/webp")


class GoogleLensProvider(ReverseSearchProvider):
    name = "google_lens"
    display_name = "Google Lens (SerpApi)"
    requires_public_url = False
    supports_direct_upload = True

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.settings.serpapi_key)

    async def upload_image(self, data: bytes, mime: str = "image/jpeg") -> str:
        """Upload image bytes and return SerpApi's `image_id`.

        Validated locally first: a request that the endpoint would reject on
        size or type is better refused here, with a message naming the actual
        limit, than surfaced as an opaque provider error mid-run.
        """
        if not self.configured:
            raise SearchProviderNotConfiguredError(
                "SERPAPI_KEY is not set, so no image can be uploaded for search."
            )
        if not data:
            raise SearchProviderError("Refusing to upload an empty image.", provider=self.name)
        if len(data) > SERPAPI_MAX_UPLOAD_BYTES:
            raise SearchProviderError(
                f"Search copy is {len(data) / 1000:.0f} KB; the provider limit is "
                f"{SERPAPI_MAX_UPLOAD_BYTES / 1000:.0f} KB.",
                provider=self.name,
            )
        if mime not in SERPAPI_UPLOAD_MIMES:
            raise SearchProviderError(
                f"{mime} cannot be uploaded; the provider accepts JPEG, PNG or WebP.",
                provider=self.name,
            )

        timeout = httpx.Timeout(self.settings.search_timeout_s)
        files = {"image": ("search-copy.jpg", data, mime)}
        payload = {"api_key": self.settings.serpapi_key}

        try:
            if self._client is not None:
                response = await self._client.post(
                    SERPAPI_UPLOAD_ENDPOINT, files=files, data=payload, timeout=timeout
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        SERPAPI_UPLOAD_ENDPOINT, files=files, data=payload
                    )
        except httpx.TimeoutException:
            raise SearchProviderError(
                f"Image upload timed out after {self.settings.search_timeout_s:.0f}s.",
                provider=self.name,
            )
        except httpx.HTTPError as exc:
            raise SearchProviderError(
                f"Could not reach the image upload endpoint: {exc}", provider=self.name
            )

        if response.status_code == 401:
            raise SearchCredentialRejectedError(
                "SerpApi rejected the API key.", provider=self.name
            )
        if response.status_code == 413:
            raise SearchProviderError(
                "The provider rejected the search copy as too large.", provider=self.name
            )
        if response.status_code >= 400:
            raise SearchProviderError(
                f"Image upload returned HTTP {response.status_code}.",
                provider=self.name,
                status=response.status_code,
            )

        try:
            body = response.json()
        except ValueError:
            raise SearchProviderError(
                "Image upload returned a non-JSON response.", provider=self.name
            )

        image_id = body.get("image_id") or body.get("id")
        if not image_id:
            raise SearchProviderError(
                f"Image upload succeeded but returned no image_id: {str(body)[:160]}",
                provider=self.name,
            )
        return str(image_id)

    async def search_image(self, data: bytes, mime: str = "image/jpeg") -> SearchResponse:
        """Upload the bytes, then search Lens by the returned `image_id`."""
        image_id = await self.upload_image(data, mime)
        return await self._run_search(
            {"image_id": image_id},
            query_image_url=f"serpapi:image_id/{image_id}",
            extra_metadata={"image_id": image_id, "input_method": "direct_upload"},
        )

    async def search(self, image_url: str) -> SearchResponse:
        """Search Lens by a publicly reachable image URL (fallback path)."""
        if not self.configured:
            raise SearchProviderNotConfiguredError(
                "SERPAPI_KEY is not set, so no real reverse image search can run. "
                "RAYA does not substitute placeholder results."
            )
        return await self._run_search(
            {"url": image_url},
            query_image_url=image_url,
            extra_metadata={"input_method": "public_url"},
        )

    async def _run_search(
        self,
        query: dict[str, str],
        query_image_url: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> SearchResponse:
        """Run one Lens query. `query` carries either `url` or `image_id`."""
        params = {
            "engine": "google_lens",
            "api_key": self.settings.serpapi_key,
            "hl": "en",
            "country": "us",
            **query,
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

        metadata = {
            "engine": "google_lens",
            "search_id": (payload.get("search_metadata") or {}).get("id"),
            "google_url": (payload.get("search_metadata") or {}).get("google_lens_url"),
            "status": (payload.get("search_metadata") or {}).get("status"),
        }
        metadata.update(extra_metadata or {})

        return SearchResponse(
            provider=self.name,
            query_image_url=query_image_url,
            results=results,
            queried_at=queried_at,
            duration_ms=duration_ms,
            raw_result_count=len(raw_matches),
            provider_metadata=metadata,
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
            raise SearchCredentialRejectedError(
                "SerpApi rejected the API key.", provider=self.name
            )
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
