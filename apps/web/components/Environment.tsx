"use client";

/**
 * The environmental background.
 *
 * RAYA's identity is a bright alpine lake: sky, mountains, clear water,
 * daylight. The interface sits *inside* that environment rather than on a flat
 * canvas, so the background is built as layers rather than a single
 * `background-image`.
 *
 * Depth from one photograph
 * -------------------------
 * The source is a single flat image, so there is no real sky/mountain/water
 * separation to move independently. Instead the same image is drawn twice and
 * soft-masked at the horizon (~50%): the upper band carries sky and peaks, the
 * lower band carries water. Moving them at different rates produces genuine
 * differential parallax. The masks overlap across a wide feathered band, so
 * the few pixels of relative movement never reveal a seam.
 *
 * Movement budget is deliberately tiny -- felt, not noticed:
 *
 *   sky / mountains   ~3px
 *   water             ~1px
 *   daylight wash     ~1px
 *   cursor light      ~20px
 *
 * Performance
 * -----------
 * Pointer movement never touches React state. The handler writes to a ref, and
 * a single rAF loop eases the current value toward the target and writes two
 * CSS custom properties on one element. Every layer derives its own offset
 * from those two variables in CSS, so one property write moves all four layers
 * and nothing re-renders.
 *
 * The loop parks itself once the value has settled, so an idle page costs
 * nothing.
 *
 * It is decorative only. It never encodes pipeline state, it is
 * `pointer-events: none` throughout, and it is disabled entirely for touch
 * input and for `prefers-reduced-motion`.
 */

import { useEffect, useRef } from "react";

export function Environment() {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    // No cursor to follow on touch, and no decorative motion when the user has
    // asked for less of it.
    const fine = window.matchMedia("(pointer: fine)");
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!fine.matches || calm.matches) return;

    // Normalised pointer position in [-1, 1], target and eased-current.
    const target = { x: 0, y: 0 };
    const current = { x: 0, y: 0 };
    let frame = 0;
    let running = false;

    const tick = () => {
      // Exponential smoothing: fast enough to feel responsive, slow enough
      // that a flick of the mouse glides rather than snaps.
      current.x += (target.x - current.x) * 0.045;
      current.y += (target.y - current.y) * 0.045;

      root.style.setProperty("--px", current.x.toFixed(4));
      root.style.setProperty("--py", current.y.toFixed(4));

      const settled =
        Math.abs(target.x - current.x) < 0.0006 &&
        Math.abs(target.y - current.y) < 0.0006;

      if (settled) {
        // Park the loop; the next pointer move restarts it. An idle page then
        // costs nothing at all.
        running = false;
        return;
      }
      frame = requestAnimationFrame(tick);
    };

    const start = () => {
      if (running) return;
      running = true;
      frame = requestAnimationFrame(tick);
    };

    const onMove = (event: PointerEvent) => {
      target.x = (event.clientX / window.innerWidth) * 2 - 1;
      target.y = (event.clientY / window.innerHeight) * 2 - 1;
      // The light field follows the actual cursor, in pixels.
      root.style.setProperty("--lx", `${event.clientX}px`);
      root.style.setProperty("--ly", `${event.clientY}px`);
      start();
    };

    const onLeave = () => {
      target.x = 0;
      target.y = 0;
      start();
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);

    return () => {
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div ref={rootRef} className="env" aria-hidden="true">
      {/* Instant first paint: a 0.2 KB blurred placeholder under the real
          image, so the page never flashes bare white. */}
      <div className="env-placeholder" />
      <div className="env-sky" />
      <div className="env-water" />
      <div className="env-wash" />
      <div className="env-light" />
    </div>
  );
}
