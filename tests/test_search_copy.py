"""The bounded search copy and the direct-upload search path.

Two properties matter here and both are load-bearing for RAYA's honesty:

1. The original input is never the thing that gets sent. The copy is a separate
   object with its own hash, so the evidence can say exactly what left the
   machine without muddling it with `input.sha256`.
2. A missing or failing provider produces a refusal, never a fabricated result.

The provider is exercised against an httpx mock transport rather than the live
API: these assertions are about our request shape and our error handling, and
they must run offline and for free.
"""

from __future__ import annotations

import json

import httpx
import pytest

from raya.errors import (
    InvalidImageError,
    SearchProviderError,
    SearchProviderNotConfiguredError,
)
from raya.search.searchcopy import (
    DEFAULT_MAX_BYTES,
    EDGE_LADDER,
    build_search_copy,
)
from raya.search.serpapi import (
    SERPAPI_MAX_UPLOAD_BYTES,
    SERPAPI_UPLOAD_ENDPOINT,
    GoogleLensProvider,
)
from raya.util.hashing import sha256_bytes


class TestSearchCopy:
    def test_stays_within_the_provider_limit(self, decoded):
        for name, image in decoded.items():
            copy = build_search_copy(image.bgr)
            assert copy.byte_size <= DEFAULT_MAX_BYTES, f"{name} produced {copy.byte_size} bytes"
            assert copy.byte_size <= SERPAPI_MAX_UPLOAD_BYTES

    def test_bounds_a_very_large_image(self, decoded, settings):
        """A multi-megapixel photo must still fit the 500 KB upload ceiling."""
        import cv2

        original = decoded["subject_a"].bgr
        huge = cv2.resize(original, (original.shape[1] * 5, original.shape[0] * 5))
        copy = build_search_copy(huge)

        assert copy.byte_size <= DEFAULT_MAX_BYTES
        assert copy.resized
        assert max(copy.width, copy.height) <= EDGE_LADDER[0]

    def test_is_deterministic(self, decoded):
        """Same input, same bytes -- otherwise the recorded copy hash is not
        reproducible by anyone holding the original."""
        image = decoded["subject_a"].bgr
        first = build_search_copy(image)
        second = build_search_copy(image)
        assert first.sha256 == second.sha256
        assert first.data == second.data

    def test_hash_differs_from_the_input_hash(self, decoded, image_bytes):
        """The copy is a different object and must never be mistaken for the
        canonical input."""
        copy = build_search_copy(decoded["subject_a"].bgr)
        assert copy.sha256 != sha256_bytes(image_bytes["subject_a"])

    def test_never_upscales_a_small_image(self, decoded):
        image = decoded["subject_a"].bgr
        copy = build_search_copy(image)
        assert copy.width <= image.shape[1]
        assert copy.height <= image.shape[0]
        assert not copy.resized

    def test_preserves_aspect_ratio(self, decoded):
        import cv2

        original = decoded["subject_a"].bgr
        huge = cv2.resize(original, (original.shape[1] * 5, original.shape[0] * 5))
        copy = build_search_copy(huge)

        source_ratio = huge.shape[1] / huge.shape[0]
        copy_ratio = copy.width / copy.height
        assert copy_ratio == pytest.approx(source_ratio, rel=0.02)

    def test_a_tighter_budget_is_honoured(self, decoded):
        copy = build_search_copy(decoded["subject_a"].bgr, max_bytes=40_000)
        assert copy.byte_size <= 40_000

    def test_rejects_an_empty_image(self):
        import numpy as np

        with pytest.raises(InvalidImageError):
            build_search_copy(np.zeros((0, 0, 3), dtype=np.uint8))

    def test_the_copy_still_contains_a_detectable_face(self, decoded, detector):
        """A derivative small enough to upload is worthless if the search
        engine cannot see a face in it."""
        import cv2
        import numpy as np

        copy = build_search_copy(decoded["subject_a"].bgr)
        roundtrip = cv2.imdecode(np.frombuffer(copy.data, np.uint8), cv2.IMREAD_COLOR)
        assert detector.detect(roundtrip), "no face survived the search copy"

    def test_records_its_own_provenance(self, decoded):
        payload = build_search_copy(decoded["subject_a"].bgr).to_dict()
        assert payload["mime"] == "image/jpeg"
        assert payload["sha256"]
        assert payload["byte_size"] > 0
        assert "derivative" in payload["note"].lower()


def _provider(handler, key: str | None = "test-key", settings=None):
    """A GoogleLensProvider wired to a mock transport."""
    from raya.config import Settings

    settings = settings or Settings()
    settings = settings.model_copy(update={"serpapi_key": key})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GoogleLensProvider(settings, client=client)


class TestUpload:
    async def test_uploads_and_returns_an_image_id(self, decoded):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["method"] = request.method
            seen["content_type"] = request.headers.get("content-type", "")
            return httpx.Response(200, json={"image_id": "abc123", "message": "ok"})

        copy = build_search_copy(decoded["subject_a"].bgr)
        image_id = await _provider(handler).upload_image(copy.data, copy.mime)

        assert image_id == "abc123"
        assert seen["url"] == SERPAPI_UPLOAD_ENDPOINT
        assert seen["method"] == "POST"
        assert "multipart/form-data" in seen["content_type"]

    async def test_search_image_queries_lens_by_image_id(self, decoded):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if str(request.url).startswith(SERPAPI_UPLOAD_ENDPOINT):
                return httpx.Response(200, json={"image_id": "img_42"})
            return httpx.Response(
                200,
                json={
                    "search_metadata": {"id": "s1", "status": "Success"},
                    "visual_matches": [
                        {
                            "position": 1,
                            "title": "A post",
                            "link": "https://x.com/u/status/1",
                            "image": "https://cdn.example/1.jpg",
                            "source": "X",
                        }
                    ],
                },
            )

        copy = build_search_copy(decoded["subject_a"].bgr)
        response = await _provider(handler).search_image(copy.data, copy.mime)

        assert len(calls) == 2, "expected an upload then a search"
        search_url = str(calls[1].url)
        assert "image_id=img_42" in search_url
        assert "engine=google_lens" in search_url
        # The URL parameter must be absent: nothing was published to search.
        assert "url=" not in search_url

        assert len(response.results) == 1
        assert response.results[0].page_url == "https://x.com/u/status/1"
        assert response.provider_metadata["image_id"] == "img_42"
        assert response.provider_metadata["input_method"] == "direct_upload"

    async def test_missing_credentials_refuse_rather_than_fabricate(self, decoded):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("no request should be made without a key")

        copy = build_search_copy(decoded["subject_a"].bgr)
        provider = _provider(handler, key=None)

        assert not provider.configured
        with pytest.raises(SearchProviderNotConfiguredError):
            await provider.search_image(copy.data, copy.mime)

    async def test_oversized_upload_is_refused_locally(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("oversized payload should never be sent")

        oversized = b"\xff" * (SERPAPI_MAX_UPLOAD_BYTES + 1)
        with pytest.raises(SearchProviderError, match="limit"):
            await _provider(handler).upload_image(oversized, "image/jpeg")

    async def test_unsupported_mime_is_refused_locally(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("unsupported type should never be sent")

        with pytest.raises(SearchProviderError, match="JPEG"):
            await _provider(handler).upload_image(b"GIF89a", "image/gif")

    async def test_empty_payload_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("empty payload should never be sent")

        with pytest.raises(SearchProviderError):
            await _provider(handler).upload_image(b"", "image/jpeg")

    @pytest.mark.parametrize(
        "status,expected",
        [(401, SearchProviderNotConfiguredError), (413, SearchProviderError), (500, SearchProviderError)],
    )
    async def test_upload_http_errors_are_typed(self, status, expected):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": "nope"})

        with pytest.raises(expected):
            await _provider(handler).upload_image(b"x" * 100, "image/jpeg")

    async def test_upload_without_an_image_id_is_an_error(self):
        """A 200 that carries no id must not be treated as success."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": "Image uploaded successfully"})

        with pytest.raises(SearchProviderError, match="image_id"):
            await _provider(handler).upload_image(b"x" * 100, "image/jpeg")

    async def test_expired_image_id_surfaces_the_provider_error(self, decoded):
        """SerpApi expires an image_id after ~10 minutes; the resulting search
        error must reach the user rather than becoming an empty result set."""

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(SERPAPI_UPLOAD_ENDPOINT):
                return httpx.Response(200, json={"image_id": "stale"})
            return httpx.Response(200, json={"error": "Image has expired."})

        copy = build_search_copy(decoded["subject_a"].bgr)
        with pytest.raises(SearchProviderError, match="expired"):
            await _provider(handler).search_image(copy.data, copy.mime)

    async def test_a_timeout_is_reported_as_such(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("too slow")

        with pytest.raises(SearchProviderError, match="timed out"):
            await _provider(handler).upload_image(b"x" * 100, "image/jpeg")

    def test_provider_advertises_direct_upload(self):
        provider = GoogleLensProvider()
        assert provider.supports_direct_upload
        # No public hosting is required any more: this is what lets the
        # original input stay unpublished.
        assert not provider.requires_public_url
        assert provider.describe()["supports_direct_upload"] is True


class TestNullProviderRefusesBothRoutes:
    async def test_upload_route_refuses(self):
        from raya.search.fallback import NullProvider

        with pytest.raises(SearchProviderNotConfiguredError):
            await NullProvider().search_image(b"data", "image/jpeg")

    async def test_url_route_refuses(self):
        from raya.search.fallback import NullProvider

        with pytest.raises(SearchProviderNotConfiguredError):
            await NullProvider().search("https://example.com/x.jpg")
