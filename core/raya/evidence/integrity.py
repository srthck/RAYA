"""Integrity checking and the tamper demonstration.

The blockchain layer is only worth having if something actually reads back from
it and compares. This module is that something.

`check_integrity` performs three independent comparisons:

  local bytes  ->  local hash      (did the record change in memory?)
  local hash   ->  on-chain hash   (does the anchor still match?)
  local hash   ->  IPFS-retrieved  (does the stored copy still match?)

A run is only ever described as "integrity verified" when the checks that
actually ran all passed. If the chain was unreachable, the result says so
rather than quietly downgrading to a weaker claim.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Optional

from ..util.canonical import canonical_bytes
from ..util.hashing import sha256_bytes
from .bundle import EvidenceBundle


@dataclass
class Check:
    name: str
    label: str
    performed: bool
    passed: Optional[bool]
    expected: Optional[str] = None
    actual: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "performed": self.performed,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


@dataclass
class IntegrityReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def performed(self) -> list[Check]:
        return [c for c in self.checks if c.performed]

    @property
    def verified(self) -> bool:
        """True only if at least one check ran and every performed check passed."""
        performed = self.performed
        return bool(performed) and all(c.passed for c in performed)

    @property
    def anchored(self) -> bool:
        return any(c.name == "chain_match" and c.performed and c.passed for c in self.checks)

    def summary(self) -> str:
        if not self.performed:
            return "No integrity checks could be performed."
        if self.verified:
            return (
                "Integrity verified: the local evidence hash matches every "
                "independently retrieved copy."
            )
        failed = [c.label for c in self.performed if not c.passed]
        return "Integrity check failed: " + "; ".join(failed) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "anchored": self.anchored,
            "summary": self.summary(),
            "checks": [c.to_dict() for c in self.checks],
        }


def check_integrity(
    bundle: EvidenceBundle,
    onchain_hash: Optional[str] = None,
    ipfs_bytes: Optional[bytes] = None,
) -> IntegrityReport:
    """Compare the local evidence against every independent copy available."""
    report = IntegrityReport()

    # 1. Self-consistency: do the frozen bytes still hash to the stored digest,
    #    and does re-canonicalizing the record reproduce it?
    recomputed = bundle.recompute()
    report.checks.append(
        Check(
            name="self_consistent",
            label="Local record matches its own hash",
            performed=True,
            passed=(recomputed == bundle.sha256 and bundle.verify_self()),
            expected=bundle.sha256,
            actual=recomputed,
            detail="Re-canonicalized the record and re-hashed the frozen bytes.",
        )
    )

    # 2. The anchor.
    if onchain_hash:
        normalized = _strip0x(onchain_hash)
        report.checks.append(
            Check(
                name="chain_match",
                label="On-chain hash matches local hash",
                performed=True,
                passed=(normalized == bundle.sha256),
                expected=bundle.sha256,
                actual=normalized,
                detail="Read back from the contract after confirmation.",
            )
        )
    else:
        report.checks.append(
            Check(
                name="chain_match",
                label="On-chain hash matches local hash",
                performed=False,
                passed=None,
                detail="Evidence was not anchored, so no on-chain value could be read.",
            )
        )

    # 3. The stored copy.
    if ipfs_bytes is not None:
        retrieved = sha256_bytes(ipfs_bytes)
        report.checks.append(
            Check(
                name="ipfs_match",
                label="IPFS copy matches local hash",
                performed=True,
                passed=(retrieved == bundle.sha256),
                expected=bundle.sha256,
                actual=retrieved,
                detail="Re-downloaded the bundle from IPFS and re-hashed the bytes.",
            )
        )
    else:
        report.checks.append(
            Check(
                name="ipfs_match",
                label="IPFS copy matches local hash",
                performed=False,
                passed=None,
                detail="The bundle was not retrieved from IPFS for this check.",
            )
        )

    return report


# ---- tamper demonstration --------------------------------------------------


@dataclass
class TamperResult:
    field_path: str
    original_value: Any
    tampered_value: Any
    original_hash: str
    tampered_hash: str
    anchored_hash: Optional[str]
    detected: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "original_value": self.original_value,
            "tampered_value": self.tampered_value,
            "original_hash": self.original_hash,
            "tampered_hash": self.tampered_hash,
            "anchored_hash": self.anchored_hash,
            "detected": self.detected,
            "summary": (
                f"Altering `{self.field_path}` changed the evidence hash, so the "
                f"record no longer matches the anchored value."
                if self.detected
                else "Tampering was not detected -- this indicates a bug in the hash chain."
            ),
        }


def simulate_tamper(
    bundle: EvidenceBundle,
    field_path: str = "match.similarity",
    new_value: Any = None,
    anchored_hash: Optional[str] = None,
) -> TamperResult:
    """Alter one field on a copy and show that the hash no longer matches.

    Nothing here mutates the real bundle: the tamper is applied to a deep copy.
    The point is to demonstrate the property that makes anchoring worthwhile --
    a single changed field produces a completely different digest, and the
    anchored value is what catches it.
    """
    tampered = copy.deepcopy(bundle.record)
    original = _get_path(tampered, field_path)

    if new_value is None:
        new_value = _plausible_alteration(original)

    _set_path(tampered, field_path, new_value)
    tampered_hash = sha256_bytes(canonical_bytes(tampered))
    reference = _strip0x(anchored_hash) if anchored_hash else bundle.sha256

    return TamperResult(
        field_path=field_path,
        original_value=original,
        tampered_value=new_value,
        original_hash=bundle.sha256,
        tampered_hash=tampered_hash,
        anchored_hash=reference,
        detected=(tampered_hash != reference),
    )


def _plausible_alteration(value: Any) -> Any:
    """Produce the kind of edit a forger would actually make.

    A convincing tamper nudges a value rather than mangling it -- inflating a
    similarity score, swapping a URL. The whole point is that even a change this
    small is caught.
    """
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return round(min(float(value) + 0.15, 1.0), 6)
    if isinstance(value, str):
        if value.startswith("http"):
            return value.rstrip("/") + "-altered"
        return value + " (altered)"
    return "altered"


def _get_path(obj: dict, path: str) -> Any:
    cursor: Any = obj
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise KeyError(f"evidence record has no field `{path}`")
        cursor = cursor[part]
    return cursor


def _set_path(obj: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cursor: Any = obj
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value


def _strip0x(value: str) -> str:
    return value[2:].lower() if value.startswith("0x") else value.lower()
