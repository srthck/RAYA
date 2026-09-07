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
from .retriever import CandidateRetriever, RetrievalAttempt
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
        """Retrieve a usable image for this candidate, then compare it.

        Tries a bounded cascade rather than a single URL, because one URL is
        not enough in practice: platform crawler endpoints often serve HTML to
        non-browser clients, and provider thumbnails are often too small to
        compare. Order is fixed and every attempt is recorded.
        """
        usable = await self._retrieve_usable_image(candidate, bus)
        if usable is None:
            # `_retrieve_usable_image` has already set the most specific status
            # it could determine from the attempts it made.
            return

        decoded, faces, retrieved = usable

        candidate.image_sha256 = retrieved.sha256
        candidate.image_bytes = retrieved.byte_size
        candidate.image_mime = retrieved.mime
        candidate.fetched_url = retrieved.final_url
        candidate.http_status = retrieved.http_status
        candidate.image_width = decoded.width
        candidate.image_height = decoded.height
        candidate.face_count = len(faces)

        if bus:
            bus.emit(
                EventType.CANDIDATE_FETCHED,
                candidate_id=candidate.id,
                sha256=retrieved.sha256,
                bytes=retrieved.byte_size,
                mime=retrieved.mime,
                attempts=len(candidate.attempts),
            )
            bus.emit(
                EventType.CANDIDATE_FACE_FOUND,
                candidate_id=candidate.id,
                face_count=len(faces),
            )

        # Score every sufficiently large face and keep the best. A group photo
        # containing the subject is a legitimate match, so scoring only the
        # largest face would miss real hits.
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

    async def _retrieve_usable_image(self, candidate: Candidate, bus: EventBus | None):
        """Walk the cascade until an image yields a face big enough to compare.

        Order, deliberately fixed so runs are reproducible:

          1. the provider's primary image URL
          2. the provider's thumbnail
          3. images the *source page* publicly declares (og:image, twitter:image,
             link rel=image_src, JSON-LD)

        Step 3 costs an extra request, so it is only reached when the direct
        URLs produced nothing usable. Returns the first usable candidate, or
        None having set the most specific failure status observed.
        """
        direct: list[tuple[str, str]] = []
        for url, source in (
            (candidate.image_url, "image_url"),
            (candidate.thumbnail_url, "thumbnail_url"),
        ):
            if url and all(url != seen for seen, _ in direct):
                direct.append((url, source))

        best_effort = await self._try_sources(candidate, direct, bus)
        if best_effort is not None:
            return best_effort

        # Nothing direct worked. Ask the public source page what image it
        # declares for external consumers.
        if candidate.page_url:
            page_urls = await self.retriever.fetch_page_image_urls(candidate.page_url)
            tried = {url for url, _ in direct}
            from_page = [(u, "page_metadata") for u in page_urls if u not in tried]
            if from_page:
                best_effort = await self._try_sources(candidate, from_page, bus)
                if best_effort is not None:
                    return best_effort

        self._set_cascade_failure(candidate)
        return None

    async def _try_sources(
        self, candidate: Candidate, sources: list[tuple[str, str]], bus: EventBus | None
    ):
        """Try each URL in turn, recording the outcome of every one."""
        for url, origin in sources:
            attempt = RetrievalAttempt(url=url, source=origin, ok=False)
            try:
                retrieved = await self.retriever.fetch(url)
            except SourceUnreachableError as exc:
                attempt.reason = exc.message
                candidate.attempts.append(attempt.to_dict())
                continue
            except RayaError as exc:
                attempt.reason = exc.message
                candidate.attempts.append(attempt.to_dict())
                continue

            attempt.final_url = retrieved.final_url
            attempt.http_status = retrieved.http_status
            attempt.content_type = retrieved.mime
            attempt.byte_size = retrieved.byte_size
            attempt.sha256 = retrieved.sha256

            # The bytes were independently retrieved and hashed. Record that on
            # the candidate now, before we know whether the image is usable:
            # "retrieved and hashed, but no face" is a stronger, more honest
            # statement than "no face" with nothing to show for the download.
            if candidate.image_sha256 is None:
                candidate.image_sha256 = retrieved.sha256
                candidate.image_bytes = retrieved.byte_size
                candidate.image_mime = retrieved.mime
                candidate.fetched_url = retrieved.final_url
                candidate.http_status = retrieved.http_status

            try:
                decoded = await asyncio.to_thread(
                    decode_image, retrieved.data, self.settings
                )
            except RayaError as exc:
                attempt.reason = f"undecodable: {exc.message}"
                candidate.attempts.append(attempt.to_dict())
                continue

            attempt.decoded = True
            attempt.width = decoded.width
            attempt.height = decoded.height
            if candidate.image_width is None:
                candidate.image_width = decoded.width
                candidate.image_height = decoded.height

            faces = await asyncio.to_thread(self.detector.detect, decoded.bgr)
            if candidate.face_count is None:
                candidate.face_count = len(faces)
            if not faces:
                attempt.reason = "no face detected"
                candidate.attempts.append(attempt.to_dict())
                continue

            if not any(
                f.quality.size_px >= self.settings.min_face_size_px for f in faces
            ):
                largest = max(f.quality.size_px for f in faces)
                attempt.reason = (
                    f"largest face {largest}px, below the "
                    f"{self.settings.min_face_size_px}px minimum"
                )
                candidate.attempts.append(attempt.to_dict())
                continue

            attempt.ok = True
            candidate.attempts.append(attempt.to_dict())
            return decoded, faces, retrieved

        return None

    def _set_cascade_failure(self, candidate: Candidate) -> None:
        """Choose the status that best describes why the cascade came up empty.

        The most informative outcome wins: a face that was merely too small is
        more specific than nothing decodable, which in turn is more specific
        than nothing retrievable at all.
        """
        reasons = [a.get("reason") or "" for a in candidate.attempts]
        decoded_any = any(a.get("decoded") for a in candidate.attempts)

        if any("below the" in r for r in reasons):
            self._fail(candidate, CandidateStatus.FACE_TOO_SMALL)
        elif any("no face detected" in r for r in reasons):
            self._fail(candidate, CandidateStatus.NO_FACE)
        elif decoded_any:
            self._fail(candidate, CandidateStatus.UNDECODABLE)
        else:
            detail = reasons[0] if reasons else None
            self._fail(candidate, CandidateStatus.UNREACHABLE, detail)

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
