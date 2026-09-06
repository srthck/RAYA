"""Interfaces for the face layer.

The pipeline depends on these, not on OpenCV. Swapping YuNet for another
detector, or SFace for another encoder, is a matter of writing one class --
no orchestration code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .types import ComparisonResult, DetectedFace, FaceEmbedding


class FaceDetector(ABC):
    name: str
    version: str

    @abstractmethod
    def detect(self, bgr: np.ndarray) -> list[DetectedFace]:
        """Return every face found, ordered largest first."""

    def describe(self) -> dict:
        """Identify the model *and* the exact file that produced the scores.

        The evidence names the model; that claim is only reproducible if the
        bytes behind the name are pinned too.
        """
        return {
            "name": self.name,
            "version": self.version,
            "model_sha256": self.model_sha256(),
        }

    def model_sha256(self) -> str | None:
        return None


class FaceEncoder(ABC):
    name: str
    version: str
    dim: int
    metric: str

    @abstractmethod
    def encode(self, bgr: np.ndarray, face: DetectedFace) -> FaceEmbedding:
        """Align, crop and embed a single detected face."""

    @abstractmethod
    def compare(
        self, a: FaceEmbedding, b: FaceEmbedding, threshold: float
    ) -> ComparisonResult:
        """Score two embeddings against a decision threshold."""

    def describe(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "dim": self.dim,
            "metric": self.metric,
            "model_sha256": self.model_sha256(),
        }

    def model_sha256(self) -> str | None:
        return None
