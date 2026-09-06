"""Independent verification of discovered candidates.

This is the centre of RAYA. Everything before it is discovery; everything after
it is preservation. The rule enforced here is a single sentence:

    the search engine proposes, RAYA decides.

For each candidate we re-download the image, detect a face with our own
detector, embed it with our own encoder, and compare it against the subject
embedding. A candidate is accepted only if that similarity score clears the
threshold. The search provider's opinion that two images are visually related
carries no weight in the decision.

Every candidate is evaluated and every outcome recorded. Rejections are kept
and surfaced rather than swallowed, because the rejections are what show the
pipeline is reasoning over candidates instead of rubber-stamping the first one.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from ..config import Settings, get_settings
from ..errors import FaceTooSmallError, RayaError, SourceUnreachableError
from ..events import EventBus, EventType
from ..face.base import FaceDetector, FaceEncoder
from ..face.types import FaceEmbedding
from ..search.base import SearchResult
from ..util.imaging import decode_image, encode_jpeg
from .platforms import classify_url
from .retriever import CandidateRetriever
from .types import STATUS_REASONS, Candidate, CandidateStatus, CandidateVerdict

# The preview shown beside the input face in the UI. Small on purpose: it is an
# illustration for a human, never the artifact we hashed.
PREVIEW_MAX_EDGE = 320


class CandidateVerifier:
    def __init__(
        self,
        detector: FaceDetector,
        encoder: FaceEncoder,
        retriever: CandidateRetriever | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.detector = detector
        self.encoder = encoder
        self.retriever = retriever or CandidateRetriever(self.settings)

    # ---- stage 05: filtering ----------------------------------------------

    def build_candidates(
        self, results: list[SearchResult], bus: EventBus | None = None
    ) -> list[Candidate]:
        """Turn raw search results into classified candidates.

        Nothing is discarded here. Non-social results are marked NOT_SOCIAL and
        kept, so the evidence record can state honestly how many results the
        search returned versus how many were eligible for verification.
        """
        candidates: list[Candidate] = []
        for index, result in enumerate(results):
            classification = classify_url(result.page_url)
            candidate = Candidate(
                id=f"c{index + 1:03d}",
                position=result.position,
                title=result.title,
                page_url=result.page_url,
                image_url=result.image_url,
                thumbnail_url=result.thumbnail_url,
                source_name=result.source_name,
                platform=classification.platform_key,
                platform_label=classification.platform_label,
                is_social=classification.is_social,
                is_post_url=classification.is_post_url,
            )
            if not classification.is_social:
                candidate.status = CandidateStatus.NOT_SOCIAL
                candidate.reason = STATUS_REASONS[CandidateStatus.NOT_SOCIAL]
            elif not candidate.image_url:
                candidate.status = CandidateStatus.NO_IMAGE_URL
                candidate.reason = STATUS_REASONS[CandidateStatus.NO_IMAGE_URL]

            candidates.append(candidate)
            if bus:
                bus.emit(EventType.CANDIDATE_DISCOVERED, candidate=candidate.to_dict())

        if bus:
            bus.emit(
                EventType.CANDIDATE_CLASSIFIED,
                total=len(candidates),
                social=sum(1 for c in candidates if c.is_social),
                eligible=sum(
                    1 for c in candidates if c.status == CandidateStatus.DISCOVERED
                ),
                by_platform=_count_by_platform(candidates),
            )
        return candidates

    # ---- stage 06: verification -------------------------------------------

    async def verify_all(
        self,
        candidates: list[Candidate],
        subject: FaceEmbedding,
        bus: EventBus | None = None,
        concurrency: int = 4,
    ) -> list[Candidate]:
        """Evaluate every eligible candidate with bounded concurrency.

        The cap keeps us a polite client of the sites we fetch from, and keeps
        peak memory bounded when several large images arrive at once.
        """
        eligible = [c for c in candidates if c.status == CandidateStatus.DISCOVERED]
        eligible = eligible[: self.settings.max_verified_candidates]

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def run(candidate: Candidate) -> None:
            async with semaphore:
                await self.verify_one(candidate, subject, bus)

        await asyncio.gather(*(run(c) for c in eligible))
        return candidates

    async def verify_one(
        self, candidate: Candidate, subject: FaceEmbedding, bus: EventBus | None = None
    ) -> Candidate:
        started = time.perf_counter()
        if bus:
            bus.emit(EventType.CANDIDATE_EVALUATING, candidate_id=candidate.id)

        try:
            await self._evaluate(candidate, subject, bus)
        except SourceUnreachableError as exc:
            self._fail(candidate, CandidateStatus.UNREACHABLE, exc.message)
        except FaceTooSmallError as exc:
            self._fail(candidate, CandidateStatus.FACE_TOO_SMALL, exc.message)
        except RayaError as exc:
            self._fail(candidate, CandidateStatus.UNDECODABLE, exc.message)
        except Exception as exc:  # noqa: BLE001 - one bad candidate must not end the run
            self._fail(candidate, CandidateStatus.ERROR, f"Evaluation failed: {exc}")

        candidate.duration_ms = int((time.perf_counter() - started) * 1000)

        if bus:
            event = (
                EventType.CANDIDATE_VERIFIED
                if candidate.verified
                else EventType.CANDIDATE_REJECTED
            )
            bus.emit(event, candidate=candidate.to_dict())
        return candidate

    async def _evaluate(
        self, candidate: Candidate, subject: FaceEmbedding, bus: EventBus | None
    ) -> None:
        # 1. Retrieve the image ourselves, and hash exactly what arrived.
        retrieved = await self.retriever.fetch(candidate.image_url)
        candidate.image_sha256 = retrieved.sha256
        candidate.image_bytes = retrieved.byte_size
        candidate.image_mime = retrieved.mime
        candidate.fetched_url = retrieved.final_url
        candidate.http_status = retrieved.http_status
        if bus:
            bus.emit(
                EventType.CANDIDATE_FETCHED,
                candidate_id=candidate.id,
                sha256=retrieved.sha256,
                bytes=retrieved.byte_size,
                mime=retrieved.mime,
                duration_ms=retrieved.duration_ms,
            )

        # 2. Decode in a worker thread so the event loop keeps serving SSE.
        decoded = await asyncio.to_thread(decode_image, retrieved.data, self.settings)
        candidate.image_width = decoded.width
        candidate.image_height = decoded.height

        # 3. Detect with our own detector.
        faces = await asyncio.to_thread(self.detector.detect, decoded.bgr)
        candidate.face_count = len(faces)
        if not faces:
            self._fail(candidate, CandidateStatus.NO_FACE)
            return

        if bus:
            bus.emit(
                EventType.CANDIDATE_FACE_FOUND,
                candidate_id=candidate.id,
                face_count=len(faces),
            )

        # 4. Score every face in the candidate image and keep the best. A group
        #    photo containing the subject is a legitimate match, so scoring only
        #    the largest face would miss real hits.
        best_score: Optional[float] = None
        best_face = None
        for face in faces:
            if face.quality.size_px < self.settings.min_face_size_px:
                continue
            embedding = await asyncio.to_thread(self.encoder.encode, decoded.bgr, face)
            score = await asyncio.to_thread(self.encoder.similarity, subject, embedding)
            if best_score is None or score > best_score:
                best_score, best_face = score, face

        if best_score is None:
            self._fail(candidate, CandidateStatus.FACE_TOO_SMALL)
            return

        candidate.face_quality = best_face.quality.to_dict()
        threshold = self.settings.similarity_threshold
        passed = best_score >= threshold
        candidate.verdict = CandidateVerdict(
            similarity=best_score,
            threshold=threshold,
            metric=self.encoder.metric,
            passed=passed,
        )
        candidate.status = (
            CandidateStatus.VERIFIED if passed else CandidateStatus.REJECTED
        )
        candidate.reason = STATUS_REASONS[candidate.status]
        candidate.thumbnail_png = _preview(decoded.bgr, best_face)

        if bus:
            bus.emit(
                EventType.CANDIDATE_COMPARED,
                candidate_id=candidate.id,
                similarity=round(best_score, 6),
                threshold=threshold,
                passed=passed,
            )

    @staticmethod
    def _fail(
        candidate: Candidate, status: CandidateStatus, reason: str | None = None
    ) -> None:
        candidate.status = status
        candidate.reason = reason or STATUS_REASONS.get(status, "Candidate rejected.")


def _preview(bgr, face) -> bytes | None:
    """Crop a padded face preview for the side-by-side comparison view."""
    try:
        import cv2

        x, y, w, h = face.bbox
        pad = int(max(w, h) * 0.35)
        height, width = bgr.shape[:2]
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(width, x + w + pad), min(height, y + h + pad)
        crop = bgr[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        scale = PREVIEW_MAX_EDGE / max(crop.shape[0], crop.shape[1])
        if scale < 1:
            crop = cv2.resize(
                crop,
                (int(crop.shape[1] * scale), int(crop.shape[0] * scale)),
                interpolation=cv2.INTER_AREA,
            )
        return encode_jpeg(crop, quality=86)
    except Exception:  # noqa: BLE001 - a missing preview must never fail a run
        return None


def _count_by_platform(candidates: list[Candidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.platform] = counts.get(candidate.platform, 0) + 1
    return counts
