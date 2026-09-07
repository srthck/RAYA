"""The candidate retrieval cascade.

One image URL is not enough in practice: platform crawler endpoints serve HTML
to non-browser clients, and provider thumbnails are frequently too small to
compare. These tests pin the cascade's order, its honesty about what it tried,
and -- most importantly -- that widening retrieval did not widen the SSRF
surface. Every URL the cascade discovers is attacker-influenced, including the
ones extracted from a source page.

All HTTP is mocked. Nothing here touches a live social platform.

Hostnames are the reserved example.* domains because `assert_safe_url`
resolves every host for real before any request -- that is the SSRF guard
doing its job, and a fictional subdomain would be refused before the mock
transport was ever reached.
"""

from __future__ import annotations

import cv2
import httpx
import numpy as np
import pytest

from raya.candidates.retriever import (
    CandidateRetriever,
    RetrievalAttempt,
    extract_image_urls,
)
from raya.candidates.types import Candidate, CandidateStatus
from raya.candidates.verifier import CandidateVerifier


# ---- helpers ---------------------------------------------------------------


def _jpeg(bgr) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    assert ok
    return buf.tobytes()


def _face_bytes(fixture: str, scale: float = 1.0) -> bytes:
    """Re-encode a fixture, optionally scaled, as fresh JPEG bytes."""
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / fixture
    image = cv2.imread(str(path))
    if scale != 1.0:
        image = cv2.resize(
            image,
            (max(1, int(image.shape[1] * scale)), max(1, int(image.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return _jpeg(image)


def _blank(width: int = 400, height: int = 300) -> bytes:
    return _jpeg(np.full((height, width, 3), 200, dtype=np.uint8))


def _routes(mapping: dict[str, httpx.Response]):
    """A mock transport that answers exactly the URLs given."""

    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in mapping:
            return mapping[key]
        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler)


def _retriever(settings, mapping) -> CandidateRetriever:
    permissive = settings.model_copy(update={"allow_private_network": True})
    client = httpx.AsyncClient(transport=_routes(mapping), follow_redirects=True)
    return CandidateRetriever(permissive, client=client)


def _candidate(**kwargs) -> Candidate:
    base = dict(
        id="c001",
        position=1,
        title="A post",
        page_url="https://x.com/u/status/1",
        image_url=None,
        thumbnail_url=None,
        source_name="X",
        platform="x",
        platform_label="X",
        is_social=True,
        is_post_url=True,
    )
    base.update(kwargs)
    return Candidate(**base)


# ---- metadata extraction ---------------------------------------------------


class TestMetadataExtraction:
    def test_reads_the_public_declarations_a_page_makes(self):
        html = """
        <meta property="og:image" content="https://cdn.example.com/og.jpg">
        <meta name="twitter:image" content="/card.png">
        <link rel="image_src" href="https://cdn.example.com/legacy.jpg">
        <script type="application/ld+json">{"image":{"url":"https://cdn.example.com/ld.jpg"}}</script>
        """
        urls = extract_image_urls(html, "https://x.com/u/status/1")
        assert "https://cdn.example.com/og.jpg" in urls
        # Relative URLs resolve against the page they were found on.
        assert "https://x.com/card.png" in urls
        assert "https://cdn.example.com/legacy.jpg" in urls
        assert "https://cdn.example.com/ld.jpg" in urls

    def test_order_is_deterministic_and_deduplicated(self):
        html = (
            '<meta property="og:image" content="https://e.com/a.jpg">'
            '<meta name="twitter:image" content="https://e.com/a.jpg">'
            '<link rel="image_src" href="https://e.com/b.jpg">'
        )
        urls = extract_image_urls(html, "https://e.com/p")
        assert urls == ["https://e.com/a.jpg", "https://e.com/b.jpg"]

    def test_ignores_data_uris_and_malformed_json_ld(self):
        html = (
            '<meta property="og:image" content="data:image/png;base64,AAAA">'
            '<script type="application/ld+json">{ this is not json </script>'
            '<meta name="twitter:image" content="https://e.com/ok.jpg">'
        )
        assert extract_image_urls(html, "https://e.com/p") == ["https://e.com/ok.jpg"]

    def test_returns_nothing_for_a_page_without_image_metadata(self):
        assert extract_image_urls("<html><body>hi</body></html>", "https://e.com") == []


# ---- the cascade -----------------------------------------------------------


class TestCascade:
    @pytest.fixture
    def permissive(self, settings):
        return settings.model_copy(update={"allow_private_network": True})

    def _verifier(self, detector, encoder, permissive, mapping):
        return CandidateVerifier(
            detector,
            encoder,
            retriever=_retriever(permissive, mapping),
            settings=permissive,
        )

    async def test_direct_image_succeeds_without_touching_the_page(
        self, detector, encoder, permissive, embeddings
    ):
        img = "https://example.com/full.jpg"
        page = "https://x.com/u/status/1"
        mapping = {
            img: httpx.Response(
                200, content=_face_bytes("subject_a_alt.jpg"), headers={"content-type": "image/jpeg"}
            ),
            # If the page is fetched at all this test should fail loudly.
            page: httpx.Response(500, text="should not be requested"),
        }
        verifier = self._verifier(detector, encoder, permissive, mapping)
        candidate = _candidate(image_url=img, page_url=page)

        await verifier.verify_one(candidate, embeddings["subject_a"])

        assert candidate.status == CandidateStatus.VERIFIED
        assert candidate.image_sha256
        assert [a["source"] for a in candidate.attempts] == ["image_url"]

    async def test_html_response_falls_through_to_the_thumbnail(
        self, detector, encoder, permissive, embeddings
    ):
        """The Meta `lookaside.*` case: an image URL that serves HTML."""
        img = "https://example.net/crawler?media_id=1"
        thumb = "https://example.org/thumb.jpg"
        mapping = {
            img: httpx.Response(200, text="<html>nope</html>", headers={"content-type": "text/html"}),
            thumb: httpx.Response(
                200, content=_face_bytes("subject_a_alt.jpg"), headers={"content-type": "image/jpeg"}
            ),
        }
        verifier = self._verifier(detector, encoder, permissive, mapping)
        candidate = _candidate(image_url=img, thumbnail_url=thumb)

        await verifier.verify_one(candidate, embeddings["subject_a"])

        assert candidate.status == CandidateStatus.VERIFIED
        sources = [a["source"] for a in candidate.attempts]
        assert sources == ["image_url", "thumbnail_url"]
        # The HTML attempt is recorded, not silently dropped.
        assert candidate.attempts[0]["ok"] is False
        assert "not an image" in (candidate.attempts[0]["reason"] or "")

    async def test_tiny_thumbnail_falls_through_to_page_metadata(
        self, detector, encoder, permissive, embeddings
    ):
        """The X preview case: a real image, but the face is unusably small."""
        thumb = "https://example.org/tiny.jpg"
        page = "https://x.com/u/status/1"
        big = "https://example.net/original.jpg"
        mapping = {
            thumb: httpx.Response(
                200,
                # Large enough to decode (min 64px), but the face inside is
                # ~28px -- below the 48px minimum for a reliable comparison.
                content=_face_bytes("subject_a_alt.jpg", scale=0.15),
                headers={"content-type": "image/jpeg"},
            ),
            page: httpx.Response(
                200,
                text=f'<meta property="og:image" content="{big}">',
                headers={"content-type": "text/html"},
            ),
            big: httpx.Response(
                200, content=_face_bytes("subject_a_alt.jpg"), headers={"content-type": "image/jpeg"}
            ),
        }
        verifier = self._verifier(detector, encoder, permissive, mapping)
        candidate = _candidate(image_url=thumb, page_url=page)

        await verifier.verify_one(candidate, embeddings["subject_a"])

        assert candidate.status == CandidateStatus.VERIFIED
        assert [a["source"] for a in candidate.attempts] == ["image_url", "page_metadata"]
        assert "below the" in (candidate.attempts[0]["reason"] or "")

    async def test_a_retrieved_but_faceless_image_is_still_hashed(
        self, detector, encoder, permissive, embeddings
    ):
        """"Retrieved and hashed, but no face" beats "no face" with nothing."""
        img = "https://example.com/scenery.jpg"
        mapping = {img: httpx.Response(200, content=_blank(), headers={"content-type": "image/jpeg"})}
        verifier = self._verifier(detector, encoder, permissive, mapping)
        candidate = _candidate(image_url=img, page_url=None)

        await verifier.verify_one(candidate, embeddings["subject_a"])

        assert candidate.status == CandidateStatus.NO_FACE
        assert candidate.image_sha256, "the bytes were downloaded, so prove it"
        assert candidate.attempts[0]["sha256"] == candidate.image_sha256

    async def test_a_different_person_is_rejected_not_verified(
        self, detector, encoder, permissive, embeddings
    ):
        img = "https://example.com/other.jpg"
        mapping = {
            img: httpx.Response(
                200, content=_face_bytes("subject_b.jpg"), headers={"content-type": "image/jpeg"}
            )
        }
        verifier = self._verifier(detector, encoder, permissive, mapping)
        candidate = _candidate(image_url=img, page_url=None)

        await verifier.verify_one(candidate, embeddings["subject_a"])

        assert candidate.status == CandidateStatus.REJECTED
        assert candidate.verdict.similarity < permissive.similarity_threshold

    async def test_exhausting_the_cascade_reports_unreachable_with_a_reason(
        self, detector, encoder, permissive, embeddings
    ):
        mapping = {}  # everything 404s
        verifier = self._verifier(detector, encoder, permissive, mapping)
        candidate = _candidate(
            image_url="https://example.com/gone.jpg",
            thumbnail_url="https://example.org/gone-too.jpg",
            page_url="https://x.com/u/status/1",
        )

        await verifier.verify_one(candidate, embeddings["subject_a"])

        assert candidate.status == CandidateStatus.UNREACHABLE
        assert candidate.reason
        assert len(candidate.attempts) == 2  # both direct URLs tried and recorded


# ---- the cascade must not widen the SSRF surface ---------------------------


class TestCascadeSecurity:
    async def test_page_metadata_pointing_at_a_private_address_is_refused(self, settings):
        """A source page is attacker-influenced, so the URLs it declares are too."""
        page = "https://example.net/post"
        mapping = {
            page: httpx.Response(
                200,
                text=(
                    '<meta property="og:image" content="http://169.254.169.254/latest/meta-data/">'
                    '<meta name="twitter:image" content="http://10.0.0.5/internal.png">'
                ),
                headers={"content-type": "text/html"},
            )
        }
        # Default settings: the SSRF guard is ON, as in production.
        retriever = CandidateRetriever(
            settings, client=httpx.AsyncClient(transport=_routes(mapping), follow_redirects=True)
        )
        assert await retriever.fetch_page_image_urls(page) == []

    async def test_a_page_that_is_not_html_yields_nothing(self, settings):
        page = "https://example.com/thing"
        mapping = {page: httpx.Response(200, content=b"\x00\x01", headers={"content-type": "application/octet-stream"})}
        permissive = settings.model_copy(update={"allow_private_network": True})
        retriever = _retriever(permissive, mapping)
        assert await retriever.fetch_page_image_urls(page) == []

    async def test_a_private_page_url_is_never_fetched(self, settings):
        """The guard applies before the request, not after."""
        retriever = CandidateRetriever(settings)
        assert await retriever.fetch_page_image_urls("http://127.0.0.1:8000/admin") == []

    async def test_html_is_never_accepted_as_an_image(self, settings):
        url = "https://example.com/page"
        mapping = {url: httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})}
        permissive = settings.model_copy(update={"allow_private_network": True})
        retriever = _retriever(permissive, mapping)
        from raya.errors import SourceUnreachableError

        with pytest.raises(SourceUnreachableError):
            await retriever.fetch(url)


class TestAttemptRecord:
    def test_serialises_every_field_a_reviewer_needs(self):
        attempt = RetrievalAttempt(
            url="https://e.com/a.jpg", source="image_url", ok=False, reason="nope"
        )
        payload = attempt.to_dict()
        for key in (
            "url", "source", "ok", "final_url", "http_status",
            "content_type", "byte_size", "sha256", "decoded",
            "width", "height", "reason",
        ):
            assert key in payload
