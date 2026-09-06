"""Process-wide runtime: models, uploads and in-flight runs.

The face models take a moment to load and are safe to share, so they are built
once at startup and reused. `RunManager` owns the in-flight runs and their event
buses; when a run finishes it is persisted by `RunStore` and dropped from memory.

Uploads are separated from verifications on purpose. Detection happens at upload
time, so when an image contains several faces the UI can ask which one is the
subject *before* any search is performed -- rather than guessing, or making the
user upload the file a second time.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from raya.config import Settings, get_settings
from raya.errors import RayaError
from raya.events import EventBus
from raya.evidence.schema import new_verification_id
from raya.face.detector import YuNetDetector
from raya.face.encoder import SFaceEncoder
from raya.pipeline.orchestrator import Pipeline
from raya.pipeline.result import VerificationResult
from raya.pipeline.store import RunStore
from raya.util.hashing import sha256_bytes
from raya.util.imaging import decode_image

# How long a finished run stays in memory before readers fall back to disk.
RUN_TTL_S = 60 * 30
UPLOAD_TTL_S = 60 * 60


@dataclass
class Upload:
    upload_id: str
    data: bytes = field(repr=False)
    sha256: str
    width: int
    height: int
    mime: str
    format: str
    byte_size: int
    faces: list[dict[str, Any]]
    created_at: float = field(default_factory=time.time)

    @property
    def requires_selection(self) -> bool:
        return len(self.faces) > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "mime": self.mime,
            "format": self.format,
            "byte_size": self.byte_size,
            "face_count": len(self.faces),
            "faces": self.faces,
            "requires_selection": self.requires_selection,
        }


@dataclass
class ActiveRun:
    verification_id: str
    bus: EventBus
    task: Optional[asyncio.Task] = None
    result: Optional[VerificationResult] = None
    finished_at: Optional[float] = None


class Runtime:
    """Holds everything that should exist once per process."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.detector = YuNetDetector(self.settings)
        self.encoder = SFaceEncoder(self.settings)
        self.pipeline = Pipeline(
            settings=self.settings, detector=self.detector, encoder=self.encoder
        )
        self.store = RunStore(self.settings)
        self._uploads: dict[str, Upload] = {}
        self._runs: dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    # ---- uploads -----------------------------------------------------------

    async def create_upload(self, data: bytes) -> Upload:
        decoded = await asyncio.to_thread(decode_image, data, self.settings)
        faces = await asyncio.to_thread(self.detector.detect, decoded.bgr)
        upload = Upload(
            upload_id=f"up_{uuid.uuid4().hex[:16]}",
            data=data,
            sha256=sha256_bytes(data),
            width=decoded.width,
            height=decoded.height,
            mime=decoded.mime,
            format=decoded.format,
            byte_size=len(data),
            faces=[f.to_dict() for f in faces],
        )
        self._gc()
        self._uploads[upload.upload_id] = upload
        return upload

    def get_upload(self, upload_id: str) -> Optional[Upload]:
        return self._uploads.get(upload_id)

    # ---- runs --------------------------------------------------------------

    async def start_run(self, upload: Upload, face_index: Optional[int]) -> ActiveRun:
        verification_id = new_verification_id()
        bus = EventBus(verification_id)
        run = ActiveRun(verification_id=verification_id, bus=bus)

        async with self._lock:
            self._runs[verification_id] = run

        async def execute() -> None:
            try:
                result = await self.pipeline.run(
                    upload.data, face_index=face_index, bus=bus, verification_id=verification_id
                )
                run.result = result
                # Persist before marking finished, so a client that reacts to
                # the terminal event never races ahead of the stored artifacts.
                await asyncio.to_thread(self.store.save, result, bus.log)
            except Exception:  # noqa: BLE001 - the pipeline already handles its own
                if not bus.closed:
                    bus.close()
            finally:
                run.finished_at = time.time()

        run.task = asyncio.create_task(execute())
        return run

    def get_run(self, verification_id: str) -> Optional[ActiveRun]:
        return self._runs.get(verification_id)

    def result_dict(self, verification_id: str) -> Optional[dict[str, Any]]:
        """Return a run's result from memory, falling back to disk."""
        run = self._runs.get(verification_id)
        if run and run.result is not None:
            return run.result.to_dict()
        stored = self.store.load(verification_id)
        return stored.result if stored else None

    def asset(self, verification_id: str, filename: str) -> Optional[bytes]:
        return self.store.asset(verification_id, filename)

    # ---- housekeeping ------------------------------------------------------

    def _gc(self) -> None:
        """Drop stale uploads and finished runs.

        Uploaded images are held in memory only as long as they might still be
        verified. Nothing is written to disk until a run produces evidence.
        """
        now = time.time()
        for key, upload in list(self._uploads.items()):
            if now - upload.created_at > UPLOAD_TTL_S:
                del self._uploads[key]
        for key, run in list(self._runs.items()):
            if run.finished_at and now - run.finished_at > RUN_TTL_S:
                del self._runs[key]

    def describe(self) -> dict[str, Any]:
        """Public capability report -- what is configured and what is not.

        The UI renders this honestly: a missing search key or contract address
        is shown as a disabled capability rather than hidden.
        """
        return {
            "detector": self.detector.describe(),
            "encoder": self.encoder.describe(),
            "threshold": self.settings.similarity_threshold,
            "metric": self.settings.similarity_metric,
            "search": self.pipeline.provider.describe(),
            "storage": self.pipeline.store.describe(),
            "chain": self.pipeline.anchor.describe(),
            "limits": {
                "max_upload_bytes": self.settings.max_upload_bytes,
                "max_candidates": self.settings.max_candidates,
                "max_verified_candidates": self.settings.max_verified_candidates,
                "min_face_size_px": self.settings.min_face_size_px,
            },
        }


_runtime: Optional[Runtime] = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


def reset_runtime() -> None:
    global _runtime
    _runtime = None
