"""SFace face recognition (OpenCV Zoo, 2021-12 release).

SFace maps an aligned face crop to a 128-dimensional embedding. Two embeddings
are compared with cosine similarity. This is the component that makes RAYA's
central claim possible: the search engine proposes a candidate, and *this*
model -- ours, running locally, on both images -- decides whether to accept it.

On the threshold: OpenCV publishes 0.363 as SFace's cosine operating point.
RAYA defaults to 0.40. Candidate images pulled off the public web have been
resized and recompressed at least once, which shifts scores downward and widens
their spread, so the extra margin buys back some of the false-match headroom
that the published figure assumes on clean inputs.
"""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

from ..config import Settings, get_settings
from ..errors import FaceTooSmallError
from .base import FaceEncoder
from .detector import ModelMissingError
from .types import ComparisonResult, DetectedFace, FaceEmbedding

# OpenCV's SFace pipeline expects a 112x112 aligned crop.
ALIGNED_SIZE = 112


class SFaceEncoder(FaceEncoder):
    name = "SFace"
    version = "2021dec"
    dim = 128
    metric = "cosine"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        path = self.settings.sface_path
        if not Path(path).exists():
            raise ModelMissingError(
                f"SFace model not found at {path}. Run `python scripts/fetch_models.py`.",
                path=str(path),
            )
        self._path = str(path)
        self._lock = threading.Lock()
        self._recognizer = cv2.FaceRecognizerSF.create(model=self._path, config="")

    # ---- encoding ----------------------------------------------------------

    def align(self, bgr: np.ndarray, face: DetectedFace) -> np.ndarray:
        """Return the 112x112 similarity-transformed crop SFace expects.

        Alignment uses YuNet's five landmarks, so pose and in-plane rotation are
        normalized before embedding. Skipping this step is the single most
        common cause of spuriously low similarity between two photos of the
        same person.
        """
        with self._lock:
            return self._recognizer.alignCrop(bgr, face.raw)

    def encode(self, bgr: np.ndarray, face: DetectedFace) -> FaceEmbedding:
        if face.quality.size_px < self.settings.min_face_size_px:
            raise FaceTooSmallError(
                f"Face is {face.quality.size_px} px across; at least "
                f"{self.settings.min_face_size_px} px is needed for a reliable "
                f"comparison.",
                size_px=face.quality.size_px,
                required=self.settings.min_face_size_px,
            )
        aligned = self.align(bgr, face)
        with self._lock:
            feature = self._recognizer.feature(aligned)
        vector = np.asarray(feature, dtype=np.float32).reshape(-1)
        return FaceEmbedding(vector=vector, model=f"{self.name}-{self.version}", dim=int(vector.size))

    # ---- comparison --------------------------------------------------------

    def similarity(self, a: FaceEmbedding, b: FaceEmbedding) -> float:
        """Cosine similarity in [-1, 1]; higher means more alike."""
        if a.dim != b.dim:
            raise ValueError(f"embedding dimension mismatch: {a.dim} vs {b.dim}")
        left = a.vector.reshape(1, -1)
        right = b.vector.reshape(1, -1)
        with self._lock:
            score = self._recognizer.match(left, right, cv2.FaceRecognizerSF_FR_COSINE)
        return float(score)

    def compare(
        self, a: FaceEmbedding, b: FaceEmbedding, threshold: float | None = None
    ) -> ComparisonResult:
        threshold = self.settings.similarity_threshold if threshold is None else threshold
        score = self.similarity(a, b)
        return ComparisonResult(
            similarity=score,
            threshold=threshold,
            metric=self.metric,
            passed=score >= threshold,
            reference_model=f"{self.name}-{self.version}",
        )
