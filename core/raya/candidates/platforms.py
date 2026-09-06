"""Public social-platform classification.

The task is to find a *public social media source*, so a search result that
points at a news article, a stock-photo library or a content farm is not what
we are after. This module is the filter, and it is deliberately conservative:
an unrecognised domain is classified as `OTHER` and does not become a social
candidate.

Two properties are recorded per candidate:

  * which platform the page belongs to, and
  * whether the URL looks like a specific *post* rather than a bare profile or
    the platform's home page.

A post URL is far stronger evidence than a profile URL, because it names the
individual item the image was published in. The distinction is reported rather
than used to silently discard candidates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class Platform:
    key: str
    label: str
    domains: tuple[str, ...]
    # Patterns that indicate the URL identifies one post/photo/video.
    post_patterns: tuple[str, ...] = field(default=())
    is_social: bool = True

    def matches(self, host: str) -> bool:
        return any(host == d or host.endswith("." + d) for d in self.domains)

    def looks_like_post(self, path: str) -> bool:
        return any(re.search(p, path, re.IGNORECASE) for p in self.post_patterns)


PLATFORMS: tuple[Platform, ...] = (
    Platform(
        key="x",
        label="X",
        domains=("x.com", "twitter.com", "t.co", "fxtwitter.com", "vxtwitter.com"),
        post_patterns=(r"/status/\d+", r"/i/web/status/\d+"),
    ),
    Platform(
        key="instagram",
        label="Instagram",
        domains=("instagram.com", "instagr.am", "cdninstagram.com"),
        post_patterns=(r"^/(p|reel|reels|tv)/[\w-]+",),
    ),
    Platform(
        key="facebook",
        label="Facebook",
        domains=("facebook.com", "fb.com", "fb.watch", "m.facebook.com"),
        post_patterns=(r"/posts/", r"/photo", r"/permalink", r"/videos/", r"story_fbid="),
    ),
    Platform(
        key="linkedin",
        label="LinkedIn",
        domains=("linkedin.com", "lnkd.in"),
        post_patterns=(r"/posts/", r"/feed/update/", r"/pulse/"),
    ),
    Platform(
        key="youtube",
        label="YouTube",
        domains=("youtube.com", "youtu.be", "ytimg.com"),
        post_patterns=(r"^/watch", r"^/shorts/", r"^/[\w-]{11}$"),
    ),
    Platform(
        key="tiktok",
        label="TikTok",
        domains=("tiktok.com", "vm.tiktok.com"),
        post_patterns=(r"/video/\d+", r"/photo/\d+"),
    ),
    Platform(
        key="reddit",
        label="Reddit",
        domains=("reddit.com", "redd.it", "redditmedia.com"),
        post_patterns=(r"/comments/\w+",),
    ),
    Platform(
        key="threads",
        label="Threads",
        domains=("threads.net", "threads.com"),
        post_patterns=(r"/post/", r"/t/"),
    ),
    Platform(
        key="mastodon",
        label="Mastodon",
        domains=("mastodon.social", "mastodon.online", "mstdn.social"),
        post_patterns=(r"/@[\w.]+/\d+",),
    ),
    Platform(
        key="bluesky",
        label="Bluesky",
        domains=("bsky.app", "bsky.social"),
        post_patterns=(r"/post/\w+",),
    ),
    Platform(
        key="pinterest",
        label="Pinterest",
        domains=("pinterest.com", "pin.it", "pinimg.com"),
        post_patterns=(r"^/pin/\d+",),
    ),
    Platform(
        key="vk",
        label="VK",
        domains=("vk.com", "vk.ru"),
        post_patterns=(r"wall-?\d+", r"/photo-?\d+"),
    ),
    Platform(
        key="flickr",
        label="Flickr",
        domains=("flickr.com", "staticflickr.com"),
        post_patterns=(r"/photos/[\w@-]+/\d+",),
    ),
)

_PLATFORM_BY_KEY = {p.key: p for p in PLATFORMS}


@dataclass
class Classification:
    platform_key: str
    platform_label: str
    is_social: bool
    is_post_url: bool
    host: Optional[str]

    def to_dict(self) -> dict:
        return {
            "platform": self.platform_key,
            "platform_label": self.platform_label,
            "is_social": self.is_social,
            "is_post_url": self.is_post_url,
            "host": self.host,
        }


OTHER = Classification(
    platform_key="other",
    platform_label="Other website",
    is_social=False,
    is_post_url=False,
    host=None,
)


def normalize_host(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    # `www.` and `m.` are presentation prefixes, not different services.
    for prefix in ("www.", "m.", "mobile.", "web."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    return host or None


def classify_url(url: Optional[str]) -> Classification:
    """Map a page URL to a platform, or `OTHER` if it is not a known social host."""
    if not url:
        return OTHER
    host = normalize_host(url)
    if not host:
        return OTHER

    parsed = urlparse(url)
    path_and_query = parsed.path + ("?" + parsed.query if parsed.query else "")

    for platform in PLATFORMS:
        if platform.matches(host):
            return Classification(
                platform_key=platform.key,
                platform_label=platform.label,
                is_social=platform.is_social,
                is_post_url=platform.looks_like_post(path_and_query),
                host=host,
            )
    return Classification(
        platform_key="other",
        platform_label="Other website",
        is_social=False,
        is_post_url=False,
        host=host,
    )


def platform_label(key: str) -> str:
    platform = _PLATFORM_BY_KEY.get(key)
    return platform.label if platform else "Other website"
