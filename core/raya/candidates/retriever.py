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

import html as html_module
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from ..config import Settings, get_settings
from ..errors import SourceUnreachableError
from ..util.hashing import sha256_bytes

ALLOWED_SCHEMES = {"http", "https"}
IMAGE_MIME_PREFIXES = ("image/",)


@dataclass
class RetrievalAttempt:
    """One attempt to fetch a candidate image, successful or not.

    Recorded for every URL tried so that a candidate is never silently
    discarded: the evidence shows what was requested, what came back and why it
    was not usable.
    """

    url: str
    source: str  # "image_url" | "thumbnail_url" | "page_metadata"
    ok: bool
    final_url: Optional[str] = None
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    byte_size: Optional[int] = None
    sha256: Optional[str] = None
    decoded: bool = False
    width: Optional[int] = None
    height: Optional[int] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "source": self.source,
            "ok": self.ok,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "decoded": self.decoded,
            "width": self.width,
            "height": self.height,
            "reason": self.reason,
        }


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


# How much of a source page to read when looking for image metadata. The tags
# we want live in <head>, so a small ceiling is plenty and bounds the cost of
# fetching an attacker-influenced page.
MAX_HTML_BYTES = 512_000

# Public image declarations, in preference order. og:image and twitter:image
# are what a platform publishes *for* external consumers, which is exactly the
# case here -- this reads a page's own public metadata, not private content.
_META_PATTERNS = (
    r'<meta[^>]+property=["\']og:image(?::secure_url|:url)?["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url|:url)?["\']',
    r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
    r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
)


def extract_image_urls(html: str, base_url: str, limit: int = 6) -> list[str]:
    """Pull publicly declared image URLs out of a source page.

    Reads only metadata a page publishes for external consumers -- Open Graph,
    Twitter cards, `link rel=image_src` and JSON-LD `image` fields. It does not
    log in, does not defeat access controls, and does not scrape page content.

    Relative URLs are resolved against the page. Order is deterministic and
    duplicates are dropped, so the cascade is reproducible.
    """
    found: list[str] = []

    def add(value: str) -> None:
        value = html_module.unescape((value or "").strip())
        if not value or value.startswith("data:"):
            return
        resolved = urljoin(base_url, value)
        if resolved not in found:
            found.append(resolved)

    for pattern in _META_PATTERNS:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            add(match.group(1))

    # JSON-LD: `image` may be a string, an object with `url`, or a list of
    # either. Malformed blocks are skipped rather than failing the candidate.
    for block in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(block.group(1).strip())
        except (ValueError, TypeError):
            continue

        def walk(node) -> None:
            if isinstance(node, dict):
                image = node.get("image") or node.get("thumbnailUrl")
                if isinstance(image, str):
                    add(image)
                elif isinstance(image, dict):
                    if isinstance(image.get("url"), str):
                        add(image["url"])
                elif isinstance(image, list):
                    for item in image:
                        if isinstance(item, str):
                            add(item)
                        elif isinstance(item, dict) and isinstance(item.get("url"), str):
                            add(item["url"])
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)

    return found[:limit]


class CandidateRetriever:
    """Fetches candidate images with size, type and redirect limits enforced."""

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    async def fetch_page_image_urls(self, page_url: str) -> list[str]:
        """Read a public source page and return the image URLs it declares.

        Used only after direct retrieval has failed or produced something
        unusable. Failures are swallowed and return an empty list: a page that
        cannot be read is simply one exhausted option, not a run-ending error.
        """
        try:
            assert_safe_url(page_url, self.settings)
        except SourceUnreachableError:
            return []

        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }
        timeout = httpx.Timeout(self.settings.fetch_timeout_s)

        # Use the injected client when there is one, exactly as `fetch` does:
        # it keeps connection reuse in production and makes this path testable
        # with a mock transport instead of reaching the real internet.
        client = self._client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, max_redirects=5, headers=headers
            )

        try:
            try:
                async with client.stream(
                    "GET", page_url, headers=headers, timeout=timeout, follow_redirects=True
                ) as response:
                    final_url = str(response.url)
                    if final_url != page_url:
                        assert_safe_url(final_url, self.settings)
                    if response.status_code >= 400:
                        return []
                    mime = (response.headers.get("content-type") or "").split(";")[0].strip()
                    if not mime.startswith(("text/html", "application/xhtml")):
                        return []

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_HTML_BYTES:
                            break
                        chunks.append(chunk)
                    body = b"".join(chunks).decode("utf-8", errors="replace")
            except (httpx.HTTPError, SourceUnreachableError):
                return []
        finally:
            if owns_client:
                await client.aclose()

        urls: list[str] = []
        for url in extract_image_urls(body, final_url):
            # Every extracted URL is attacker-influenced and must clear the
            # same guard as any other candidate URL.
            try:
                assert_safe_url(url, self.settings)
            except SourceUnreachableError:
                continue
            urls.append(url)
        return urls

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
