"""The evidence bundle: a record plus the bytes that were actually hashed.

Keeping the bytes alongside the record matters. If we re-serialized the record
each time we needed its hash, a later change to the serializer would silently
change the answer. The bundle freezes one canonical byte string at creation and
everything downstream -- the IPFS upload, the on-chain anchor, the exported
files -- refers to that same string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..util.canonical import canonical_bytes, canonical_json
from ..util.hashing import sha256_bytes


@dataclass(frozen=True)
class EvidenceBundle:
    record: dict[str, Any]
    canonical: bytes
    sha256: str

    @classmethod
    def create(cls, record: dict[str, Any]) -> "EvidenceBundle":
        canonical = canonical_bytes(record)
        return cls(record=record, canonical=canonical, sha256=sha256_bytes(canonical))

    @property
    def text(self) -> str:
        return self.canonical.decode("utf-8")

    @property
    def byte_size(self) -> int:
        return len(self.canonical)

    def pretty(self) -> str:
        """Indented JSON for humans.

        Explicitly *not* what gets hashed -- the canonical form is. Exports ship
        both so a reader can inspect the record comfortably and still verify the
        digest against the canonical bytes.
        """
        import json

        return json.dumps(self.record, indent=2, sort_keys=True, ensure_ascii=False)

    def verify_self(self) -> bool:
        """Confirm the frozen bytes still hash to the recorded digest."""
        return sha256_bytes(self.canonical) == self.sha256

    def recompute(self) -> str:
        """Re-derive the hash from the record via canonicalization.

        Used by the integrity check to prove the record and its bytes agree.
        A mismatch means the record was mutated in memory after creation.
        """
        return sha256_bytes(canonical_bytes(self.record))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "canonical_json": canonical_json(self.record),
        }
