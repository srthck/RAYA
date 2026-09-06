#!/usr/bin/env python3
"""Regenerate the environment background derivatives.

The background photograph is RAYA's visual identity, but the full-resolution
source is ~2.6 MB -- far too heavy to ship behind translucent interface
surfaces. This produces the WebP derivatives that are actually served.

The source is kept out of `public/` (and out of git) precisely so it cannot be
served by accident; only the outputs below are deployed.

    source  1536x1024 PNG   2.65 MB
    ->      1536 / 1024 / 640 px WebP, plus a 24px blurred placeholder
    ->      ~450 KB total, ~91% smaller

Usage:
    python scripts/build_environment.py [--source PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "assets" / "environment-source.png"
OUT_DIR = REPO_ROOT / "apps" / "web" / "public"

# Widths worth serving. The image sits behind translucent panels and a daylight
# wash, so it never needs to resolve fine detail -- quality 80 is generous.
WIDTHS = (1536, 1024, 640)
QUALITY = 80


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        print(f"Source not found: {source}")
        print("Place the environment photograph there, or pass --source.")
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required: pip install pillow")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGB")
    print(f"source {image.width}x{image.height}  {source.stat().st_size / 1e6:.2f} MB\n")

    total = 0
    for width in WIDTHS:
        # Never upscale past the source: it would add bytes without detail.
        if width > image.width:
            continue
        height = round(image.height * width / image.width)
        resized = image.resize((width, height), Image.LANCZOS)
        target = OUT_DIR / f"environment-{width}.webp"
        resized.save(target, "WEBP", quality=QUALITY, method=6)
        total += target.stat().st_size
        print(f"  {target.name:26} {width}x{height:<6} {target.stat().st_size / 1024:7.1f} KB")

    # A 24px blur stand-in, inlined under the real image so the first paint is
    # never bare white while the photograph loads.
    placeholder = OUT_DIR / "environment-blur.webp"
    image.resize((24, 16), Image.LANCZOS).save(placeholder, "WEBP", quality=60)
    total += placeholder.stat().st_size
    print(f"  {placeholder.name:26} {'24x16':<13} {placeholder.stat().st_size / 1024:7.1f} KB")

    print(f"\ntotal shipped: {total / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
