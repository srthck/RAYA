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
  active: "var(--ink)",
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
      <motion.span
        style={{ display: "block" }}
        animate={{ opacity: [1, 0.4, 1] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
      >
        {glyph}
      </motion.span>
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
                      width: 1,
                      flex: 1,
                      minHeight: 28,
                      background:
                        stage.state === "done" ? "var(--verified)" : "var(--line)",
                      opacity: stage.state === "done" ? 0.4 : 1,
                      transition: "background var(--dur) var(--ease)",
                    }}
                  />
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
