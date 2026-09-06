"""Provider selection.

One function decides which provider the pipeline talks to. Adding a second live
vendor means adding a branch here and a class next to `serpapi.py` -- nothing
else in the codebase changes.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Settings, get_settings
from .base import ReverseSearchProvider
from .fallback import NullProvider, ReplayProvider
from .serpapi import GoogleLensProvider

_LIVE_PROVIDERS = {"serpapi": GoogleLensProvider, "google_lens": GoogleLensProvider}


def build_provider(
    settings: Settings | None = None, replay_fixture: str | Path | None = None
) -> ReverseSearchProvider:
    settings = settings or get_settings()

    if replay_fixture is not None:
        return ReplayProvider(replay_fixture)

    factory = _LIVE_PROVIDERS.get(settings.search_provider)
    if factory is None:
        return NullProvider(
            f"Unknown search provider '{settings.search_provider}'. "
            f"Supported: {', '.join(sorted(_LIVE_PROVIDERS))}."
        )

    provider = factory(settings)
    if not provider.configured:
        return NullProvider(
            "SERPAPI_KEY is not set. RAYA performs a real reverse image search or "
            "none at all -- it will not fabricate candidates."
        )
    return provider
