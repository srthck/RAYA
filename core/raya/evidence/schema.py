"""The evidence record.

This is the artifact RAYA actually preserves. Everything else in the system
exists to produce it honestly, or to prove afterwards that it has not changed.

Three rules govern what goes in:

1. **Only facts.** Every field is something RAYA measured or received, not
   something it inferred. There is no confidence score, no identity claim and
   no name. The record says "these two images scored 0.83 under SFace cosine
   similarity, against a 0.40 threshold" -- it does not say who anyone is.

2. **No biometrics.** Face embeddings are never written here. The record names
   the model and its dimensionality so the measurement is reproducible, and
   stops there. The record is destined for IPFS, which is public and permanent;
   putting a biometric template in it would be irreversible.

3. **Reproducible bytes.** The record is serialized through
   `util.canonical.canonical_json`, so any party holding the same logical
   record recomputes the identical SHA-256. That is the entire basis of the
   tamper-evidence claim, and it is why `SCHEMA_VERSION` is pinned: a schema
   change would change every hash, so it has to be visible.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from ..candidates.types import Candidate, CandidateStatus
from ..search.base import SearchResponse
from ..util.hashing import sha256_canonical

SCHEMA_VERSION = "1.0"
PIPELINE_VERSION = "1.0.0"


def new_verification_id() -> str:
    """A sortable, human-quotable run identifier."""
    stamp = time.strftime("%Y%m%d", time.gmtime())
    return f"VER-{stamp}-{uuid.uuid4().hex[:12].upper()}"


def build_evidence_record(
    *,
    verification_id: str,
    created_at: float,
    input_meta: dict[str, Any],
    search: Optional[SearchResponse],
    candidates: list[Candidate],
    match: Optional[Candidate],
    detector_info: dict[str, Any],
    encoder_info: dict[str, Any],
    threshold: float,
    input_ipfs_cid: Optional[str] = None,
) -> dict[str, Any]:
    """Assemble the canonical evidence record for one verification run."""

    compared = [c for c in candidates if c.status.was_compared]
    social = [c for c in candidates if c.is_social]

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "verification_id": verification_id,
        "created_at": _iso(created_at),
        "pipeline": {
            "version": PIPELINE_VERSION,
            "name": "RAYA",
            "stages": [
                "input",
                "face_detection",
                "face_encoding",
                "reverse_search",
                "candidate_filtering",
                "independent_verification",
                "evidence",
            ],
        },
        "input": {
            "sha256": input_meta["sha256"],
            "byte_size": input_meta["byte_size"],
            "mime": input_meta["mime"],
            "width": input_meta["width"],
            "height": input_meta["height"],
            "face": input_meta.get("face"),
            "ipfs_cid": input_ipfs_cid,
        },
        "search": _search_block(search, candidates, social),
        "candidates": [_candidate_block(c) for c in candidates],
        "match": _match_block(match),
        "verification": {
            "detector": detector_info,
            "encoder": encoder_info,
            "metric": encoder_info.get("metric", "cosine"),
            "threshold": threshold,
            "compared_count": len(compared),
            "verified_count": sum(1 for c in candidates if c.verified),
            "rejected_count": sum(
                1 for c in candidates if c.status == CandidateStatus.REJECTED
            ),
            "embedding_exported": False,
            "processing": "local",
        },
        "claim": _claim_block(match, threshold),
    }
    return record


def _iso(epoch: float) -> str:
    """UTC, second precision, Z-suffixed -- one unambiguous timestamp format."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _search_block(
    search: Optional[SearchResponse],
    candidates: list[Candidate],
    social: list[Candidate],
) -> dict[str, Any]:
    if search is None:
        return {
            "performed": False,
            "provider": None,
            "result_count": 0,
            "social_candidate_count": 0,
        }
    return {
        "performed": True,
        "provider": search.provider,
        "queried_at": _iso(search.queried_at),
        "query_image_url": search.query_image_url,
        "result_count": len(search.results),
        "raw_result_count": search.raw_result_count,
        "social_candidate_count": len(social),
        "evaluated_count": sum(1 for c in candidates if c.status.was_compared),
        "is_replay": bool(search.provider_metadata.get("is_replay", False)),
    }


def _candidate_block(candidate: Candidate) -> dict[str, Any]:
    """Per-candidate summary.

    Timings are deliberately excluded: they are performance data, not evidence,
    and they would make two records of the same findings differ.
    """
    return {
        "id": candidate.id,
        "platform": candidate.platform,
        "page_url": candidate.page_url,
        "image_url": candidate.image_url,
        "is_social": candidate.is_social,
        "is_post_url": candidate.is_post_url,
        "status": candidate.status.value,
        "reason": candidate.reason,
        "image_sha256": candidate.image_sha256,
        "similarity": (
            round(candidate.verdict.similarity, 6)
            if candidate.verdict and candidate.verdict.similarity is not None
            else None
        ),
    }


def _match_block(match: Optional[Candidate]) -> Optional[dict[str, Any]]:
    if match is None:
        return None
    return {
        "candidate_id": match.id,
        "platform": match.platform,
        "platform_label": match.platform_label,
        "post_url": match.page_url,
        "is_post_url": match.is_post_url,
        "image_url": match.image_url,
        "fetched_url": match.fetched_url,
        "image_sha256": match.image_sha256,
        "image_byte_size": match.image_bytes,
        "image_mime": match.image_mime,
        "image_width": match.image_width,
        "image_height": match.image_height,
        "similarity": round(match.verdict.similarity, 6) if match.verdict else None,
        "face_quality": match.face_quality,
    }


def _claim_block(match: Optional[Candidate], threshold: float) -> dict[str, Any]:
    """What this record does and does not assert.

    Stated inside the evidence itself, so the limitation travels with the
    artifact rather than living only in a README the reader may never open.
    """
    if match is None:
        return {
            "result": "no_verified_match",
            "asserts": "No public social media source was independently verified for this image.",
            "does_not_assert": "Absence of a match is not evidence that no such source exists.",
        }
    return {
        "result": "verified_visual_match",
        "asserts": (
            "The face in the input image and the face in the retrieved source image "
            f"scored at or above the {threshold} cosine-similarity threshold under the "
            "named model, and the source image was independently retrieved and hashed."
        ),
        "does_not_assert": (
            "This is not an identity determination. It does not establish who the "
            "person is, that the source post is authentic, or that the depicted "
            "person authored or consented to it. Face recognition error rates vary "
            "with image quality and demographic factors."
        ),
    }


def hash_record(record: dict[str, Any]) -> str:
    """SHA-256 of the canonical serialization of an evidence record."""
    return sha256_canonical(record)
