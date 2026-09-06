"""The result of one verification run.

A run carries its full history, including the parts that failed. There is a
single status field with a small, explicit vocabulary, because the difference
between "we verified a match and anchored it" and "we verified a match but the
anchor failed" is exactly the difference a reviewer needs to see, and it is the
difference most demos blur.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..candidates.types import Candidate, CandidateStatus
from ..chain.anchor import AnchorReceipt, OnChainRecord
from ..evidence.bundle import EvidenceBundle
from ..evidence.integrity import IntegrityReport
from ..search.base import SearchResponse
from ..storage.ipfs import StoredEvidence


class RunStatus(str, Enum):
    # Terminal successes
    VERIFIED_AND_ANCHORED = "verified_and_anchored"
    VERIFIED_NOT_ANCHORED = "verified_not_anchored"

    # Terminal non-matches -- not failures of the system
    NO_VERIFIED_MATCH = "no_verified_match"
    NO_SOCIAL_CANDIDATES = "no_social_candidates"
    NO_SEARCH_RESULTS = "no_search_results"

    # Stops before verification could happen
    NO_FACE_DETECTED = "no_face_detected"
    MULTIPLE_FACES = "multiple_faces"
    FACE_UNUSABLE = "face_unusable"
    SEARCH_UNAVAILABLE = "search_unavailable"
    INVALID_INPUT = "invalid_input"
    FAILED = "failed"

    @property
    def is_match(self) -> bool:
        return self in (
            RunStatus.VERIFIED_AND_ANCHORED,
            RunStatus.VERIFIED_NOT_ANCHORED,
        )


# One sentence per status, shown verbatim in the UI. Written so that no state
# reads as a success unless it is one.
STATUS_HEADLINES = {
    RunStatus.VERIFIED_AND_ANCHORED: "Verified visual match, evidence anchored",
    RunStatus.VERIFIED_NOT_ANCHORED: "Verified visual match, evidence not anchored",
    RunStatus.NO_VERIFIED_MATCH: "No verified public social source found",
    RunStatus.NO_SOCIAL_CANDIDATES: "No public social sources among the search results",
    RunStatus.NO_SEARCH_RESULTS: "Reverse image search returned no results",
    RunStatus.NO_FACE_DETECTED: "No usable face detected",
    RunStatus.MULTIPLE_FACES: "Multiple faces detected - select a subject",
    RunStatus.FACE_UNUSABLE: "Face detected but not usable for comparison",
    RunStatus.SEARCH_UNAVAILABLE: "Reverse image search is unavailable",
    RunStatus.INVALID_INPUT: "Image could not be read",
    RunStatus.FAILED: "Verification failed",
}


@dataclass
class StageError:
    stage: str
    code: str
    message: str
    fatal: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
            "fatal": self.fatal,
        }


@dataclass
class VerificationResult:
    verification_id: str
    created_at: float = field(default_factory=time.time)
    status: RunStatus = RunStatus.FAILED

    input: dict[str, Any] = field(default_factory=dict)
    faces: list[dict[str, Any]] = field(default_factory=list)
    selected_face_index: Optional[int] = None

    # The bounded derivative actually sent to the provider. Distinct object,
    # distinct hash: never confuse it with the canonical input.
    search_copy: Optional[Any] = None
    search: Optional[SearchResponse] = None
    candidates: list[Candidate] = field(default_factory=list)
    match: Optional[Candidate] = None

    evidence: Optional[EvidenceBundle] = None
    storage: Optional[StoredEvidence] = None
    anchor: Optional[AnchorReceipt] = None
    onchain: Optional[OnChainRecord] = None
    integrity: Optional[IntegrityReport] = None

    errors: list[StageError] = field(default_factory=list)
    duration_ms: Optional[int] = None

    # Preview images, served separately rather than embedded in JSON.
    input_face_png: Optional[bytes] = field(default=None, repr=False)

    # ---- derived views -----------------------------------------------------

    @property
    def headline(self) -> str:
        return STATUS_HEADLINES.get(self.status, "Verification complete")

    @property
    def social_candidates(self) -> list[Candidate]:
        return [c for c in self.candidates if c.is_social]

    @property
    def compared_candidates(self) -> list[Candidate]:
        return [c for c in self.candidates if c.status.was_compared]

    @property
    def rejected_candidates(self) -> list[Candidate]:
        return [c for c in self.candidates if c.status == CandidateStatus.REJECTED]

    @property
    def similarity(self) -> Optional[float]:
        return self.match.similarity if self.match else None

    def add_error(self, stage: str, code: str, message: str, fatal: bool = False) -> None:
        self.errors.append(StageError(stage=stage, code=code, message=message, fatal=fatal))

    def to_dict(self, include_candidates: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "verification_id": self.verification_id,
            "created_at": self.created_at,
            "status": self.status.value,
            "headline": self.headline,
            "is_match": self.status.is_match,
            "input": self.input,
            "faces": self.faces,
            "selected_face_index": self.selected_face_index,
            "search": self.search.to_dict() if self.search else None,
            "search_copy": self.search_copy.to_dict() if self.search_copy else None,
            "counts": {
                "results": len(self.candidates),
                "social": len(self.social_candidates),
                "compared": len(self.compared_candidates),
                "verified": sum(1 for c in self.candidates if c.verified),
                "rejected": len(self.rejected_candidates),
            },
            "match": self.match.to_dict() if self.match else None,
            "similarity": self.similarity,
            "evidence": (
                {
                    "sha256": self.evidence.sha256,
                    "byte_size": self.evidence.byte_size,
                    "schema_version": self.evidence.record.get("schema_version"),
                }
                if self.evidence
                else None
            ),
            "storage": self.storage.to_dict() if self.storage else None,
            "anchor": self.anchor.to_dict() if self.anchor else None,
            "onchain": self.onchain.to_dict() if self.onchain else None,
            "integrity": self.integrity.to_dict() if self.integrity else None,
            "errors": [e.to_dict() for e in self.errors],
            "duration_ms": self.duration_ms,
        }
        if include_candidates:
            payload["candidates"] = [c.to_dict() for c in self.candidates]
        return payload
