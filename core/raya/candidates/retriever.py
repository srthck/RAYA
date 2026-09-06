"""Independent retrieval of candidate images.

"Independent" is the operative word. The search provider hands us a URL; we go
and fetch the bytes ourselves, hash exactly what arrived, and run our own
models on it. We never treat the provider's thumbnail or its assertion of a
match as evidence.

Because the URLs we fetch are chosen by a third-party API in response to
user-supplied input, this module is a genuine SSRF surface. Every request is
therefore resolved and checked against private address space before it is
issued, and again on each redirect hop.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx

from ..config import Settings, get_settings
from ..errors import SourceUnreachableError
from ..util.hashing import sha256_bytes

ALLOWED_SCHEMES = {"http", "https"}
IMAGE_MIME_PREFIXES = ("image/",)


@dataclass
class RetrievedImage:
    data: bytes
    sha256: str
    mime: str
    byte_size: int
    final_url: str
    http_status: int
    duration_ms: int


class UnsafeUrlError(SourceUnreachableError):
    code = "unsafe_url"


def _is_public_ip(raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_safe_url(url: str, settings: Settings | None = None) -> None:
    """Reject anything that could make the server fetch its own network.

    Resolution is done here rather than trusting the hostname, because a public
    name can resolve to 127.0.0.1 or a cloud metadata address.
    """
    settings = settings or get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Refusing to fetch a {parsed.scheme or 'schemeless'} URL.", url=url)
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("URL has no host.", url=url)

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise SourceUnreachableError(f"Could not resolve {host}.", url=url)

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise SourceUnreachableError(f"Could not resolve {host}.", url=url)
    for address in addresses:
        if not _is_public_ip(address) and not settings.allow_private_network:
            raise UnsafeUrlError(
                f"{host} resolves to a non-public address ({address}); refusing to fetch.",
                url=url,
            )


class CandidateRetriever:
    """Fetches candidate images with size, type and redirect limits enforced."""

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    async def fetch(self, url: str) -> RetrievedImage:
        assert_safe_url(url, self.settings)
        started = time.perf_counter()

        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5",
        }
        timeout = httpx.Timeout(self.settings.fetch_timeout_s)

        client = self._client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, max_redirects=5, headers=headers
            )
        try:
            response = await self._stream(client, url, headers, timeout)
        except httpx.TimeoutException:
            raise SourceUnreachableError(
                f"Timed out after {self.settings.fetch_timeout_s:.0f}s fetching the source image.",
                url=url,
            )
        except httpx.HTTPError as exc:
            raise SourceUnreachableError(f"Could not fetch the source image: {exc}", url=url)
        finally:
            if owns_client:
                await client.aclose()

        response_data, mime, final_url, status = response
        return RetrievedImage(
            data=response_data,
            sha256=sha256_bytes(response_data),
            mime=mime,
            byte_size=len(response_data),
            final_url=final_url,
            http_status=status,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _stream(
        self, client: httpx.AsyncClient, url: str, headers: dict, timeout: httpx.Timeout
    ) -> tuple[bytes, str, str, int]:
        async with client.stream(
            "GET", url, headers=headers, timeout=timeout, follow_redirects=True
        ) as response:
            final_url = str(response.url)
            # A redirect chain can end somewhere private even when the first
            # hop was public, so the final destination is re-checked.
            if final_url != url:
                assert_safe_url(final_url, self.settings)

            if response.status_code >= 400:
                raise SourceUnreachableError(
                    f"Source returned HTTP {response.status_code}.",
                    url=url,
                    status=response.status_code,
                )

            mime = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if mime and not mime.startswith(IMAGE_MIME_PREFIXES):
                raise SourceUnreachableError(
                    f"Source returned {mime}, not an image.", url=url, mime=mime
                )

            declared = response.headers.get("content-length")
            if declared and declared.isdigit():
                if int(declared) > self.settings.max_candidate_bytes:
                    raise SourceUnreachableError(
                        f"Source image is {int(declared) / 1e6:.1f} MB, over the "
                        f"{self.settings.max_candidate_bytes / 1e6:.0f} MB limit.",
                        url=url,
                    )

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                # Enforced during streaming as well: a server can lie about or
                # omit Content-Length.
                if total > self.settings.max_candidate_bytes:
                    raise SourceUnreachableError(
                        f"Source image exceeded the "
                        f"{self.settings.max_candidate_bytes / 1e6:.0f} MB limit.",
                        url=url,
                    )
                chunks.append(chunk)

            data = b"".join(chunks)
            if not data:
                raise SourceUnreachableError("Source returned an empty response.", url=url)
            return data, mime or "application/octet-stream", final_url, response.status_code
