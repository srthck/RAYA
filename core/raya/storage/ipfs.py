"""Evidence storage on IPFS.

IPFS gives the evidence bundle a content address: the CID is derived from the
bytes, so it cannot point at different content later. That complements the
on-chain anchor rather than duplicating it -- the chain proves *when* a hash was
committed, IPFS makes the bytes behind that hash retrievable.

Three backends, one interface:

  * `PinataStore` -- a pinning service, so the bundle survives without us
    running infrastructure. This is the default for a real run.
  * `KuboStore`   -- a local `ipfs daemon`, for self-hosted or offline work.
  * `LocalStore`  -- a content-addressed directory on disk. It computes a real
    CIDv1 but does not publish anything, and says so. It exists so the pipeline
    still produces a complete, hash-linked bundle when no IPFS is available;
    the result is explicitly labelled `published: false`.
"""

from __future__ import annotations

import base64
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from ..config import Settings, get_settings
from ..errors import StorageError


@dataclass
class StoredEvidence:
    cid: str
    provider: str
    size: int
    published: bool
    gateway_url: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "cid": self.cid,
            "provider": self.provider,
            "size": self.size,
            "published": self.published,
            "gateway_url": self.gateway_url,
            "detail": self.detail,
        }


class EvidenceStore(ABC):
    name: str

    @abstractmethod
    async def put(self, data: bytes, filename: str) -> StoredEvidence:
        """Store bytes and return their content identifier."""

    @abstractmethod
    async def get(self, cid: str) -> bytes:
        """Retrieve bytes by CID -- used by the integrity check."""

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    def describe(self) -> dict:
        return {"provider": self.name, "configured": self.configured}


# ---- CIDv1 -----------------------------------------------------------------


def cidv1_raw(data: bytes) -> str:
    """Compute the CIDv1 of `data` as a single raw block.

    Layout: multibase 'b' (base32, lowercase, unpadded) over
    <version 0x01><codec 0x55 raw><multihash 0x12 0x20 sha256-digest>.

    This is computed locally so a CID can be reported (and checked) without
    trusting whatever a pinning service returns. It matches `ipfs add` only for
    inputs stored as a single raw leaf; UnixFS chunking of larger files
    produces a different, DAG-based CID. Evidence bundles are a few kilobytes,
    comfortably inside one block.
    """
    digest = hashlib.sha256(data).digest()
    raw = bytes([0x01, 0x55, 0x12, 0x20]) + digest
    return "b" + base64.b32encode(raw).decode("ascii").rstrip("=").lower()


# ---- Pinata ----------------------------------------------------------------


class PinataStore(EvidenceStore):
    name = "pinata"
    API = "https://api.pinata.cloud/pinning/pinFileToIPFS"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.pinata_jwt)

    async def put(self, data: bytes, filename: str = "evidence.json") -> StoredEvidence:
        if not self.configured:
            raise StorageError("PINATA_JWT is not set.")
        headers = {"Authorization": f"Bearer {self.settings.pinata_jwt}"}
        files = {"file": (filename, data, "application/json")}
        metadata = json.dumps({"name": filename, "keyvalues": {"tool": "RAYA"}})

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.API,
                    headers=headers,
                    files=files,
                    data={"pinataMetadata": metadata},
                )
        except httpx.HTTPError as exc:
            raise StorageError(f"Could not reach Pinata: {exc}")

        if response.status_code >= 400:
            raise StorageError(
                f"Pinata returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        cid = payload.get("IpfsHash")
        if not cid:
            raise StorageError("Pinata response contained no CID.")
        return StoredEvidence(
            cid=cid,
            provider=self.name,
            size=len(data),
            published=True,
            gateway_url=f"{self.settings.pinata_gateway.rstrip('/')}/ipfs/{cid}",
        )

    async def get(self, cid: str) -> bytes:
        return await _gateway_get(cid, self.settings)


# ---- Kubo (local node) -----------------------------------------------------


class KuboStore(EvidenceStore):
    name = "kubo"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.kubo_api_url)

    async def put(self, data: bytes, filename: str = "evidence.json") -> StoredEvidence:
        url = f"{self.settings.kubo_api_url.rstrip('/')}/api/v0/add"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    files={"file": (filename, data, "application/json")},
                    params={"cid-version": "1", "raw-leaves": "true", "pin": "true"},
                )
        except httpx.HTTPError as exc:
            raise StorageError(f"Could not reach the local IPFS node: {exc}")

        if response.status_code >= 400:
            raise StorageError(f"IPFS node returned HTTP {response.status_code}.")
        # `add` streams newline-delimited JSON; the final line is the root.
        last = [line for line in response.text.strip().splitlines() if line.strip()][-1]
        cid = json.loads(last).get("Hash")
        if not cid:
            raise StorageError("IPFS node response contained no CID.")
        return StoredEvidence(
            cid=cid,
            provider=self.name,
            size=len(data),
            published=True,
            gateway_url=f"{self.settings.ipfs_public_gateway.rstrip('/')}/ipfs/{cid}",
            detail="Pinned to a local IPFS node.",
        )

    async def get(self, cid: str) -> bytes:
        url = f"{self.settings.kubo_api_url.rstrip('/')}/api/v0/cat"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params={"arg": cid})
                if response.status_code >= 400:
                    raise StorageError(f"IPFS cat returned HTTP {response.status_code}.")
                return response.content
        except httpx.HTTPError:
            return await _gateway_get(cid, self.settings)


# ---- Local fallback --------------------------------------------------------


class LocalStore(EvidenceStore):
    """Content-addressed local storage.

    Honest about what it is: the CID is genuine and the bytes are retrievable
    on this machine, but nothing has been published to the IPFS network.
    `published` is False and the UI renders that as an explicit downgrade
    rather than showing a CID that no one else can resolve.
    """

    name = "local"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.root = self.settings.data_dir / "ipfs"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def configured(self) -> bool:
        return True

    async def put(self, data: bytes, filename: str = "evidence.json") -> StoredEvidence:
        cid = cidv1_raw(data)
        (self.root / cid).write_bytes(data)
        return StoredEvidence(
            cid=cid,
            provider=self.name,
            size=len(data),
            published=False,
            gateway_url=None,
            detail=(
                "Stored locally with a computed CIDv1. No IPFS pinning service was "
                "configured, so this bundle is not retrievable from the public network."
            ),
        )

    async def get(self, cid: str) -> bytes:
        path = self.root / cid
        if not path.exists():
            raise StorageError(f"No locally stored bundle for CID {cid}.")
        return path.read_bytes()


async def _gateway_get(cid: str, settings: Settings) -> bytes:
    """Fetch a CID through a public gateway, for the IPFS integrity check."""
    gateways = [settings.pinata_gateway, settings.ipfs_public_gateway]
    errors = []
    for gateway in gateways:
        if not gateway:
            continue
        url = f"{gateway.rstrip('/')}/ipfs/{cid}"
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
            if response.status_code < 400:
                return response.content
            errors.append(f"{gateway}: HTTP {response.status_code}")
        except httpx.HTTPError as exc:
            errors.append(f"{gateway}: {exc}")
    raise StorageError(f"Could not retrieve {cid} from any gateway ({'; '.join(errors)}).")


def build_store(settings: Settings | None = None) -> EvidenceStore:
    """Pick a backend.

    `auto` prefers a real pinning service, falls back to a local node, and only
    then to on-disk storage -- always choosing the most publishable option that
    is actually configured.
    """
    settings = settings or get_settings()
    provider = (settings.ipfs_provider or "auto").lower()

    if provider == "pinata":
        return PinataStore(settings)
    if provider == "kubo":
        return KuboStore(settings)
    if provider == "local":
        return LocalStore(settings)

    if settings.pinata_jwt:
        return PinataStore(settings)
    if _kubo_reachable(settings):
        return KuboStore(settings)
    return LocalStore(settings)


def _kubo_reachable(settings: Settings) -> bool:
    try:
        response = httpx.post(
            f"{settings.kubo_api_url.rstrip('/')}/api/v0/version", timeout=1.5
        )
        return response.status_code < 400
    except Exception:  # noqa: BLE001 - absence of a node is the normal case
        return False
