"""The reverse-image-search boundary.

The pipeline is written against this interface and never against a vendor.
That matters for more than tidiness: it is what lets the evidence record name
the provider that actually answered, and what lets a reviewer swap in a
different one without touching the verification logic.

A provider's job ends at *discovery*. It returns candidates. It never decides
whether a candidate is a match -- that is the verification layer's job, and
keeping the two apart is the core of RAYA's design.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SearchResult:
    """One raw candidate as the provider reported it.

    `page_url` is where the image was found; `image_url` is the image itself.
    Both are kept: the page is the citable source, the image is what we
    independently re-download and run our own face models against.
    """

    position: int
    title: Optional[str]
    page_url: Optional[str]
    image_url: Optional[str]
    thumbnail_url: Optional[str]
    source_name: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "title": self.title,
            "page_url": self.page_url,
            "image_url": self.image_url,
            "thumbnail_url": self.thumbnail_url,
            "source_name": self.source_name,
        }


@dataclass
class SearchResponse:
    provider: str
    query_image_url: str
    results: list[SearchResult]
    queried_at: float
    duration_ms: int
    raw_result_count: int
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "query_image_url": self.query_image_url,
            "queried_at": self.queried_at,
            "duration_ms": self.duration_ms,
            "result_count": len(self.results),
            "raw_result_count": self.raw_result_count,
            "metadata": self.provider_metadata,
        }


class ReverseSearchProvider(ABC):
    """A source of reverse-image-search candidates."""

    name: str
    display_name: str
    requires_public_url: bool = True
    supports_direct_upload: bool = False

    @abstractmethod
    async def search(self, image_url: str) -> SearchResponse:
        """Run a reverse image search for a publicly reachable image URL."""

    async def search_image(self, data: bytes, mime: str = "image/jpeg") -> SearchResponse:
        """Search by uploading image bytes directly to the provider.

        This is the preferred path: it needs no public hosting of the input, so
        the original image is never published anywhere just to make it
        searchable. Providers that cannot accept an upload fall back to
        `search()` and must advertise `supports_direct_upload = False`.
        """
        raise NotImplementedError(
            f"{self.name} does not support direct image upload."
        )

    @property
    @abstractmethod
    def configured(self) -> bool:
        """Whether this provider has the credentials it needs to run."""

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "configured": self.configured,
            "supports_direct_upload": self.supports_direct_upload,
        }

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
