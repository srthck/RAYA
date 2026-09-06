"""Persistence for completed runs.

Two features depend on runs outliving the request that created them:
`/evidence/{id}` and `/replay/{id}`. Because the event log is written to disk
alongside the result, a replay re-emits the events the backend actually
produced -- with their real relative timings -- rather than animating a script.

Deliberately a directory of JSON files, not a database. The evidence artifacts
are the product here; keeping them as plain, inspectable files on disk means a
reviewer can read, diff and `sha256sum` them without RAYA running at all. A
database would add a dependency and hide the very thing we want to expose.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..config import Settings, get_settings
from ..events import Event
from .result import VerificationResult


@dataclass
class StoredRun:
    verification_id: str
    result: dict[str, Any]
    events: list[dict[str, Any]]
    evidence_record: Optional[dict[str, Any]]
    evidence_canonical: Optional[str]

    @property
    def status(self) -> str:
        return self.result.get("status", "unknown")


class RunStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.root = self.settings.data_dir / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, verification_id: str) -> Path:
        # Verification ids are generated internally, but this is a filesystem
        # path built from a value that also arrives in URLs, so reject anything
        # that could escape the runs directory.
        if not _safe_id(verification_id):
            raise ValueError(f"unsafe verification id: {verification_id!r}")
        return self.root / verification_id

    # ---- writing -----------------------------------------------------------

    def save(self, result: VerificationResult, events: list[Event]) -> Path:
        target = self._dir(result.verification_id)
        target.mkdir(parents=True, exist_ok=True)

        (target / "result.json").write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (target / "events.json").write_text(
            json.dumps([e.to_dict() for e in events], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if result.evidence is not None:
            # The canonical bytes are written verbatim: this is the file whose
            # sha256sum must equal the anchored hash, so it must not be
            # reformatted on the way to disk.
            (target / "evidence.json").write_bytes(result.evidence.canonical)
            (target / "evidence.pretty.json").write_text(
                result.evidence.pretty(), encoding="utf-8"
            )
            (target / "evidence.sha256").write_text(
                f"{result.evidence.sha256}  evidence.json\n", encoding="utf-8"
            )

        if result.input_face_png:
            (target / "input-face.jpg").write_bytes(result.input_face_png)
        for candidate in result.candidates:
            if candidate.thumbnail_png:
                (target / f"candidate-{candidate.id}.jpg").write_bytes(
                    candidate.thumbnail_png
                )

        (target / "index.json").write_text(
            json.dumps(
                {
                    "verification_id": result.verification_id,
                    "status": result.status.value,
                    "headline": result.headline,
                    "created_at": result.created_at,
                    "saved_at": time.time(),
                    "similarity": result.similarity,
                    "evidence_sha256": result.evidence.sha256 if result.evidence else None,
                    "cid": result.storage.cid if result.storage else None,
                    "tx_hash": result.anchor.tx_hash if result.anchor else None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return target

    # ---- reading -----------------------------------------------------------

    def exists(self, verification_id: str) -> bool:
        try:
            return (self._dir(verification_id) / "result.json").exists()
        except ValueError:
            return False

    def load(self, verification_id: str) -> Optional[StoredRun]:
        # An unsafe id is "not found", matching `exists`, so callers never have
        # to distinguish a rejected path from an absent run.
        try:
            target = self._dir(verification_id)
        except ValueError:
            return None
        result_path = target / "result.json"
        if not result_path.exists():
            return None

        events_path = target / "events.json"
        evidence_path = target / "evidence.json"

        return StoredRun(
            verification_id=verification_id,
            result=json.loads(result_path.read_text(encoding="utf-8")),
            events=(
                json.loads(events_path.read_text(encoding="utf-8"))
                if events_path.exists()
                else []
            ),
            evidence_record=(
                json.loads(evidence_path.read_text(encoding="utf-8"))
                if evidence_path.exists()
                else None
            ),
            evidence_canonical=(
                evidence_path.read_text(encoding="utf-8")
                if evidence_path.exists()
                else None
            ),
        )

    def asset(self, verification_id: str, filename: str) -> Optional[bytes]:
        """Read one saved image, refusing any path that leaves the run dir."""
        if "/" in filename or "\\" in filename or ".." in filename:
            return None
        try:
            path = self._dir(verification_id) / filename
        except ValueError:
            return None
        return path.read_bytes() if path.exists() else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for child in self.root.iterdir():
            index = child / "index.json"
            if index.exists():
                try:
                    entries.append(json.loads(index.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    continue
        entries.sort(key=lambda e: e.get("created_at", 0), reverse=True)
        return entries[:limit]

    def delete(self, verification_id: str) -> bool:
        target = self._dir(verification_id)
        if not target.exists():
            return False
        shutil.rmtree(target)
        return True


def _safe_id(value: str) -> bool:
    return bool(value) and all(c.isalnum() or c in "-_" for c in value) and ".." not in value
