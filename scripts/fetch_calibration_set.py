#!/usr/bin/env python3
"""Assemble a face-verification calibration set from Wikimedia Commons.

Three fixture photographs are enough to prove the encoder separates people at
all; they are nowhere near enough to choose an operating threshold. This builds
a larger, identity-labelled set so `benchmarks/calibrate.py` can measure score
distributions, error rates and a threshold sweep on real data.

Why Commons rather than a standard benchmark: LFW is unreachable from this
environment, and Commons carries a large body of public-domain portraits
(chiefly US federal government works, and NASA imagery).

Automated curation, and its consequences:

  * Files are found by full-text search over the File namespace. Category
    membership is not usable here: a person's Commons category holds only a
    few files directly, with the photographs pushed into subcategories.
  * Only images where the detector finds *exactly one* face of sufficient size
    are kept. That drops group shots, artwork, buildings and signatures, which
    such a search returns in quantity -- roughly three quarters of hits are
    discarded.
  * The filename match is taken as the identity label. This is the weak point:
    a file titled after one person can depict another (a spouse, a colleague,
    a crowd), so the set carries some label noise. `calibrate.py` prints its
    worst genuine pairs and closest impostor pairs precisely so that noise
    stays visible rather than silently distorting the error rates.

The images are cached outside the repository and are not committed.

Usage:
    python scripts/fetch_calibration_set.py [--per-identity 4] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

API = "https://commons.wikimedia.org/w/api.php"
UA = "RAYA-calibration/1.0 (face-verification threshold study)"

# Public figures whose Commons categories are dominated by public-domain
# official photography (US federal government works, NASA, and similar).
IDENTITIES = [
    "Barack Obama", "Joe Biden", "George W. Bush", "Bill Clinton",
    "Jimmy Carter", "Kamala Harris", "Hillary Clinton", "Condoleezza Rice",
    "Colin Powell", "John Kerry", "Nancy Pelosi", "Mike Pence",
    "Antony Blinken", "Janet Yellen", "Buzz Aldrin", "Neil Armstrong",
    "Sally Ride", "Chris Hadfield", "Angela Merkel", "Ban Ki-moon",
    "Christine Lagarde", "Jens Stoltenberg", "Ursula von der Leyen",
    "Justin Trudeau",
]


def api_get(params: dict) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def category_images(name: str, limit: int = 40) -> list[str]:
    """Return thumbnail URLs of candidate images for a person.

    Uses full-text search over the File namespace rather than category
    membership: a person's Commons category typically holds only a handful of
    files directly, with the actual photographs pushed down into
    subcategories, so `categorymembers` returns almost nothing useful.
    """
    try:
        payload = api_get(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": f'intitle:"{name}"',
                "gsrnamespace": "6",
                "gsrlimit": str(limit),
                "prop": "imageinfo",
                "iiprop": "url|size|mime",
                "iiurlwidth": "900",
                "format": "json",
            }
        )
    except Exception as exc:  # noqa: BLE001
        print(f"    image search failed: {exc}")
        return []

    urls: list[str] = []
    for page in (payload.get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("mime", "").startswith("image/"):
            continue
        # Skip vector/animated and very small originals.
        if info.get("mime") in ("image/svg+xml", "image/gif"):
            continue
        if not title_is_plausible(page.get("title", ""), name):
            continue
        url = info.get("thumburl") or info.get("url")
        if url:
            urls.append(url)
    return urls


# Titles that carry a person's name but depict something else. Spot-checking
# the worst genuine pairs found both kinds in the first pass: a Marine aboard
# a ship named after John Kerry, and a speaker at a Hillary Clinton rally.
TITLE_BLOCKLIST = (
    "uss ", "ss ", "school", "university", "college", "airport", "building",
    "center", "centre", "library", "bridge", "hospital", "highway", "statue",
    "memorial", "museum", "stamp", "signature", "logo", "poster", "sign",
    "rally", "campaign", "supporters", "crowd", "protest", "march",
    "map", "chart", "graph", "cartoon", "painting", "mural", "plaque",
    "grave", "tomb", "house", "street", "park", "monument", "coin",
)


def title_is_plausible(title: str, name: str) -> bool:
    """Cheap guard against files named after a person but not depicting them.

    Not exhaustive -- some noise survives, which `calibrate.py` surfaces by
    printing the worst genuine pairs. It removes the systematic cases.
    """
    lowered = title.lower()
    if any(bad in lowered for bad in TITLE_BLOCKLIST):
        return False
    # "with", "and" and "meets" almost always signal two or more subjects.
    surname = name.split()[-1].lower()
    after = lowered.split(surname, 1)[-1] if surname in lowered else ""
    if any(token in after for token in (" with ", " and ", " meets", " greets")):
        return False
    return True


def download(url: str) -> bytes | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read()
    except Exception:  # noqa: BLE001 - a dead file is normal; move on
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-identity", type=int, default=4)
    parser.add_argument("--out", default=str(REPO_ROOT / ".raya-data" / "calibration"))
    parser.add_argument("--min-face-px", type=int, default=80)
    args = parser.parse_args()

    from raya.config import get_settings
    from raya.face.detector import YuNetDetector
    from raya.util.imaging import decode_image

    settings = get_settings()
    if not settings.yunet_path.exists():
        print("Models missing. Run: python scripts/fetch_models.py")
        return 1
    detector = YuNetDetector(settings)

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    total_kept = 0
    for name in IDENTITIES:
        slug = name.lower().replace(" ", "_").replace("-", "_")
        target = out_root / slug
        existing = list(target.glob("*.jpg")) if target.exists() else []
        if len(existing) >= args.per_identity:
            print(f"{name}: already have {len(existing)}")
            total_kept += len(existing)
            continue

        print(f"{name}:")
        target.mkdir(parents=True, exist_ok=True)
        kept = len(existing)

        for url in category_images(name):
            if kept >= args.per_identity:
                break
            data = download(url)
            if not data or len(data) < 20_000:
                continue
            try:
                image = decode_image(data, settings)
            except Exception:  # noqa: BLE001
                continue

            faces = detector.detect(image.bgr)
            # Exactly one sufficiently large face: this is the curation rule
            # that turns a messy category into a usable identity set.
            if len(faces) != 1 or faces[0].quality.size_px < args.min_face_px:
                continue

            (target / f"{slug}_{kept:02d}.jpg").write_bytes(data)
            kept += 1
            print(f"    kept {kept}/{args.per_identity} ({faces[0].quality.size_px}px face)")
            time.sleep(0.25)  # be a polite client of Commons

        total_kept += kept
        if kept < 2:
            print(f"    only {kept} usable image(s); this identity yields no positive pairs")

    identities = [d for d in out_root.iterdir() if d.is_dir() and len(list(d.glob("*.jpg"))) >= 2]
    print(f"\n{total_kept} images across {len(identities)} usable identities in {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
