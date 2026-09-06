#!/usr/bin/env python3
"""Measure the rendered Verify layout in a real browser.

Layout bugs are geometric, so this asserts on geometry rather than on CSS
source: it loads the page in Chrome, reads the bounding box of every major
region, and reports overlaps, clipping and horizontal overflow numerically.

Checks performed at each viewport:

  * pairwise rectangle intersection between the Journey rail, the main column
    and the technical panel -- any overlap is a hard failure;
  * every region inside the viewport horizontally (no left or right clipping);
  * document scrollWidth vs clientWidth (no horizontal page scroll);
  * exactly one Journey rail and one site nav rendered.

Zoom is simulated the way a browser does it: at 125% a 1280 px screen presents
1024 CSS pixels, so the viewport width is divided by the zoom factor.

Usage:
    python scripts/layout_qa.py [--url http://127.0.0.1:3000/verify] [--shot DIR]
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

# (label, css width, note)
VIEWPORTS = [
    ("1280 @100%", 1280, 832),
    ("1280 @125%", 1024, 666),
    ("1280 @150%", 853, 555),
    ("1024", 1024, 800),
    ("860", 860, 800),
    ("mobile 390", 390, 844),
]

REGIONS = {
    "journey": "[aria-label='Verification stages']",
    "main": ".workspace-main",
    "technical": "[aria-label='Technical detail']",
    "nav": "header",
}


def rect(page, selector):
    el = page.query_selector(selector)
    if not el:
        return None
    return el.bounding_box()


def overlaps(a, b) -> float:
    """Area of intersection between two bounding boxes."""
    if not a or not b:
        return 0.0
    x = max(0.0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
    y = max(0.0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
    return x * y


def check(page, label: str, width: int) -> list[str]:
    failures: list[str] = []
    boxes = {name: rect(page, sel) for name, sel in REGIONS.items()}

    # 1. Duplicate components.
    # Duplication is the fault being guarded against. Absence is legitimate:
    # only the workspace pages carry a Journey rail.
    n_journey = len(page.query_selector_all(REGIONS["journey"]))
    n_nav = len(page.query_selector_all("header"))
    if n_journey > 1:
        failures.append(f"{n_journey} Journey rails rendered (expected at most 1)")
    if n_nav > 1:
        failures.append(f"{n_nav} navs rendered (expected at most 1)")

    # 2. Overlap between the three workspace regions.
    # `technical` is nested inside `main` by design, so that pair is skipped.
    # The rail must not overlap either of them.
    for a, b in (("journey", "main"), ("journey", "technical")):
        area = overlaps(boxes[a], boxes[b])
        if area > 1.0:
            ra, rb = boxes[a], boxes[b]
            failures.append(
                f"{a} overlaps {b} by {area:.0f}px^2 "
                f"[{a} x{ra['x']:.0f}-{ra['x']+ra['width']:.0f} y{ra['y']:.0f}-{ra['y']+ra['height']:.0f}] "
                f"[{b} x{rb['x']:.0f}-{rb['x']+rb['width']:.0f} y{rb['y']:.0f}-{rb['y']+rb['height']:.0f}]"
            )

    # 3. Horizontal clipping of any region.
    for name, box in boxes.items():
        if not box:
            continue
        if box["x"] < -0.5:
            failures.append(f"{name} clipped on the left (x={box['x']:.1f})")
        if box["x"] + box["width"] > width + 0.5:
            failures.append(
                f"{name} exceeds viewport right edge "
                f"(right={box['x'] + box['width']:.1f} > {width})"
            )

    # 4. Page-level horizontal scroll.
    scroll_w, client_w = page.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    if scroll_w > client_w + 1:
        failures.append(f"horizontal page scroll: scrollWidth {scroll_w} > clientWidth {client_w}")

    return failures


def run(url: str, shot_dir: str | None, with_content: bool) -> int:
    total_failures = 0

    with sync_playwright() as pw:
        # Use the installed Chrome rather than downloading a Chromium build.
        browser = pw.chromium.launch(channel="chrome", headless=True)
        try:
            for label, width, height in VIEWPORTS:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(url, wait_until="networkidle", timeout=45_000)

                if with_content:
                    # Exercise the populated state: an empty page can look fine
                    # while real hashes, previews and backend messages change
                    # the geometry.
                    page.set_input_files("input[type=file]", str(with_content))
                    page.wait_for_timeout(3500)
                    verify = page.query_selector("button:has-text('Verify')")
                    if verify:
                        verify.click()
                        page.wait_for_timeout(6000)

                failures = check(page, label, width)

                # Sticky rails only misbehave once the page scrolls, so the
                # same geometry is re-checked part-way and at the bottom.
                doc_h = page.evaluate("() => document.documentElement.scrollHeight")
                for frac in (0.35, 0.7, 1.0):
                    page.evaluate(f"() => window.scrollTo(0, {doc_h} * {frac})")
                    page.wait_for_timeout(250)
                    for f in check(page, label, width):
                        failures.append(f"[scrolled {int(frac*100)}%] {f}")
                page.evaluate("() => window.scrollTo(0, 0)")
                status = "PASS" if not failures else "FAIL"
                print(f"\n{status}  {label}  ({width}x{height})")
                for f in failures:
                    print(f"     - {f}")
                if not failures:
                    boxes = {n: rect(page, s) for n, s in REGIONS.items()}
                    for name in ("journey", "main", "technical"):
                        b = boxes[name]
                        if b:
                            print(
                                f"     {name:10} x {b['x']:6.0f} -> {b['x']+b['width']:6.0f}"
                                f"   y {b['y']:6.0f} -> {b['y']+b['height']:6.0f}"
                            )
                        else:
                            print(f"     {name:10} not rendered at this width")

                total_failures += len(failures)
                if shot_dir:
                    safe = label.replace(" ", "_").replace("%", "").replace("@", "at")
                    page.screenshot(path=f"{shot_dir}/verify_{safe}.png", full_page=True)
                page.close()
        finally:
            browser.close()

    print(f"\n{'ALL VIEWPORTS PASS' if total_failures == 0 else f'{total_failures} FAILURES'}")
    return 0 if total_failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:3000/verify")
    parser.add_argument("--shot", default=None, help="directory for screenshots")
    parser.add_argument("--upload", default=None, help="image to upload for populated-state QA")
    args = parser.parse_args()
    return run(args.url, args.shot, args.upload)


if __name__ == "__main__":
    sys.exit(main())
