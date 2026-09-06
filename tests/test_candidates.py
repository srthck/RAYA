"""Platform classification and safe candidate retrieval."""

from __future__ import annotations

import pytest

from raya.candidates.platforms import classify_url
from raya.candidates.retriever import UnsafeUrlError, assert_safe_url
from raya.candidates.types import Candidate, CandidateStatus
from raya.errors import SourceUnreachableError


class TestPlatformClassification:
    @pytest.mark.parametrize(
        "url,platform",
        [
            ("https://x.com/someone/status/1789", "x"),
            ("https://twitter.com/someone/status/1789", "x"),
            ("https://www.instagram.com/p/Cxyz123/", "instagram"),
            ("https://instagram.com/reel/Cxyz123/", "instagram"),
            ("https://www.facebook.com/user/posts/123", "facebook"),
            ("https://www.linkedin.com/posts/someone_activity-123", "linkedin"),
            ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
            ("https://www.tiktok.com/@user/video/123", "tiktok"),
            ("https://www.reddit.com/r/pics/comments/abc/title/", "reddit"),
            ("https://bsky.app/profile/u/post/abc", "bluesky"),
        ],
    )
    def test_recognises_social_platforms(self, url, platform):
        result = classify_url(url)
        assert result.platform_key == platform
        assert result.is_social

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.cnn.com/2026/01/01/story.html",
            "https://en.wikipedia.org/wiki/Example",
            "https://shutterstock.com/image-photo/x-123",
            "https://some-random-blog.example/post",
        ],
    )
    def test_rejects_non_social_sources(self, url):
        result = classify_url(url)
        assert result.platform_key == "other"
        assert not result.is_social

    def test_distinguishes_a_post_from_a_profile(self):
        """A post URL cites a specific item; a profile URL does not."""
        assert classify_url("https://x.com/someone/status/1789").is_post_url
        assert not classify_url("https://x.com/someone").is_post_url
        assert classify_url("https://www.instagram.com/p/Cxyz/").is_post_url
        assert not classify_url("https://www.instagram.com/someone/").is_post_url

    def test_ignores_presentation_subdomains(self):
        for url in (
            "https://www.x.com/u/status/1",
            "https://m.x.com/u/status/1",
            "https://mobile.twitter.com/u/status/1",
        ):
            assert classify_url(url).platform_key == "x"

    def test_handles_missing_and_malformed_urls(self):
        for url in (None, "", "not-a-url", "javascript:alert(1)"):
            assert not classify_url(url).is_social


class TestSsrfGuard:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/image.jpg",
            "http://localhost:5001/api/v0/add",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://10.0.0.5/x.png",
            "http://192.168.1.1/x.png",
            "http://[::1]/x.png",
        ],
    )
    def test_blocks_private_and_loopback_addresses(self, url):
        """The URLs we fetch come from a third-party API, so this is a real
        SSRF surface, not a theoretical one."""
        with pytest.raises(SourceUnreachableError):
            assert_safe_url(url)

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "gopher://x"])
    def test_blocks_non_http_schemes(self, url):
        with pytest.raises(UnsafeUrlError):
            assert_safe_url(url)

    def test_blocks_a_url_without_a_host(self):
        with pytest.raises(UnsafeUrlError):
            assert_safe_url("http:///x.jpg")

    def test_can_be_enabled_for_local_fixtures(self, settings):
        """Tests serve fixtures from localhost, so the guard is configurable --
        but only via an explicit setting that defaults to off."""
        permissive = settings.model_copy(update={"allow_private_network": True})
        assert_safe_url("http://127.0.0.1:9/image.jpg", permissive)


class TestCandidateFiltering:
    def _results(self):
        from raya.search.base import SearchResult

        return [
            SearchResult(1, "A post", "https://x.com/u/status/1", "https://img/1.jpg", None, "X"),
            SearchResult(2, "News", "https://cnn.com/story", "https://img/2.jpg", None, "CNN"),
            SearchResult(3, "No image", "https://x.com/u/status/3", None, None, "X"),
        ]

    @pytest.fixture
    def verifier(self, detector, encoder, settings):
        from raya.candidates.verifier import CandidateVerifier

        return CandidateVerifier(detector, encoder, settings=settings)

    def test_keeps_every_result_and_labels_it(self, verifier):
        """Nothing is silently dropped: the evidence record has to be able to
        state how many results were returned versus eligible."""
        candidates = verifier.build_candidates(self._results())
        assert len(candidates) == 3

        by_id = {c.id: c for c in candidates}
        assert by_id["c001"].status == CandidateStatus.DISCOVERED
        assert by_id["c002"].status == CandidateStatus.NOT_SOCIAL
        assert by_id["c003"].status == CandidateStatus.NO_IMAGE_URL

    def test_every_filtered_candidate_carries_a_reason(self, verifier):
        for candidate in verifier.build_candidates(self._results()):
            if candidate.status != CandidateStatus.DISCOVERED:
                assert candidate.reason

    def test_serialisation_omits_the_preview_bytes(self, verifier):
        candidate = verifier.build_candidates(self._results())[0]
        candidate.thumbnail_png = b"\xff\xd8binary"
        payload = candidate.to_dict()
        assert payload["has_preview"] is True
        assert "thumbnail_png" not in payload


class TestCandidateStatus:
    def test_verified_is_the_only_non_failure_terminal_state(self):
        assert not CandidateStatus.VERIFIED.is_terminal_failure
        for status in (
            CandidateStatus.REJECTED,
            CandidateStatus.NO_FACE,
            CandidateStatus.UNREACHABLE,
            CandidateStatus.NOT_SOCIAL,
        ):
            assert status.is_terminal_failure

    def test_only_compared_states_report_a_comparison(self):
        assert CandidateStatus.VERIFIED.was_compared
        assert CandidateStatus.REJECTED.was_compared
        assert not CandidateStatus.NO_FACE.was_compared
        assert not CandidateStatus.UNREACHABLE.was_compared
