"""The bounded search derivative.

Reverse image search needs the picture to reach the provider. The original
input must not: it is the canonical evidence, its bytes are what `input.sha256`
commits to, and re-encoding it would break that commitment.

So RAYA derives a *separate* object -- a bounded, deterministically encoded copy
-- and sends only that. Two distinct artifacts, two distinct hashes, both
recorded:

    original input   ->  input.sha256        canonical, never re-encoded
    search copy      ->  search_copy.sha256  derivative, leaves the machine

This is also the honest privacy boundary. The face *embedding* never leaves the
machine, but the search copy does. RAYA says so plainly rather than claiming
reverse search is private.

Determinism matters for provenance: the same input and settings must always
produce byte-identical output, so the recorded `search_copy.sha256` is
reproducible by anyone holding the original.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from ..errors import InvalidImageError
from ..util.hashing import sha256_bytes

# SerpApi's upload endpoint rejects anything over 500 KB. We aim below it so a
# provider-side off-by-something never costs a run.
DEFAULT_MAX_BYTES = 480_000

# Long-edge ladder, then quality ladder. Tried in order, first fit wins. Fixed
# ladders (rather than a solver) are what make the output deterministic.
EDGE_LADDER = (1600, 1280, 1024, 800, 640, 512)
QUALITY_LADDER = (92, 85, 78, 70, 62, 55, 45)


@dataclass
class SearchCopy:
    """A derivative image prepared for the search provider."""

    data: bytes
    sha256: str
    mime: str
    width: int
    height: int
    byte_size: int
    max_edge: int
    quality: int
    resized: bool

    def to_dict(self) -> dict:
        return {
            "sha256": self.sha256,
            "mime": self.mime,
            "width": self.width,
            "height": self.height,
            "byte_size": self.byte_size,
            "max_edge": self.max_edge,
            "jpeg_quality": self.quality,
            "resized": self.resized,
            "note": (
                "Bounded derivative of the input, sent to the search provider. "
                "The original input bytes are never re-encoded and are hashed "
                "separately as input.sha256."
            ),
        }


def build_search_copy(
    bgr: np.ndarray, max_bytes: int = DEFAULT_MAX_BYTES
) -> SearchCopy:
    """Encode `bgr` as the smallest acceptable JPEG within `max_bytes`.

    Walks the edge ladder outermost and the quality ladder innermost, so the
    result keeps as much resolution as the budget allows before it starts
    sacrificing quality. Returns the first combination that fits.
    """
    if bgr is None or bgr.size == 0:
        raise InvalidImageError("Cannot build a search copy from an empty image.")

    source_h, source_w = bgr.shape[:2]
    source_edge = max(source_h, source_w)

    for edge in EDGE_LADDER:
        # Never upscale: a larger ladder rung than the source would add bytes
        # without adding information.
        target_edge = min(edge, source_edge)
        resized = target_edge < source_edge
        image = _resize_to_edge(bgr, target_edge) if resized else bgr

        for quality in QUALITY_LADDER:
            data = _encode_jpeg(image, quality)
            if len(data) <= max_bytes:
                height, width = image.shape[:2]
                return SearchCopy(
                    data=data,
                    sha256=sha256_bytes(data),
                    mime="image/jpeg",
                    width=width,
                    height=height,
                    byte_size=len(data),
                    max_edge=target_edge,
                    quality=quality,
                    resized=resized,
                )

        # If the source was already smaller than this rung, later (smaller)
        # rungs are the only way to shrink further -- keep walking.

    # Last resort: the smallest rung at the lowest quality. If even that
    # overflows, the caller must be told rather than handed an oversized file
    # the provider will reject.
    smallest = _resize_to_edge(bgr, EDGE_LADDER[-1])
    data = _encode_jpeg(smallest, QUALITY_LADDER[-1])
    if len(data) > max_bytes:
        raise InvalidImageError(
            f"Could not encode a search copy under {max_bytes / 1000:.0f} KB "
            f"(smallest attempt was {len(data) / 1000:.0f} KB)."
        )
    height, width = smallest.shape[:2]
    return SearchCopy(
        data=data,
        sha256=sha256_bytes(data),
        mime="image/jpeg",
        width=width,
        height=height,
        byte_size=len(data),
        max_edge=EDGE_LADDER[-1],
        quality=QUALITY_LADDER[-1],
        resized=True,
    )


def _resize_to_edge(bgr: np.ndarray, target_edge: int) -> np.ndarray:
    height, width = bgr.shape[:2]
    longest = max(height, width)
    if longest <= target_edge:
        return bgr
    scale = target_edge / longest
    return cv2.resize(
        bgr,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def _encode_jpeg(bgr: np.ndarray, quality: int) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise InvalidImageError("Failed to encode the search copy.")
    return buf.tobytes()
