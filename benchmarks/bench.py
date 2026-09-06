#!/usr/bin/env python3
"""Measure the cost of each pipeline stage.

Reported so that claims about performance in the documentation are measured
rather than asserted, and so a regression is visible. Network-bound stages
(search, candidate retrieval, chain) are excluded: their timing says more about
the network than about RAYA.

Usage:
    python benchmarks/bench.py [--runs 20]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from raya.config import get_settings  # noqa: E402
from raya.evidence.bundle import EvidenceBundle  # noqa: E402
from raya.face.detector import YuNetDetector  # noqa: E402
from raya.face.encoder import SFaceEncoder  # noqa: E402
from raya.util.hashing import sha256_bytes  # noqa: E402
from raya.util.imaging import decode_image  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"


def timed(fn, runs: int) -> dict:
    """Run `fn` `runs` times after one warm-up, returning millisecond stats."""
    fn()  # warm-up: first call pays lazy model graph initialisation
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {
        "mean": statistics.mean(samples),
        "median": statistics.median(samples),
        "p95": samples[min(len(samples) - 1, int(len(samples) * 0.95))],
        "min": samples[0],
        "max": samples[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.yunet_path.exists() or not settings.sface_path.exists():
        print("Models are missing. Run: python scripts/fetch_models.py")
        return 1

    data = (FIXTURES / "subject_a.jpg").read_bytes()
    alt = (FIXTURES / "subject_a_alt.jpg").read_bytes()

    load_start = time.perf_counter()
    detector = YuNetDetector(settings)
    encoder = SFaceEncoder(settings)
    load_ms = (time.perf_counter() - load_start) * 1000

    image = decode_image(data, settings)
    alt_image = decode_image(alt, settings)
    face = detector.detect(image.bgr)[0]
    alt_face = detector.detect(alt_image.bgr)[0]
    embedding = encoder.encode(image.bgr, face)
    alt_embedding = encoder.encode(alt_image.bgr, alt_face)

    record = {
        "schema_version": "1.0",
        "verification_id": "VER-BENCH",
        "candidates": [{"id": f"c{i:03d}", "similarity": 0.5} for i in range(12)],
        "match": {"similarity": 0.8140},
    }

    stages = {
        "SHA-256 of input bytes": lambda: sha256_bytes(data),
        "Decode + validate": lambda: decode_image(data, settings),
        "Face detection (YuNet)": lambda: detector.detect(image.bgr),
        "Alignment (112x112 crop)": lambda: encoder.align(image.bgr, face),
        "Face encoding (SFace)": lambda: encoder.encode(image.bgr, face),
        "Similarity comparison": lambda: encoder.similarity(embedding, alt_embedding),
        "Evidence canonicalize + hash": lambda: EvidenceBundle.create(record),
    }

    print("RAYA stage benchmarks")
    print(f"{args.runs} runs after warm-up | {image.width}x{image.height} input")
    print(f"Model load (once, at startup): {load_ms:.0f} ms")
    print()
    print(f"{'Stage':<32}{'median':>11}{'mean':>11}{'p95':>11}{'max':>11}")
    print("-" * 78)

    for name, fn in stages.items():
        stats = timed(fn, args.runs)
        print(
            f"{name:<32}"
            f"{stats['median']:>8.2f} ms"
            f"{stats['mean']:>8.2f} ms"
            f"{stats['p95']:>8.2f} ms"
            f"{stats['max']:>8.2f} ms"
        )

    # The local (non-network) portion of one verification against one candidate.
    def local_path():
        img = decode_image(data, settings)
        f = detector.detect(img.bgr)[0]
        e = encoder.encode(img.bgr, f)
        cimg = decode_image(alt, settings)
        cf = detector.detect(cimg.bgr)[0]
        ce = encoder.encode(cimg.bgr, cf)
        encoder.similarity(e, ce)
        EvidenceBundle.create(record)

    stats = timed(local_path, max(5, args.runs // 2))
    print("-" * 78)
    print(
        f"{'Full local path, 1 candidate':<32}"
        f"{stats['median']:>8.2f} ms"
        f"{stats['mean']:>8.2f} ms"
        f"{stats['p95']:>8.2f} ms"
        f"{stats['max']:>8.2f} ms"
    )
    print()
    print("Excludes reverse search, candidate download and chain latency, which")
    print("are network-bound and dominate wall-clock time in a real run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
