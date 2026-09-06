#!/usr/bin/env python3
"""Threshold calibration for the SFace comparison step.

RAYA's operating threshold decides what counts as a verified visual match, so
it should be an empirical choice on real data rather than a number copied from
a model card. This measures, on an identity-labelled image set:

  * the genuine (same person) and impostor (different people) score
    distributions,
  * false match rate (FMR) and false non-match rate (FNMR) across a sweep,
  * the equal error rate and the threshold that achieves it,
  * the operating point RAYA actually ships, with its measured error rates.

Deliberately reported, not hidden:

  * the *worst* genuine pairs and *best* impostor pairs, because those are
    where label noise in an automatically curated set shows up, and a reader
    should be able to judge the set rather than take the numbers on faith;
  * that this is one model on one modest set of mostly high-quality official
    portraits, which is not a population-level accuracy claim.

Usage:
    python benchmarks/calibrate.py [--dir DIR] [--json OUT]
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from raya.config import get_settings  # noqa: E402
from raya.face.detector import YuNetDetector  # noqa: E402
from raya.face.encoder import SFaceEncoder  # noqa: E402
from raya.util.imaging import decode_image  # noqa: E402


@dataclass
class Pair:
    a: str
    b: str
    score: float
    genuine: bool


def load_embeddings(root: Path, settings, detector, encoder):
    """Embed one face per image, grouped by the identity its folder names."""
    identities: dict[str, list[tuple[str, object]]] = {}
    skipped = 0

    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(folder.glob("*.jpg")):
            try:
                image = decode_image(path.read_bytes(), settings)
                faces = detector.detect(image.bgr)
                if len(faces) != 1:
                    skipped += 1
                    continue
                embedding = encoder.encode(image.bgr, faces[0])
            except Exception:  # noqa: BLE001 - a bad file must not stop the study
                skipped += 1
                continue
            identities.setdefault(folder.name, []).append((path.name, embedding))

    # An identity with one usable image contributes no genuine pair.
    identities = {k: v for k, v in identities.items() if len(v) >= 2}
    return identities, skipped


def all_pairs(identities, encoder) -> list[Pair]:
    pairs: list[Pair] = []
    flat = [(name, file, emb) for name, items in identities.items() for file, emb in items]

    for (name_a, file_a, emb_a), (name_b, file_b, emb_b) in itertools.combinations(flat, 2):
        pairs.append(
            Pair(
                a=f"{name_a}/{file_a}",
                b=f"{name_b}/{file_b}",
                score=encoder.similarity(emb_a, emb_b),
                genuine=(name_a == name_b),
            )
        )
    return pairs


def rates(pairs: list[Pair], threshold: float) -> dict:
    genuine = [p for p in pairs if p.genuine]
    impostor = [p for p in pairs if not p.genuine]

    # FNMR: genuine pairs we wrongly reject. FMR: impostor pairs we wrongly accept.
    false_non_match = sum(1 for p in genuine if p.score < threshold)
    false_match = sum(1 for p in impostor if p.score >= threshold)

    return {
        "threshold": round(threshold, 4),
        "fnmr": false_non_match / len(genuine) if genuine else 0.0,
        "fmr": false_match / len(impostor) if impostor else 0.0,
        "tpr": 1 - (false_non_match / len(genuine)) if genuine else 0.0,
        "false_non_matches": false_non_match,
        "false_matches": false_match,
    }


def describe(scores: list[float]) -> dict:
    if not scores:
        return {}
    ordered = sorted(scores)
    n = len(ordered)

    def pct(p: float) -> float:
        return ordered[min(n - 1, max(0, int(round(p * (n - 1)))))]

    return {
        "count": n,
        "min": round(ordered[0], 4),
        "p05": round(pct(0.05), 4),
        "median": round(pct(0.5), 4),
        "p95": round(pct(0.95), 4),
        "max": round(ordered[-1], 4),
        "mean": round(sum(ordered) / n, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(REPO_ROOT / ".raya-data" / "calibration"))
    parser.add_argument("--json", default=str(REPO_ROOT / "benchmarks" / "calibration.json"))
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.exists():
        print(f"No calibration set at {root}.")
        print("Run: python scripts/fetch_calibration_set.py")
        return 1

    settings = get_settings()
    detector = YuNetDetector(settings)
    encoder = SFaceEncoder(settings)

    print("Loading calibration set...")
    identities, skipped = load_embeddings(root, settings, detector, encoder)
    if not identities:
        print("No identity had two usable images; cannot calibrate.")
        return 1

    pairs = all_pairs(identities, encoder)
    genuine = [p.score for p in pairs if p.genuine]
    impostor = [p.score for p in pairs if not p.genuine]

    images = sum(len(v) for v in identities.values())
    print(f"\n{images} images | {len(identities)} identities | {skipped} skipped")
    print(f"{len(genuine)} genuine pairs | {len(impostor)} impostor pairs\n")

    print("SCORE DISTRIBUTIONS")
    g, i = describe(genuine), describe(impostor)
    print(f"{'':10}{'n':>7}{'min':>9}{'p05':>9}{'median':>9}{'p95':>9}{'max':>9}")
    print("-" * 62)
    print(f"{'genuine':10}{g['count']:>7}{g['min']:>9}{g['p05']:>9}{g['median']:>9}{g['p95']:>9}{g['max']:>9}")
    print(f"{'impostor':10}{i['count']:>7}{i['min']:>9}{i['p05']:>9}{i['median']:>9}{i['p95']:>9}{i['max']:>9}")

    # ---- sweep -----------------------------------------------------------
    sweep = [rates(pairs, t / 100) for t in range(0, 101, 2)]

    print("\nTHRESHOLD SWEEP")
    print(f"{'thr':>6}{'FMR':>10}{'FNMR':>10}{'TPR':>10}{'false+':>9}{'false-':>9}")
    print("-" * 54)
    for row in sweep:
        if 0.20 <= row["threshold"] <= 0.70:
            print(
                f"{row['threshold']:>6.2f}{row['fmr']:>10.4f}{row['fnmr']:>10.4f}"
                f"{row['tpr']:>10.4f}{row['false_matches']:>9}{row['false_non_matches']:>9}"
            )

    # Equal error rate: where FMR and FNMR cross.
    eer_row = min(sweep, key=lambda r: abs(r["fmr"] - r["fnmr"]))
    # Strictest useful operating point: the lowest threshold with zero false
    # matches on this set.
    zero_fm = [r for r in sweep if r["false_matches"] == 0]
    zero_fm_threshold = min((r["threshold"] for r in zero_fm), default=None)

    shipped = rates(pairs, settings.similarity_threshold)

    print("\nOPERATING POINTS")
    print(f"  equal error rate      {eer_row['fmr']:.4f} at threshold {eer_row['threshold']:.2f}")
    if zero_fm_threshold is not None:
        zero_row = next(r for r in zero_fm if r["threshold"] == zero_fm_threshold)
        print(
            f"  first zero-FMR        threshold {zero_fm_threshold:.2f} "
            f"(FNMR {zero_row['fnmr']:.4f})"
        )
    print(
        f"  RAYA ships            threshold {settings.similarity_threshold:.2f} "
        f"-> FMR {shipped['fmr']:.4f}, FNMR {shipped['fnmr']:.4f}, TPR {shipped['tpr']:.4f}"
    )

    # ---- where the set is weakest ---------------------------------------
    worst_genuine = sorted((p for p in pairs if p.genuine), key=lambda p: p.score)[:5]
    best_impostor = sorted((p for p in pairs if not p.genuine), key=lambda p: -p.score)[:5]

    print("\nWORST GENUINE PAIRS (hardest same-person comparisons)")
    for p in worst_genuine:
        print(f"  {p.score:.4f}  {p.a}  vs  {p.b}")
    print("\nHIGHEST IMPOSTOR PAIRS (closest different-person comparisons)")
    for p in best_impostor:
        print(f"  {p.score:.4f}  {p.a}  vs  {p.b}")
    print("\n  Note: an automatically curated set carries label noise. A very low")
    print("  genuine score or very high impostor score may be a mislabelled image")
    print("  rather than a model error.")

    payload = {
        "images": images,
        "identities": len(identities),
        "skipped": skipped,
        "genuine_pairs": len(genuine),
        "impostor_pairs": len(impostor),
        "genuine": g,
        "impostor": i,
        "sweep": sweep,
        "eer": eer_row,
        "first_zero_fmr_threshold": zero_fm_threshold,
        "shipped_threshold": settings.similarity_threshold,
        "shipped_rates": shipped,
        "encoder": encoder.describe(),
        "detector": detector.describe(),
        "worst_genuine": [{"a": p.a, "b": p.b, "score": round(p.score, 4)} for p in worst_genuine],
        "best_impostor": [{"a": p.a, "b": p.b, "score": round(p.score, 4)} for p in best_impostor],
    }
    Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWritten to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
