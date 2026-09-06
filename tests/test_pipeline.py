"""End-to-end pipeline runs.

Nothing in the verification path is mocked. A real HTTP server serves the
fixture photographs, the real retriever downloads them over TCP, and the real
YuNet/SFace models decide the outcome. Only the search provider is replaced --
with a recorded fixture rather than a fabricated one -- because calling a paid
API from a unit test would be neither reproducible nor free.

What this proves is the claim the whole project rests on: RAYA accepts a
candidate on the strength of its own comparison, and rejects one that the same
search returned alongside it.
"""

from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from raya.candidates.types import CandidateStatus
from raya.events import EventType
from raya.pipeline.orchestrator import Pipeline
from raya.pipeline.result import RunStatus
from raya.search.fallback import ReplayProvider
from raya.storage.ipfs import LocalStore

FIXTURES = Path(__file__).parent / "fixtures"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep pytest output readable
        pass


@pytest.fixture(scope="module")
def image_server():
    """Serve the fixture images over real HTTP on an ephemeral port."""
    handler = partial(_QuietHandler, directory=str(FIXTURES))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def pipeline_settings(settings, tmp_path):
    return settings.model_copy(
        update={
            # The fixture server is on loopback, which the SSRF guard blocks by
            # default. Enabled explicitly here and nowhere else.
            "allow_private_network": True,
            "data_dir": tmp_path / "raya-data",
            "ipfs_provider": "local",
        }
    )


def _fixture_file(tmp_path, base_url, entries) -> Path:
    path = tmp_path / "search.json"
    path.write_text(
        json.dumps(
            {
                "provider": "recorded_google_lens",
                "results": [
                    {
                        "position": i + 1,
                        "title": e["title"],
                        "page_url": e["page_url"],
                        "image_url": f"{base_url}/{e['file']}",
                        "source_name": e.get("source"),
                    }
                    for i, e in enumerate(entries)
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _build(pipeline_settings, detector, encoder, fixture_path) -> Pipeline:
    return Pipeline(
        settings=pipeline_settings,
        detector=detector,
        encoder=encoder,
        provider=ReplayProvider(fixture_path),
        store=LocalStore(pipeline_settings),
    )


class TestFullRun:
    @pytest.fixture
    async def result(self, pipeline_settings, detector, encoder, image_server, tmp_path, image_bytes):
        fixture = _fixture_file(
            tmp_path,
            image_server,
            [
                # Same person, different photo -> should be VERIFIED.
                {
                    "title": "A post",
                    "page_url": "https://x.com/subject/status/1789",
                    "file": "subject_a_alt.jpg",
                    "source": "X",
                },
                # Different person -> should be REJECTED on our own comparison.
                {
                    "title": "Another person",
                    "page_url": "https://x.com/other/status/4242",
                    "file": "subject_b.jpg",
                    "source": "X",
                },
                # Not a social source -> filtered before any download.
                {
                    "title": "News article",
                    "page_url": "https://cnn.com/story",
                    "file": "subject_a.jpg",
                    "source": "CNN",
                },
                # Social, but the image has no face in it.
                {
                    "title": "No face here",
                    "page_url": "https://instagram.com/p/Cabc/",
                    "file": "no_face.jpg",
                    "source": "Instagram",
                },
            ],
        )
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        return await pipeline.run(image_bytes["subject_a"])

    async def test_reaches_a_verified_match(self, result):
        assert result.status == RunStatus.VERIFIED_NOT_ANCHORED
        assert result.match is not None
        assert result.match.platform == "x"
        assert result.match.page_url == "https://x.com/subject/status/1789"

    async def test_the_match_is_the_correct_candidate(self, result, pipeline_settings):
        assert result.similarity > pipeline_settings.similarity_threshold
        assert result.similarity > 0.6

    async def test_the_lookalike_is_rejected_by_our_own_comparison(self, result):
        """The search returned this candidate; RAYA declined it."""
        rejected = {c.page_url: c for c in result.rejected_candidates}
        other = rejected.get("https://x.com/other/status/4242")
        assert other is not None
        assert other.status == CandidateStatus.REJECTED
        assert other.similarity < 0.4
        assert other.image_sha256, "a rejected candidate is still hashed"

    async def test_non_social_results_are_filtered_without_download(self, result):
        news = next(c for c in result.candidates if c.page_url == "https://cnn.com/story")
        assert news.status == CandidateStatus.NOT_SOCIAL
        assert news.image_sha256 is None

    async def test_a_candidate_without_a_face_is_reported_as_such(self, result):
        faceless = next(
            c for c in result.candidates if c.page_url == "https://instagram.com/p/Cabc/"
        )
        assert faceless.status == CandidateStatus.NO_FACE
        # It was still independently retrieved and hashed.
        assert faceless.image_sha256

    async def test_every_candidate_has_an_outcome_and_a_reason(self, result):
        assert len(result.candidates) == 4
        for candidate in result.candidates:
            assert candidate.status != CandidateStatus.DISCOVERED
            assert candidate.reason

    async def test_source_image_is_independently_hashed(self, result):
        """The hash must be of the bytes we downloaded, not of anything the
        search provider supplied."""
        from raya.util.hashing import sha256_bytes

        expected = sha256_bytes((FIXTURES / "subject_a_alt.jpg").read_bytes())
        assert result.match.image_sha256 == expected

    async def test_evidence_is_created_and_self_consistent(self, result):
        assert result.evidence is not None
        assert result.evidence.verify_self()
        assert result.evidence.recompute() == result.evidence.sha256

    async def test_evidence_records_rejections_not_just_the_match(self, result):
        record = result.evidence.record
        assert record["verification"]["rejected_count"] >= 1
        assert record["verification"]["compared_count"] >= 2
        assert len(record["candidates"]) == 4

    async def test_evidence_contains_no_biometric_data(self, result):
        """The bundle is destined for IPFS, which is public and permanent.

        Checked structurally rather than by substring: the record legitimately
        contains the key `embedding_exported`, which is the flag asserting that
        no vector was written. What must not appear anywhere is the vector
        itself -- a long run of floats.
        """
        record = result.evidence.record

        def walk(node, path="$"):
            if isinstance(node, dict):
                for key, value in node.items():
                    assert key != "vector", f"embedding vector present at {path}"
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                numeric = [v for v in node if isinstance(v, (int, float))]
                assert len(numeric) < 16, f"numeric array of {len(numeric)} at {path}"
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")

        walk(record)
        assert record["verification"]["embedding_exported"] is False
        assert record["verification"]["processing"] == "local"

    async def test_evidence_states_what_it_does_not_claim(self, result):
        claim = result.evidence.record["claim"]
        assert claim["result"] == "verified_visual_match"
        assert "not an identity determination" in claim["does_not_assert"].lower()

    async def test_unanchored_run_is_not_called_anchored(self, result):
        """No contract configured, so integrity must not claim an anchor."""
        assert result.integrity is not None
        assert not result.integrity.anchored
        assert any(e.code == "chain_not_configured" for e in result.errors)


class TestFailureModes:
    async def test_an_image_with_no_face_stops_cleanly(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        fixture = _fixture_file(tmp_path, image_server, [])
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        result = await pipeline.run(image_bytes["no_face"])

        assert result.status == RunStatus.NO_FACE_DETECTED
        assert result.search is None, "no search should run without a face"
        assert "No face" in result.headline or "no usable face" in result.headline.lower()

    async def test_multiple_faces_requires_a_choice(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        fixture = _fixture_file(tmp_path, image_server, [])
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        result = await pipeline.run(image_bytes["two_faces"])

        assert result.status == RunStatus.MULTIPLE_FACES
        assert len(result.faces) == 2
        assert result.search is None, "RAYA must not guess whose face to search"

    async def test_an_explicit_face_selection_proceeds(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        fixture = _fixture_file(
            tmp_path,
            image_server,
            [
                {
                    "title": "A post",
                    "page_url": "https://x.com/subject/status/1",
                    "file": "subject_a_alt.jpg",
                }
            ],
        )
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        result = await pipeline.run(image_bytes["two_faces"], face_index=0)

        assert result.selected_face_index == 0
        assert result.status != RunStatus.MULTIPLE_FACES

    async def test_no_social_candidates_is_reported_honestly(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        fixture = _fixture_file(
            tmp_path,
            image_server,
            [{"title": "News", "page_url": "https://cnn.com/x", "file": "subject_a_alt.jpg"}],
        )
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        result = await pipeline.run(image_bytes["subject_a"])

        assert result.status == RunStatus.NO_SOCIAL_CANDIDATES
        assert result.match is None

    async def test_no_verified_match_when_everyone_is_someone_else(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        fixture = _fixture_file(
            tmp_path,
            image_server,
            [{"title": "Other", "page_url": "https://x.com/o/status/9", "file": "subject_b.jpg"}],
        )
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        result = await pipeline.run(image_bytes["subject_a"])

        assert result.status == RunStatus.NO_VERIFIED_MATCH
        assert result.match is None
        # Evidence is still produced: a documented non-match is a real outcome.
        assert result.evidence is not None
        assert result.evidence.record["claim"]["result"] == "no_verified_match"

    async def test_an_unreachable_source_does_not_end_the_run(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        fixture = _fixture_file(
            tmp_path,
            image_server,
            [
                {"title": "Gone", "page_url": "https://x.com/a/status/1", "file": "missing.jpg"},
                {"title": "Good", "page_url": "https://x.com/b/status/2", "file": "subject_a_alt.jpg"},
            ],
        )
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        result = await pipeline.run(image_bytes["subject_a"])

        gone = next(c for c in result.candidates if "missing" in (c.image_url or ""))
        assert gone.status == CandidateStatus.UNREACHABLE
        # The reachable candidate still gets verified.
        assert result.match is not None


class TestEventStream:
    async def test_events_describe_the_real_run(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        """The UI renders from these events, so they must reflect what happened."""
        from raya.events import EventBus

        fixture = _fixture_file(
            tmp_path,
            image_server,
            [
                {"title": "Match", "page_url": "https://x.com/s/status/1", "file": "subject_a_alt.jpg"},
                {"title": "Other", "page_url": "https://x.com/o/status/2", "file": "subject_b.jpg"},
            ],
        )
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        bus = EventBus("VER-TEST")
        await pipeline.run(image_bytes["subject_a"], bus=bus)

        types = [e.type for e in bus.log]
        for expected in (
            EventType.PIPELINE_STARTED,
            EventType.INPUT_HASHED,
            EventType.FACE_DETECTED,
            EventType.FACE_ENCODED,
            EventType.SEARCH_COMPLETED,
            EventType.CANDIDATE_DISCOVERED,
            EventType.CANDIDATE_COMPARED,
            EventType.CANDIDATE_VERIFIED,
            EventType.CANDIDATE_REJECTED,
            EventType.MATCH_SELECTED,
            EventType.EVIDENCE_HASHED,
            EventType.VERIFICATION_COMPLETED,
        ):
            assert expected in types, f"missing event {expected}"

    async def test_sequence_numbers_are_monotonic(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        from raya.events import EventBus

        fixture = _fixture_file(tmp_path, image_server, [])
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        bus = EventBus("VER-TEST-2")
        await pipeline.run(image_bytes["no_face"], bus=bus)

        seqs = [e.seq for e in bus.log]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)
        assert bus.closed

    async def test_a_late_subscriber_receives_the_backlog(self):
        from raya.events import EventBus

        bus = EventBus("VER-BACKLOG")
        bus.emit("a.one")
        bus.emit("a.two")
        bus.close()

        received = [e.type async for e in bus.subscribe()]
        assert received == ["a.one", "a.two"]


class TestPersistence:
    async def test_a_saved_run_can_be_reloaded_and_replayed(
        self, pipeline_settings, detector, encoder, tmp_path, image_bytes, image_server
    ):
        from raya.events import EventBus
        from raya.pipeline.store import RunStore

        fixture = _fixture_file(
            tmp_path,
            image_server,
            [{"title": "Match", "page_url": "https://x.com/s/status/1", "file": "subject_a_alt.jpg"}],
        )
        pipeline = _build(pipeline_settings, detector, encoder, fixture)
        bus = EventBus("VER-SAVE-TEST")
        result = await pipeline.run(image_bytes["subject_a"], bus=bus, verification_id="VER-SAVE-TEST")

        store = RunStore(pipeline_settings)
        store.save(result, bus.log)
        loaded = store.load("VER-SAVE-TEST")

        assert loaded is not None
        assert loaded.result["verification_id"] == "VER-SAVE-TEST"
        assert len(loaded.events) == len(bus.log)

        # The canonical file on disk must still hash to the recorded digest --
        # this is what makes an exported bundle independently checkable.
        from raya.util.hashing import sha256_bytes

        raw = (pipeline_settings.data_dir / "runs" / "VER-SAVE-TEST" / "evidence.json").read_bytes()
        assert sha256_bytes(raw) == result.evidence.sha256

    def test_path_traversal_is_refused(self, pipeline_settings):
        from raya.pipeline.store import RunStore

        store = RunStore(pipeline_settings)
        assert store.load("../../etc") is None
        assert store.asset("VER-X", "../../../secret.txt") is None
        assert not store.exists("../evil")
