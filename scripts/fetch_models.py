#!/usr/bin/env python3
"""Download the YuNet and SFace ONNX models.

The models live in OpenCV Zoo under git-lfs, so the usual `raw.githubusercontent`
URL returns a ~130-byte pointer file rather than the model. We fetch from
`media.githubusercontent.com`, which serves the real LFS content, and verify the
SHA-256 of every download against a pinned digest.

Pinning matters here beyond ordinary supply-chain hygiene: the evidence record
names the model that produced each similarity score, so that claim is only
meaningful if the bytes behind the name are the expected ones.

Usage:
    python scripts/fetch_models.py [--force] [--models-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

# This file is <repo>/scripts/fetch_models.py, so parents[1] is the repository
# root:
#   parents[0] = <repo>/scripts
#   parents[1] = <repo>
#
# Anchored on __file__ rather than the working directory so that the build step
# writes to the same place `raya.config` reads from, whatever cwd the host uses.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS_DIR = REPO_ROOT / "models"
BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"


def _models_dir_from_env() -> Path | None:
    """Resolve MODELS_DIR exactly the way `raya.config.Settings` does.

    This script stays dependency-free on purpose -- it has to run before
    `pip install` has necessarily succeeded -- so it cannot simply import the
    settings object. It therefore reproduces pydantic-settings' precedence:
    a real environment variable wins over the same key in the repo's `.env`.
    """
    value = os.environ.get("MODELS_DIR")
    if value:
        return Path(value)

    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return None
    for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key.strip() == "MODELS_DIR":
            val = val.strip().strip('"').strip("'")
            return Path(val) if val else None
    return None

MODELS = [
    {
        "name": "face_detection_yunet_2023mar.onnx",
        "url": f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "size": 232589,
        "role": "face detection (YuNet)",
    },
    {
        "name": "face_recognition_sface_2021dec.onnx",
        "url": f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "size": 38696353,
        "role": "face recognition (SFace)",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    # Download to a temporary sibling and rename only after the checksum
    # passes, so an interrupted run can never leave a truncated model in place
    # that would fail confusingly at inference time.
    temp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "RAYA-model-fetch/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        read = 0
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            read += len(chunk)
            if total:
                pct = read * 100 // total
                print(f"\r    {pct:3d}%  {read / 1e6:6.1f} / {total / 1e6:.1f} MB", end="")
    print()
    temp.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch RAYA face models.")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument(
        "--models-dir",
        default=None,
        help="override the models directory (default: $MODELS_DIR, else <repo>/models)",
    )
    args = parser.parse_args()

    models_dir = (
        Path(args.models_dir) if args.models_dir else (_models_dir_from_env() or DEFAULT_MODELS_DIR)
    )
    models_dir = models_dir.resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    print(f"MODEL_DIR={models_dir}")

    failures = 0
    for model in MODELS:
        target = models_dir / model["name"]
        print(f"\n{model['role']}")
        print(f"  {model['name']}")

        if target.exists() and not args.force:
            actual = sha256_file(target)
            if actual == model["sha256"]:
                print(f"  present and verified ({target.stat().st_size / 1e6:.1f} MB)")
                continue
            print("  present but checksum does not match; re-downloading")

        print(f"  downloading from {model['url']}")
        try:
            download(model["url"], target)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}")
            failures += 1
            continue

        actual = sha256_file(target)
        if actual != model["sha256"]:
            print("  CHECKSUM MISMATCH")
            print(f"    expected {model['sha256']}")
            print(f"    actual   {actual}")
            # A wrong file is worse than a missing one: it would load and
            # silently produce scores from an unknown model.
            target.unlink(missing_ok=True)
            failures += 1
            continue
        print(f"  verified {actual[:16]}...")

    # Print the same validation block the API prints at startup, so the build
    # log and the runtime log can be compared line for line.
    yunet = models_dir / MODELS[0]["name"]
    sface = models_dir / MODELS[1]["name"]
    print()
    print(f"MODEL_DIR={models_dir}")
    print(f"YuNet exists={yunet.exists()}")
    print(f"SFace exists={sface.exists()}")

    if failures:
        print(f"\n{failures} model(s) failed. RAYA cannot run without them.")
        return 1
    if not (yunet.exists() and sface.exists()):
        print("\nA model is missing after a run that reported no failures.")
        return 1
    print("\nAll models present and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
