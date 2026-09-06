"""SHA-256 helpers.

Every hash RAYA reports is a lowercase hex digest of exactly the bytes named
in the evidence record -- never of a re-encoded or re-compressed derivative.
That is what makes the numbers independently checkable with `sha256sum`.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .canonical import canonical_bytes


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_canonical(obj: Any) -> str:
    """Hash a structured record via its canonical serialization."""
    return sha256_bytes(canonical_bytes(obj))


def hex0x(digest: str) -> str:
    """Format a hex digest as an 0x-prefixed string for on-chain comparison."""
    return digest if digest.startswith("0x") else "0x" + digest
