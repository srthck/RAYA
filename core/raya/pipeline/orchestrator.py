"""The RAYA pipeline.

Eleven stages, run in order, each one emitting events as it goes:

    input -> face detection -> face encoding -> reverse search ->
    candidate filtering -> independent verification -> evidence ->
    IPFS -> anchor -> read-back -> integrity

Two principles are enforced here rather than left to the individual stages.

**Failures degrade, they do not fabricate.** Each stage that can fail without
invalidating what came before does so explicitly: the run keeps its verified
match and records that the anchor failed. Nothing downstream is invented to
fill the gap.

**Nothing is claimed that was not measured.** The status is derived from what
actually happened. "Integrity verified" is set only after a value read back off
the chain equalled the locally computed hash.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from ..candidates.retriever import CandidateRetriever
from ..candidates.types import Candidate, CandidateStatus
from ..candidates.verifier import CandidateVerifier
from ..chain.anchor import CoreAnchor, build_anchor
from ..config import Settings, get_settings
from ..errors import (
    AnchorError,
    ChainNotConfiguredError,
    MultipleFacesError,
    NoFaceDetectedError,
    RayaError,
    SearchProviderError,
    SearchProviderNotConfiguredError,
    StorageError,
)
from ..events import EventBus, EventType
from ..evidence.bundle import EvidenceBundle
from ..evidence.integrity import check_integrity
from ..evidence.schema import build_evidence_record, new_verification_id
from ..face.detector import YuNetDetector
from ..face.encoder import SFaceEncoder
from ..face.types import DetectedFace, FaceEmbedding
from ..search.base import ReverseSearchProvider
from ..search.registry import build_provider
from ..storage.ipfs import EvidenceStore, build_store
from ..util.hashing import sha256_bytes
from ..util.imaging import decode_image, encode_jpeg
from .result import RunStatus, VerificationResult

INPUT_FACE_PREVIEW_EDGE = 320


class Pipeline:
    """Orchestrates one verification run end to end."""

    def __init__(
        self,
        settings: Settings | None = None,
        detector: YuNetDetector | None = None,
        encoder: SFaceEncoder | None = None,
        provider: ReverseSearchProvider | None = None,
        store: EvidenceStore | None = None,
        anchor: CoreAnchor | None = None,
    ):
        self.settings = settings or get_settings()
        # Models are loaded once and reused: constructing them per request would
        # add hundreds of milliseconds and needless memory churn.
        self.detector = detector or YuNetDetector(self.settings)
        self.encoder = encoder or SFaceEncoder(self.settings)
        self.provider = provider or build_provider(self.settings)
        self.store = store or build_store(self.settings)
        self.anchor = anchor or build_anchor(self.settings)
        self.verifier = CandidateVerifier(
            detector=self.detector,
            encoder=self.encoder,
            retriever=CandidateRetriever(self.settings),
            settings=self.settings,
        )

    # ---- public API --------------------------------------------------------

    async def run(
        self,
        image_bytes: bytes,
        face_index: Optional[int] = None,
        bus: EventBus | None = None,
        verification_id: Optional[str] = None,
    ) -> VerificationResult:
        verification_id = verification_id or new_verification_id()
        bus = bus or EventBus(verification_id)
        started = time.perf_counter()

        result = VerificationResult(verification_id=verification_id)
        bus.emit(
            EventType.PIPELINE_STARTED,
            verification_id=verification_id,
            provider=self.provider.name,
            detector=self.detector.describe(),
            encoder=self.encoder.describe(),
            threshold=self.settings.similarity_threshold,
        )

        try:
            await self._execute(image_bytes, face_index, bus, result)
        except RayaError as exc:
            self._handle_fatal(result, bus, exc)
        except Exception as exc:  # noqa: BLE001 - never leak a raw traceback to the UI
            result.status = RunStatus.FAILED
            result.add_error("pipeline", "internal_error", str(exc), fatal=True)
            bus.emit(EventType.VERIFICATION_FAILED, code="internal_error", message=str(exc))
        finally:
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            if result.status.is_match or result.status not in (RunStatus.FAILED,):
                bus.emit(
                    EventType.VERIFICATION_COMPLETED,
                    status=result.status.value,
                    headline=result.headline,
                    duration_ms=result.duration_ms,
                )
            bus.close()

        return result

    # ---- stages ------------------------------------------------------------

    async def _execute(
        self,
        image_bytes: bytes,
        face_index: Optional[int],
        bus: EventBus,
        result: VerificationResult,
    ) -> None:
        subject, decoded = await self._stage_face(image_bytes, face_index, bus, result)

        search_url = await self._stage_prepare_search(image_bytes, decoded, bus, result)
        if search_url is None:
            return

        if not await self._stage_search(search_url, bus, result):
            return

        await self._stage_verify(subject, bus, result)

        # Evidence is built for every run that got as far as searching, match or
        # not: a documented non-match is a legitimate, citable outcome.
        self._stage_evidence(bus, result)

        if result.match is None:
            result.status = self._no_match_status(result)
            return

        await self._stage_store(bus, result)
        await self._stage_anchor(bus, result)
        await self._stage_integrity(bus, result)

    # -- stages 01-03: input, detection, encoding ---------------------------

    async def _stage_face(
        self,
        image_bytes: bytes,
        face_index: Optional[int],
        bus: EventBus,
        result: VerificationResult,
    ) -> tuple[FaceEmbedding, Any]:
        input_hash = sha256_bytes(image_bytes)
        bus.emit(EventType.INPUT_RECEIVED, byte_size=len(image_bytes))

        decoded = await asyncio.to_thread(decode_image, image_bytes, self.settings)
        result.input = {
            "sha256": input_hash,
            "byte_size": len(image_bytes),
            "mime": decoded.mime,
            "width": decoded.width,
            "height": decoded.height,
            "format": decoded.format,
        }
        bus.emit(EventType.INPUT_HASHED, sha256=input_hash, **decoded.to_dict())

        bus.emit(EventType.FACE_DETECTING)
        faces = await asyncio.to_thread(self.detector.detect, decoded.bgr)
        result.faces = [f.to_dict() for f in faces]
        bus.emit(
            EventType.FACE_DETECTED,
            face_count=len(faces),
            faces=result.faces,
            image={"width": decoded.width, "height": decoded.height},
        )

        if not faces:
            raise NoFaceDetectedError(
                "No face was detected in this image. RAYA verifies faces, so there "
                "is nothing to search for."
            )

        # More than one face is ambiguous, and guessing would silently decide
        # whose identity is being investigated. We stop and ask instead.
        if len(faces) > 1 and face_index is None:
            raise MultipleFacesError(
                f"{len(faces)} faces were detected. Select which one is the subject.",
                faces=result.faces,
            )

        index = 0 if face_index is None else int(face_index)
        if index < 0 or index >= len(faces):
            raise NoFaceDetectedError(
                f"Face index {index} is out of range; {len(faces)} faces were detected."
            )

        face: DetectedFace = faces[index]
        result.selected_face_index = index
        result.input["face"] = face.to_dict()
        result.input_face_png = _face_preview(decoded.bgr, face)
        bus.emit(EventType.FACE_SELECTED, index=index, face=face.to_dict())

        embedding = await asyncio.to_thread(self.encoder.encode, decoded.bgr, face)
        bus.emit(
            EventType.FACE_ENCODED,
            **embedding.to_public_dict(),
            note="The embedding stays on this machine. It is never uploaded or anchored.",
        )
        return embedding, decoded

    # -- stage 04a: make the input searchable -------------------------------

    async def _stage_prepare_search(
        self,
        image_bytes: bytes,
        decoded: Any,
        bus: EventBus,
        result: VerificationResult,
    ) -> Optional[str]:
        """Produce a publicly fetchable URL for the input image.

        Google Lens is given a URL, not an upload, so a local file cannot be
        searched as-is. Publishing the input to IPFS solves this with a
        dependency the pipeline already has. When neither a public base URL nor
        a real pinning service is configured, we stop and say so rather than
        pretend a search happened.
        """
        if not self.provider.requires_public_url:
            return f"local://{result.input['sha256']}"

        if self.settings.public_base_url:
            url = (
                f"{self.settings.public_base_url.rstrip('/')}"
                f"/v1/verifications/{result.verification_id}/input"
            )
            bus.emit(EventType.SEARCH_PREPARING, method="public_base_url", url=url)
            return url

        bus.emit(EventType.SEARCH_PREPARING, method="ipfs")
        try:
            stored = await self.store.put(image_bytes, filename="input-image")
        except StorageError as exc:
            result.status = RunStatus.SEARCH_UNAVAILABLE
            result.add_error("search_prepare", "storage_error", exc.message, fatal=True)
            bus.emit(EventType.STAGE_FAILED, stage="search_prepare", message=exc.message)
            return None

        if not stored.published or not stored.gateway_url:
            message = (
                "The reverse image search needs a publicly reachable image URL, but no "
                "IPFS pinning service or PUBLIC_BASE_URL is configured. Set PINATA_JWT "
                "or PUBLIC_BASE_URL. RAYA will not fabricate search results."
            )
            result.status = RunStatus.SEARCH_UNAVAILABLE
            result.add_error("search_prepare", "no_public_url", message, fatal=True)
            bus.emit(EventType.STAGE_FAILED, stage="search_prepare", message=message)
            return None

        result.input["ipfs_cid"] = stored.cid
        bus.emit(
            EventType.SEARCH_PREPARING,
            method="ipfs",
            cid=stored.cid,
            url=stored.gateway_url,
        )
        return stored.gateway_url

    # -- stages 04-05: search and filtering ---------------------------------

    async def _stage_search(
        self, search_url: str, bus: EventBus, result: VerificationResult
    ) -> bool:
        bus.emit(
            EventType.SEARCH_STARTED,
            provider=self.provider.name,
            display_name=self.provider.display_name,
            query_image_url=search_url,
        )
        try:
            response = await self.provider.search(search_url)
        except SearchProviderNotConfiguredError as exc:
            result.status = RunStatus.SEARCH_UNAVAILABLE
            result.add_error("search", exc.code, exc.message, fatal=True)
            bus.emit(EventType.STAGE_FAILED, stage="search", message=exc.message)
            return False
        except SearchProviderError as exc:
            result.status = RunStatus.SEARCH_UNAVAILABLE
            result.add_error("search", exc.code, exc.message, fatal=True)
            bus.emit(EventType.STAGE_FAILED, stage="search", message=exc.message)
            return False

        result.search = response
        bus.emit(
            EventType.SEARCH_COMPLETED,
            provider=response.provider,
            result_count=len(response.results),
            raw_result_count=response.raw_result_count,
            duration_ms=response.duration_ms,
            is_replay=bool(response.provider_metadata.get("is_replay")),
        )

        if not response.results:
            result.status = RunStatus.NO_SEARCH_RESULTS
            return False

        result.candidates = self.verifier.build_candidates(response.results, bus)
        if not any(c.is_social for c in result.candidates):
            result.status = RunStatus.NO_SOCIAL_CANDIDATES
            return False
        return True

    # -- stage 06: independent verification ---------------------------------

    async def _stage_verify(
        self, subject: FaceEmbedding, bus: EventBus, result: VerificationResult
    ) -> None:
        await self.verifier.verify_all(result.candidates, subject, bus)

        verified = [c for c in result.candidates if c.verified]
        if verified:
            # Rank by similarity, then prefer a URL that identifies a specific
            # post over a bare profile: both are matches, but a post is the
            # stronger citation.
            verified.sort(
                key=lambda c: (c.verdict.similarity, c.is_post_url), reverse=True
            )
            result.match = verified[0]
            bus.emit(
                EventType.MATCH_SELECTED,
                candidate=result.match.to_dict(),
                among=len(verified),
            )

    def _no_match_status(self, result: VerificationResult) -> RunStatus:
        if any(c.status.was_compared for c in result.candidates):
            return RunStatus.NO_VERIFIED_MATCH
        if any(c.is_social for c in result.candidates):
            return RunStatus.NO_VERIFIED_MATCH
        return RunStatus.NO_SOCIAL_CANDIDATES

    # -- stage 07: evidence --------------------------------------------------

    def _stage_evidence(self, bus: EventBus, result: VerificationResult) -> None:
        record = build_evidence_record(
            verification_id=result.verification_id,
            created_at=result.created_at,
            input_meta=result.input,
            search=result.search,
            candidates=result.candidates,
            match=result.match,
            detector_info=self.detector.describe(),
            encoder_info=self.encoder.describe(),
            threshold=self.settings.similarity_threshold,
            input_ipfs_cid=result.input.get("ipfs_cid"),
        )
        bundle = EvidenceBundle.create(record)
        result.evidence = bundle
        bus.emit(
            EventType.EVIDENCE_CREATED,
            schema_version=record["schema_version"],
            byte_size=bundle.byte_size,
        )
        bus.emit(EventType.EVIDENCE_HASHED, sha256=bundle.sha256, algorithm="sha256")

    # -- stage 08: IPFS ------------------------------------------------------

    async def _stage_store(self, bus: EventBus, result: VerificationResult) -> None:
        bus.emit(EventType.IPFS_UPLOADING, provider=self.store.name)
        try:
            stored = await self.store.put(
                result.evidence.canonical, filename=f"{result.verification_id}-evidence.json"
            )
        except StorageError as exc:
            result.add_error("ipfs", exc.code, exc.message, fatal=False)
            bus.emit(EventType.STAGE_FAILED, stage="ipfs", message=exc.message)
            return

        result.storage = stored
        bus.emit(EventType.IPFS_UPLOADED, **stored.to_dict())

    # -- stage 09: anchor ----------------------------------------------------

    async def _stage_anchor(self, bus: EventBus, result: VerificationResult) -> None:
        if not self.anchor.configured:
            message = (
                "No contract address or signing key is configured, so the evidence "
                "was not anchored. The face match above is unaffected."
            )
            result.add_error("anchor", "chain_not_configured", message, fatal=False)
            bus.emit(EventType.STAGE_FAILED, stage="anchor", message=message)
            return

        bus.emit(
            EventType.BLOCKCHAIN_SUBMITTING,
            chain=self.settings.chain_name,
            chain_id=self.settings.chain_id,
            contract=self.settings.contract_address,
        )
        try:
            # web3.py is synchronous, so the whole submit-and-wait runs off the
            # event loop to keep the SSE stream responsive.
            receipt = await asyncio.to_thread(
                self.anchor.anchor,
                result.verification_id,
                result.evidence.sha256,
                result.input["sha256"],
                result.match.image_sha256 or "0" * 64,
                result.storage.cid if result.storage else "",
                result.similarity or 0.0,
            )
        except (AnchorError, ChainNotConfiguredError) as exc:
            result.add_error("anchor", exc.code, exc.message, fatal=False)
            bus.emit(EventType.STAGE_FAILED, stage="anchor", message=exc.message)
            return

        result.anchor = receipt
        bus.emit(EventType.BLOCKCHAIN_SUBMITTED, tx_hash=receipt.tx_hash)
        bus.emit(EventType.BLOCKCHAIN_CONFIRMED, **receipt.to_dict())

    # -- stages 10-11: read back and integrity ------------------------------

    async def _stage_integrity(self, bus: EventBus, result: VerificationResult) -> None:
        bus.emit(EventType.INTEGRITY_CHECKING)

        onchain_hash: Optional[str] = None
        if result.anchor is not None:
            try:
                record = await asyncio.to_thread(
                    self.anchor.read_record, result.verification_id
                )
                result.onchain = record
                onchain_hash = record.evidence_hash
            except AnchorError as exc:
                result.add_error("readback", exc.code, exc.message, fatal=False)
                bus.emit(EventType.STAGE_FAILED, stage="readback", message=exc.message)

        # Re-download the stored bundle so the IPFS copy is checked against the
        # local hash too, not merely assumed correct.
        ipfs_bytes: Optional[bytes] = None
        if result.storage is not None and result.storage.published:
            try:
                ipfs_bytes = await self.store.get(result.storage.cid)
            except StorageError as exc:
                result.add_error("ipfs_readback", exc.code, exc.message, fatal=False)

        report = check_integrity(result.evidence, onchain_hash, ipfs_bytes)
        result.integrity = report

        if report.verified and report.anchored:
            result.status = RunStatus.VERIFIED_AND_ANCHORED
            bus.emit(EventType.INTEGRITY_VERIFIED, **report.to_dict())
        elif report.anchored:
            result.status = RunStatus.VERIFIED_AND_ANCHORED
            bus.emit(EventType.INTEGRITY_FAILED, **report.to_dict())
        else:
            result.status = RunStatus.VERIFIED_NOT_ANCHORED
            bus.emit(EventType.INTEGRITY_FAILED, **report.to_dict())

    # ---- failure handling --------------------------------------------------

    def _handle_fatal(
        self, result: VerificationResult, bus: EventBus, exc: RayaError
    ) -> None:
        mapping = {
            "no_face_detected": RunStatus.NO_FACE_DETECTED,
            "multiple_faces": RunStatus.MULTIPLE_FACES,
            "face_too_small": RunStatus.FACE_UNUSABLE,
            "invalid_image": RunStatus.INVALID_INPUT,
            "image_too_large": RunStatus.INVALID_INPUT,
            "unsupported_format": RunStatus.INVALID_INPUT,
            "search_provider_not_configured": RunStatus.SEARCH_UNAVAILABLE,
            "search_provider_error": RunStatus.SEARCH_UNAVAILABLE,
        }
        result.status = mapping.get(exc.code, RunStatus.FAILED)
        result.add_error("pipeline", exc.code, exc.message, fatal=True)
        bus.emit(
            EventType.VERIFICATION_FAILED,
            code=exc.code,
            message=exc.message,
            status=result.status.value,
            **exc.context,
        )


def _face_preview(bgr, face: DetectedFace) -> Optional[bytes]:
    """Crop the subject face for the side-by-side comparison view."""
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
        scale = INPUT_FACE_PREVIEW_EDGE / max(crop.shape[0], crop.shape[1])
        if scale < 1:
            crop = cv2.resize(
                crop,
                (int(crop.shape[1] * scale), int(crop.shape[0] * scale)),
                interpolation=cv2.INTER_AREA,
            )
        return encode_jpeg(crop, quality=88)
    except Exception:  # noqa: BLE001
        return None
