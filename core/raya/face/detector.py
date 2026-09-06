"""YuNet face detection (OpenCV Zoo, 2023-03 release).

YuNet is a small, fast CNN detector shipped as an ONNX graph and executed by
OpenCV's own DNN backend. Running it locally is a deliberate choice: no face
image and no derived biometric ever leaves the machine during detection.
"""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

from ..config import Settings, get_settings
from ..util.hashing import sha256_file
from ..errors import RayaError
from .base import FaceDetector
from .types import DetectedFace, FaceQuality

LANDMARK_NAMES = ["right_eye", "left_eye", "nose", "mouth_right", "mouth_left"]

# Longest edge fed to the detector. Large enough to keep small faces findable,
# small enough to stay inside the range where the fixed-shape YuNet graph
# behaves consistently.
DETECT_MAX_EDGE = 1024


class ModelMissingError(RayaError):
    code = "model_missing"
    http_status = 500


class YuNetDetector(FaceDetector):
    name = "YuNet"
    version = "2023mar"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        path = self.settings.yunet_path
        if not Path(path).exists():
            raise ModelMissingError(
                f"YuNet model not found at {path}. Run `python scripts/fetch_models.py`.",
                path=str(path),
            )
        self._path = str(path)
        self._model_digest: str | None = None
        # The OpenCV detector object is stateful (setInputSize mutates it), so
        # calls are serialized. Detection is milliseconds; this is not a
        # throughput bottleneck and it avoids a whole class of race condition.
        self._lock = threading.Lock()
        self._detector = cv2.FaceDetectorYN.create(
            model=self._path,
            config="",
            input_size=(320, 320),
            score_threshold=self.settings.face_score_threshold,
            nms_threshold=self.settings.face_nms_threshold,
            top_k=self.settings.face_top_k,
        )

    def model_sha256(self) -> str | None:
        """SHA-256 of the ONNX file backing this instance.

        Computed once and cached: it identifies the exact weights that produced
        every score in the evidence, and it is what makes a published
        similarity independently reproducible.
        """
        if self._model_digest is None:
            try:
                self._model_digest = sha256_file(self._path)
            except OSError:
                self._model_digest = ""
        return self._model_digest or None

    def detect(self, bgr: np.ndarray) -> list[DetectedFace]:
        """Detect faces, returning coordinates in the original image space.

        Detection runs on a copy bounded to `DETECT_MAX_EDGE`. This is not only
        a speed optimisation: the fixed-input-shape 2023mar graph stops
        returning detections at very large resolutions (a 2687x3356 portrait
        yields nothing at native size, one face at 1024). Bounding the input
        makes recall consistent regardless of how large the source photo is.

        Coordinates are then scaled back, so cropping and alignment still work
        from the full-resolution pixels and lose no detail to the downscale.
        """
        if bgr is None or bgr.size == 0:
            return []
        height, width = bgr.shape[:2]

        scale = min(1.0, DETECT_MAX_EDGE / max(height, width))
        if scale < 1.0:
            detect_input = cv2.resize(
                bgr,
                (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            detect_input = bgr

        detect_height, detect_width = detect_input.shape[:2]
        with self._lock:
            self._detector.setInputSize((detect_width, detect_height))
            _, raw = self._detector.detect(detect_input)

        if raw is None or len(raw) == 0:
            return []

        if scale < 1.0:
            raw = np.asarray(raw, dtype=np.float32).copy()
            # Columns 0-13 are the box and the five landmarks; column 14 is the
            # confidence score and must not be rescaled.
            raw[:, :14] /= scale

        image_area = float(width * height)
        faces: list[DetectedFace] = []
        for row in raw:
            face = self._build_face(row, bgr, image_area, len(faces))
            if face is not None:
                faces.append(face)

        # Largest first: when a photo contains a subject and bystanders, the
        # subject is almost always the biggest face. The caller still decides.
        faces.sort(key=lambda f: f.area, reverse=True)
        for position, face in enumerate(faces):
            face.index = position
        return faces

    def _build_face(
        self, row: np.ndarray, bgr: np.ndarray, image_area: float, index: int
    ) -> DetectedFace | None:
        height, width = bgr.shape[:2]
        x, y, w, h = (int(round(float(v))) for v in row[:4])

        # YuNet can return boxes that run past the image edge; clamp so every
        # downstream crop is in-bounds.
        x, y = max(0, x), max(0, y)
        w = min(w, width - x)
        h = min(h, height - y)
        if w <= 1 or h <= 1:
            return None

        landmarks = [
            (int(round(float(row[4 + i * 2]))), int(round(float(row[5 + i * 2]))))
            for i in range(5)
        ]
        score = float(row[14])
        crop = bgr[y : y + h, x : x + w]

        quality = FaceQuality(
            size_px=int(min(w, h)),
            relative_area=(w * h) / image_area if image_area else 0.0,
            sharpness=_sharpness(crop),
            brightness=_brightness(crop),
            detector_score=score,
        )
        return DetectedFace(
            index=index,
            bbox=(x, y, w, h),
            landmarks=landmarks,
            score=score,
            quality=quality,
            raw=np.asarray(row, dtype=np.float32),
        )


def _sharpness(crop: np.ndarray) -> float:
    """Variance of the Laplacian -- the standard cheap blur estimate."""
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _brightness(crop: np.ndarray) -> float:
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())
