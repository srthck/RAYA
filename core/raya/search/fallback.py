"""Non-live providers.

Neither of these ever pretends to be a real search.

`NullProvider` fails loudly. It exists so that a missing API key produces an
honest "search not configured" state instead of an empty result set that looks
like "nothing was found on the web".

`ReplayProvider` serves a previously *recorded* live response from disk. It
powers offline tests and lets a reviewer re-run a past verification without
spending API credits. Every response it returns is stamped `is_replay: true`,
that flag travels into the evidence record, and the UI labels the run as a
replay. A replayed run is never presented as a fresh search.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..errors import SearchProviderError, SearchProviderNotConfiguredError
from ..util.hashing import sha256_bytes
from .base import ReverseSearchProvider, SearchResponse, SearchResult


class NullProvider(ReverseSearchProvider):
    name = "unconfigured"
    display_name = "No search provider configured"
    # Advertised as available so the pipeline reaches the search stage and
    # fails there with a specific reason, rather than stopping earlier with a
    # vague "no search path" message.
    supports_direct_upload = True

    def __init__(self, reason: str = "No reverse image search provider is configured."):
        self.reason = reason

    @property
    def configured(self) -> bool:
        return False

    async def search(self, image_url: str) -> SearchResponse:
        raise SearchProviderNotConfiguredError(self.reason)

    async def search_image(self, data: bytes, mime: str = "image/jpeg") -> SearchResponse:
        # Same refusal by either route: no key, no search, no invented results.
        raise SearchProviderNotConfiguredError(self.reason)


class ReplayProvider(ReverseSearchProvider):
    name = "replay"
    display_name = "Recorded search (replay)"
    requires_public_url = False
    # A recorded response is served whatever the input method, so the replay
    # provider exercises the same direct-upload path the live provider uses.
    supports_direct_upload = True

    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)

    @property
    def configured(self) -> bool:
        return self.fixture_path.exists()

    async def search_image(self, data: bytes, mime: str = "image/jpeg") -> SearchResponse:
        """Serve the recorded response for an uploaded search copy.

        The bytes are not sent anywhere; the copy's digest is recorded so a
        replayed run still shows which derivative would have been uploaded.
        """
        response = await self.search(f"upload:{sha256_bytes(data)}")
        response.provider_metadata["input_method"] = "direct_upload"
        response.provider_metadata["search_copy_sha256"] = sha256_bytes(data)
        return response

    async def search(self, image_url: str) -> SearchResponse:
        if not self.fixture_path.exists():
            raise SearchProviderError(
                f"Replay fixture not found: {self.fixture_path}", provider=self.name
            )
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        results = [
            SearchResult(
                position=item.get("position", index + 1),
                title=item.get("title"),
                page_url=item.get("page_url"),
                image_url=item.get("image_url"),
                thumbnail_url=item.get("thumbnail_url"),
                source_name=item.get("source_name"),
                raw=item,
            )
            for index, item in enumerate(payload.get("results", []))
        ]
        return SearchResponse(
            provider=self.name,
            query_image_url=image_url,
            results=results,
            queried_at=time.time(),
            duration_ms=0,
            raw_result_count=len(results),
            provider_metadata={
                "is_replay": True,
                "recorded_provider": payload.get("provider"),
                "recorded_at": payload.get("queried_at"),
                "fixture": self.fixture_path.name,
            },
        )
