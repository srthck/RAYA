"""Candidate value types.

A candidate carries its whole evaluation history: what the search engine said,
what we independently retrieved, what our own models measured, and why it was
accepted or rejected. Rejections are first-class -- they are shown in the UI and
counted in the evidence record, because a pipeline that only reports successes
gives a reviewer no way to judge it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CandidateStatus(str, Enum):
    DISCOVERED = "discovered"          # returned by the search provider
    NOT_SOCIAL = "not_social"          # filtered: not a known public social host
    NO_IMAGE_URL = "no_image_url"      # provider gave no retrievable image
    UNREACHABLE = "unreachable"        # image could not be independently fetched
    UNDECODABLE = "undecodable"        # fetched bytes were not a usable image
    NO_FACE = "no_face"                # no face found in the candidate image
    FACE_TOO_SMALL = "face_too_small"  # face present but too small to embed
    REJECTED = "rejected"              # compared, similarity below threshold
    VERIFIED = "verified"              # compared, similarity at or above threshold
    ERROR = "error"                    # unexpected failure evaluating this candidate

    @property
    def is_terminal_failure(self) -> bool:
        return self not in (CandidateStatus.DISCOVERED, CandidateStatus.VERIFIED)

    @property
    def was_compared(self) -> bool:
        return self in (CandidateStatus.REJECTED, CandidateStatus.VERIFIED)


# Reviewer-facing explanations. Every rejection shows one of these, so a
# candidate is never dropped without a stated reason.
STATUS_REASONS = {
    CandidateStatus.NOT_SOCIAL: "Not a recognised public social media source.",
    CandidateStatus.NO_IMAGE_URL: "Search result carried no retrievable image URL.",
    CandidateStatus.UNREACHABLE: "Source discovered, but the image could not be independently retrieved.",
    CandidateStatus.UNDECODABLE: "Retrieved file was not a decodable image.",
    CandidateStatus.NO_FACE: "No face detected in the candidate image.",
    CandidateStatus.FACE_TOO_SMALL: "Face in the candidate image is too small to compare reliably.",
    CandidateStatus.REJECTED: "Face similarity below threshold.",
    CandidateStatus.VERIFIED: "Face similarity at or above threshold.",
    CandidateStatus.ERROR: "Candidate evaluation failed.",
}


@dataclass
class CandidateVerdict:
    similarity: Optional[float]
    threshold: float
    metric: str
    passed: bool

    def to_dict(self) -> dict:
        return {
            "similarity": round(self.similarity, 6) if self.similarity is not None else None,
            "threshold": self.threshold,
            "metric": self.metric,
            "passed": self.passed,
        }


@dataclass
class Candidate:
    id: str
    position: int
    title: Optional[str]
    page_url: Optional[str]
    image_url: Optional[str]
    thumbnail_url: Optional[str]
    source_name: Optional[str]

    platform: str = "other"
    platform_label: str = "Other website"
    is_social: bool = False
    is_post_url: bool = False

    status: CandidateStatus = CandidateStatus.DISCOVERED
    reason: Optional[str] = None

    image_sha256: Optional[str] = None
    image_bytes: Optional[int] = None
    image_mime: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    fetched_url: Optional[str] = None       # after redirects
    http_status: Optional[int] = None

    # Every URL tried for this candidate, in order, with what came back. A
    # candidate is never silently discarded: if nothing was retrievable, this
    # shows exactly what was attempted and why each option failed.
    attempts: list[dict] = field(default_factory=list)

    face_count: Optional[int] = None
    face_quality: Optional[dict] = None
    verdict: Optional[CandidateVerdict] = None
    duration_ms: Optional[int] = None

    # Not serialized: a small preview the UI shows next to the input face.
    thumbnail_png: Optional[bytes] = field(default=None, repr=False)

    @property
    def similarity(self) -> Optional[float]:
        return self.verdict.similarity if self.verdict else None

    @property
    def verified(self) -> bool:
        return self.status == CandidateStatus.VERIFIED

    def to_dict(self, include_verdict: bool = True) -> dict:
        payload = {
            "id": self.id,
            "position": self.position,
            "title": self.title,
            "page_url": self.page_url,
            "image_url": self.image_url,
            "thumbnail_url": self.thumbnail_url,
            "source_name": self.source_name,
            "platform": self.platform,
            "platform_label": self.platform_label,
            "is_social": self.is_social,
            "is_post_url": self.is_post_url,
            "status": self.status.value,
            "reason": self.reason,
            "image_sha256": self.image_sha256,
            "image_bytes": self.image_bytes,
            "image_mime": self.image_mime,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "fetched_url": self.fetched_url,
            "http_status": self.http_status,
            "attempts": self.attempts,
            "face_count": self.face_count,
            "face_quality": self.face_quality,
            "duration_ms": self.duration_ms,
            "has_preview": self.thumbnail_png is not None,
        }
        if include_verdict:
            payload["verdict"] = self.verdict.to_dict() if self.verdict else None
        return payload
