"""Value types for the face layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class FaceQuality:
    """Measurable properties of a detected face.

    These are reported, never silently acted on beyond the minimum-size gate.
    Face recognition error rates depend heavily on image quality, so RAYA shows
    the reviewer what it was working with instead of hiding it behind a score.
    """

    size_px: int              # shortest side of the face box
    relative_area: float      # face area / image area
    sharpness: float          # variance of the Laplacian; higher is crisper
    brightness: float         # mean luma, 0-255
    detector_score: float     # YuNet confidence

    def to_dict(self) -> dict:
        return {
            "size_px": self.size_px,
            "relative_area": round(self.relative_area, 6),
            "sharpness": round(self.sharpness, 3),
            "brightness": round(self.brightness, 3),
            "detector_score": round(self.detector_score, 6),
        }


@dataclass
class DetectedFace:
    """One face located by the detector.

    `raw` is YuNet's own 15-value row. SFace's `alignCrop` consumes it directly,
    so we keep it rather than reconstructing landmarks and losing precision.
    """

    index: int
    bbox: tuple[int, int, int, int]        # x, y, w, h
    landmarks: list[tuple[int, int]]       # right eye, left eye, nose, mouth corners
    score: float
    quality: FaceQuality
    raw: np.ndarray = field(repr=False)

    @property
    def area(self) -> int:
        return self.bbox[2] * self.bbox[3]

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "bbox": list(self.bbox),
            "landmarks": [list(p) for p in self.landmarks],
            "score": round(self.score, 6),
            "quality": self.quality.to_dict(),
        }


@dataclass
class FaceEmbedding:
    """An SFace feature vector.

    The vector never leaves the process boundary: it is not written into the
    evidence bundle, not uploaded to IPFS and not anchored on chain. Only its
    dimensionality and the model that produced it are ever published.
    """

    vector: np.ndarray = field(repr=False)
    model: str
    dim: int

    def to_public_dict(self) -> dict:
        """Everything about the embedding that is safe to publish."""
        return {"model": self.model, "dim": self.dim, "exported": False}


@dataclass
class ComparisonResult:
    similarity: float
    threshold: float
    metric: str
    passed: bool
    reference_model: str

    def to_dict(self) -> dict:
        return {
            "similarity": round(self.similarity, 6),
            "threshold": self.threshold,
            "metric": self.metric,
            "passed": self.passed,
            "model": self.reference_model,
        }


@dataclass
class SelectedFace:
    """A detected face paired with its embedding and a display thumbnail."""

    face: DetectedFace
    embedding: FaceEmbedding
    thumbnail_png: Optional[bytes] = field(default=None, repr=False)
