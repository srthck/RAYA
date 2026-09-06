"use client";

/**
 * The left rail: where are we?
 *
 * Eight numbered stages, each reflecting an event the backend actually emitted.
 * Four states are distinguished, and the distinctions carry meaning:
 *
 *   pending   the stage has not been reached
 *   running   in progress
 *   complete  finished successfully
 *   failed    attempted and went wrong
 *   skipped   never attempted, because it was not configured
 *
 * "skipped" is not a softer "failed". An unanchored run did not break -- it was
 * never given a chain to anchor to, and the rail must not paint that red.
 */

import { motion } from "framer-motion";

import { STAGE_ORDER, type PipelineState, type StageState } from "@/lib/usePipeline";

const COLORS: Record<StageState, string> = {
  idle: "var(--ink-quaternary)",
  // In progress reads as water; completed reads as verified green. Two
  // different meanings, two different colours.
  active: "var(--accent)",
  done: "var(--verified)",
  failed: "var(--rejected)",
  skipped: "var(--pending)",
};

const GLYPH: Record<StageState, string> = {
  idle: "○",
  active: "◉",
  done: "✓",
  failed: "✕",
  skipped: "—",
};

const STATE_WORD: Record<StageState, string> = {
  idle: "pending",
  active: "running",
  done: "complete",
  failed: "failed",
  skipped: "not run",
};

function Marker({ state }: { state: StageState }) {
  const color = COLORS[state];
  const glyph = (
    <span
      aria-hidden
      style={{
        display: "block",
        width: 14,
        textAlign: "center",
        fontSize: state === "done" || state === "failed" ? 11 : 10,
        lineHeight: "14px",
        color,
      }}
    >
      {GLYPH[state]}
    </span>
  );

  if (state === "active") {
    return (
      <span style={{ position: "relative", display: "block" }}>
        <motion.span
          aria-hidden
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: 18,
            height: 18,
            marginLeft: -9,
            marginTop: -9,
            borderRadius: "50%",
            background: "var(--accent)",
          }}
          animate={{ opacity: [0.22, 0.05, 0.22], scale: [0.85, 1.25, 0.85] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        />
        <span style={{ position: "relative" }}>{glyph}</span>
      </span>
    );
  }
  return glyph;
}

export function JourneyRail({ state }: { state: PipelineState }) {
  return (
    <nav aria-label="Verification stages">
      <p className="label" style={{ marginBottom: "var(--s4)" }}>
        Journey
      </p>

      <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {STAGE_ORDER.map((entry, index) => {
          const stage = state.stages[entry.id];
          const last = index === STAGE_ORDER.length - 1;
          const reached = stage.state !== "idle";

          return (
            <li key={entry.id} style={{ display: "flex", gap: "var(--s3)", minWidth: 0 }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <Marker state={stage.state} />
                {!last && (
                  <span
                    aria-hidden
                    style={{
                      position: "relative",
                      width: 1.5,
                      flex: 1,
                      minHeight: 30,
                      borderRadius: 2,
                      background: "var(--line)",
                      overflow: "hidden",
                    }}
                  >
                    {/* Fills only when the stage above it actually completed,
                        so the line can never run ahead of the backend. */}
                    <motion.span
                      style={{
                        position: "absolute",
                        inset: 0,
                        transformOrigin: "top",
                        background:
                          stage.state === "done"
                            ? "var(--verified)"
                            : "var(--accent)",
                      }}
                      initial={false}
                      animate={{ scaleY: stage.state === "done" ? 1 : 0 }}
                      transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                    />
                  </span>
                )}
              </div>

              <div style={{ paddingBottom: last ? 0 : "var(--s4)", minWidth: 0, flex: 1 }}>
                <span
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 6,
                    lineHeight: 1.15,
                  }}
                >
                  <span
                    className="mono"
                    style={{ fontSize: 9.5, color: "var(--ink-quaternary)" }}
                  >
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: stage.state === "active" ? 600 : 460,
                      color: reached ? "var(--ink)" : "var(--ink-quaternary)",
                      letterSpacing: "-0.01em",
                    }}
                  >
                    {stage.label}
                  </span>
                </span>

                {/* Always say what the state is, in words -- colour alone is not
                    an accessible signal, and "not run" must never read as a
                    quiet success. */}
                <span
                  className="mono"
                  title={stage.detail ?? STATE_WORD[stage.state]}
                  style={{
                    display: "block",
                    marginTop: 2,
                    fontSize: 10,
                    color: COLORS[stage.state],
                    overflowWrap: "anywhere",
                  }}
                >
                  {/* The rail is ~150px wide, so a long backend message is
                      clipped to a glance here and shown in full in the main
                      column. The title carries the whole string. */}
                  {stage.detail
                    ? stage.detail.length > 24
                      ? `${stage.detail.slice(0, 24)}…`
                      : stage.detail
                    : STATE_WORD[stage.state]}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
