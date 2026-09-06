#!/usr/bin/env python3
"""Run RAYA's five demonstration cases end to end.

Every case exercises the real pipeline: real decoding, real YuNet detection,
real SFace encoding, real HTTP retrieval of candidate images, real
canonicalization and hashing. The runs are saved to `.raya-data/runs`, so each
one is browsable afterwards at `/evidence/<id>` and `/replay/<id>`.

Two substitutions, both stated in the output and both recorded in the evidence:

  * The reverse image search is served from a recorded fixture rather than a
    live paid API, so the demo is reproducible offline and costs nothing. Every
    such run is stamped `is_replay: true` and the UI labels it a replay. Set
    SERPAPI_KEY and run a real verification to see the live path.
  * Candidate images are served from a local HTTP server rather than a social
    platform, because the platforms block automated fetching. The bytes are
    still downloaded over TCP and hashed exactly as they would be in a real run.

What the cases are for:

    A  positive          a genuine match is found and verified
    B  hard negative     a different person is rejected on our own comparison
    C  many candidates   several are evaluated, exactly one passes
    D  no face           the run stops before any search happens
    E  tamper            a verified run's evidence is altered and detected

Usage:
    python demo/run_demo.py [--case A] [--keep-server]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))

from raya.config import get_settings  # noqa: E402
from raya.events import EventBus  # noqa: E402
from raya.evidence.integrity import simulate_tamper  # noqa: E402
from raya.face.detector import YuNetDetector  # noqa: E402
from raya.face.encoder import SFaceEncoder  # noqa: E402
from raya.pipeline.orchestrator import Pipeline  # noqa: E402
from raya.pipeline.store import RunStore  # noqa: E402
from raya.search.fallback import ReplayProvider  # noqa: E402
from raya.storage.ipfs import build_store  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def start_fixture_server() -> tuple[ThreadingHTTPServer, str]:
    handler = partial(_QuietHandler, directory=str(FIXTURES))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


CASES = {
    "A": {
        "title": "Positive - a genuine match is found and verified",
        "input": "subject_a.jpg",
        "expect": "a verified match on a public social source",
        "results": [
            ("A post", "https://x.com/subject/status/1789456123", "subject_a_alt.jpg", "X"),
        ],
    },
    "B": {
        "title": "Hard negative - a different person is rejected",
        "input": "subject_a.jpg",
        "expect": "no verified match; the candidate is rejected on similarity",
        "results": [
            ("Someone else", "https://x.com/other/status/4242", "subject_b.jpg", "X"),
        ],
    },
    "C": {
        "title": "Many candidates - several evaluated, one passes",
        "input": "subject_a.jpg",
        "expect": "one verified match among several rejections",
        "results": [
            ("Different person", "https://x.com/other/status/4242", "subject_b.jpg", "X"),
            ("News article", "https://cnn.com/2026/story", "subject_a_alt.jpg", "CNN"),
            ("No face in image", "https://instagram.com/p/Cxyz123/", "no_face.jpg", "Instagram"),
            ("The real source", "https://x.com/subject/status/1789456123", "subject_a_alt.jpg", "X"),
            ("Dead link", "https://x.com/gone/status/1", "does_not_exist.jpg", "X"),
        ],
    },
    "D": {
        "title": "No face - the run stops before any search",
        "input": "no_face.jpg",
        "expect": "stops at face detection; no search is performed",
        "results": [],
    },
    "E": {
        "title": "Tamper - a verified record is altered and detected",
        "input": "subject_a.jpg",
        "expect": "evidence hash diverges when one field is changed",
        "results": [
            ("A post", "https://x.com/subject/status/1789456123", "subject_a_alt.jpg", "X"),
        ],
        "tamper": True,
    },
}


def write_fixture(tmp: Path, base_url: str, key: str, results) -> Path:
    path = tmp / f"search_{key}.json"
    path.write_text(
        json.dumps(
            {
                "provider": "recorded_google_lens",
                "results": [
                    {
                        "position": i + 1,
                        "title": title,
                        "page_url": page_url,
                        "image_url": f"{base_url}/{filename}",
                        "source_name": source,
                    }
                    for i, (title, page_url, filename, source) in enumerate(results)
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


async def run_case(key: str, case: dict, base_url: str, tmp: Path, settings, detector, encoder):
    print(f"\n{BOLD}Case {key} - {case['title']}{RESET}")
    print(f"{DIM}expected: {case['expect']}{RESET}")

    fixture = write_fixture(tmp, base_url, key, case["results"])
    pipeline = Pipeline(
        settings=settings,
        detector=detector,
        encoder=encoder,
        provider=ReplayProvider(fixture),
        store=build_store(settings),
    )

    image = (FIXTURES / case["input"]).read_bytes()
    bus = EventBus("pending")
    result = await pipeline.run(image, bus=bus)

    RunStore(settings).save(result, bus.log)

    colour = GREEN if result.status.is_match else YELLOW
    if result.status.value in ("failed", "invalid_input"):
        colour = RED

    print(f"  status      {colour}{result.status.value}{RESET}")
    print(f"  headline    {result.headline}")
    print(f"  id          {result.verification_id}")

    if result.candidates:
        print(f"  candidates  {len(result.candidates)} "
              f"({len(result.social_candidates)} social, "
              f"{len(result.compared_candidates)} compared)")
        for candidate in result.candidates:
            score = (
                f"{candidate.verdict.similarity:.4f}"
                if candidate.verdict and candidate.verdict.similarity is not None
                else "     -"
            )
            tick = GREEN + "PASS" + RESET if candidate.verified else DIM + "----" + RESET
            print(f"    {tick}  {score}  {candidate.platform_label:<10} {candidate.status.value}")

    if result.evidence:
        print(f"  evidence    {result.evidence.sha256}")
    if result.storage:
        published = "published" if result.storage.published else "local only"
        print(f"  ipfs        {result.storage.cid} ({published})")
    if result.anchor:
        print(f"  anchored    {result.anchor.tx_hash}")
    elif result.evidence:
        print(f"  anchored    {YELLOW}no - chain not configured{RESET}")

    if case.get("tamper") and result.evidence:
        outcome = simulate_tamper(result.evidence, "match.similarity")
        print(f"\n  {BOLD}Tamper test{RESET}")
        print(f"    field       {outcome.field_path}")
        print(f"    original    {outcome.original_value}  ->  {outcome.original_hash[:24]}...")
        print(f"    tampered    {outcome.tampered_value}  ->  {outcome.tampered_hash[:24]}...")
        verdict = (
            f"{GREEN}TAMPERING DETECTED{RESET}"
            if outcome.detected
            else f"{RED}NOT DETECTED - this is a bug{RESET}"
        )
        print(f"    result      {verdict}")

    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RAYA demonstration cases.")
    parser.add_argument("--case", help="run a single case (A-E)")
    args = parser.parse_args()

    settings = get_settings().model_copy(
        update={
            # The fixture images are served from loopback, which the SSRF guard
            # blocks by default. Enabled only for the demo.
            "allow_private_network": True,
        }
    )

    if not settings.yunet_path.exists() or not settings.sface_path.exists():
        print(f"{RED}Models are missing. Run: python scripts/fetch_models.py{RESET}")
        return 1

    print(f"{BOLD}RAYA demonstration{RESET}")
    print("Real detection, encoding, retrieval, hashing. Recorded search fixture.")
    print(f"{DIM}Threshold {settings.similarity_threshold} | "
          f"{settings.chain_name} | runs saved to {settings.data_dir}{RESET}")

    server, base_url = start_fixture_server()
    tmp = settings.data_dir / "demo"
    tmp.mkdir(parents=True, exist_ok=True)

    detector = YuNetDetector(settings)
    encoder = SFaceEncoder(settings)

    keys = [args.case.upper()] if args.case else list(CASES)
    results = {}
    try:
        for key in keys:
            if key not in CASES:
                print(f"{RED}Unknown case {key}. Choose from {', '.join(CASES)}.{RESET}")
                return 1
            results[key] = await run_case(
                key, CASES[key], base_url, tmp, settings, detector, encoder
            )
    finally:
        server.shutdown()
        server.server_close()

    print(f"\n{BOLD}Summary{RESET}")
    print(f"{'Case':<6}{'Status':<26}{'Similarity':<12}Verification")
    print("-" * 78)
    for key, result in results.items():
        sim = f"{result.similarity:.4f}" if result.similarity is not None else "-"
        print(f"{key:<6}{result.status.value:<26}{sim:<12}{result.verification_id}")

    print(f"\n{DIM}Browse any run at http://localhost:3000/evidence/<id>{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
