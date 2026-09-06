"use client";

/**
 * The left rail: where are we?
 *
 * Each node reflects a stage the backend reported. A stage only becomes active
 * when its event arrives, and `skipped` is a distinct state from `failed` --
 * an unanchored run did not fail, it produced a weaker result, and the rail
 * says so.
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

function Marker({ state }: { state: StageState }) {
  const color = COLORS[state];

  if (state === "active") {
    return (
      <motion.span
        aria-hidden
        style={{
          width: 9,
          height: 9,
          borderRadius: "50%",
          background: color,
          display: "block",
        }}
        animate={{ scale: [1, 1.35, 1], opacity: [1, 0.55, 1] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  return (
    <span
      aria-hidden
      style={{
        width: 9,
        height: 9,
        borderRadius: "50%",
        display: "block",
        background: state === "idle" ? "transparent" : color,
        border: state === "idle" ? `1.5px solid ${color}` : `1.5px solid ${color}`,
      }}
    />
  );
}

export function JourneyRail({ state }: { state: PipelineState }) {
  return (
    <nav aria-label="Verification stages" style={{ display: "flex", flexDirection: "column" }}>
      <p className="label" style={{ marginBottom: "var(--s4)" }}>
        Journey
      </p>

      <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {STAGE_ORDER.map((entry, index) => {
          const stage = state.stages[entry.id];
          const last = index === STAGE_ORDER.length - 1;

          return (
            <li key={entry.id} style={{ display: "flex", gap: "var(--s3)" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <Marker state={stage.state} />
                {!last && (
                  <span
                    aria-hidden
                    style={{
                      width: 1,
                      flex: 1,
                      minHeight: 34,
                      background:
                        stage.state === "done" ? "var(--verified)" : "var(--line)",
                      opacity: stage.state === "done" ? 0.45 : 1,
                      transition: "background var(--dur) var(--ease)",
                    }}
                  />
                )}
              </div>

              <div style={{ paddingBottom: last ? 0 : "var(--s4)", minWidth: 0, flex: 1 }}>
                <span
                  style={{
                    fontSize: 13.5,
                    fontWeight: stage.state === "active" ? 600 : 460,
                    color:
                      stage.state === "idle" ? "var(--ink-quaternary)" : "var(--ink)",
                    letterSpacing: "-0.01em",
                    display: "block",
                    lineHeight: 1.1,
                  }}
                >
                  {stage.label}
                </span>
                {stage.detail && (
                  <span
                    className="mono"
                    style={{
                      color: COLORS[stage.state],
                      fontSize: 11,
                      display: "block",
                      marginTop: 3,
                      wordBreak: "break-word",
                    }}
                  >
                    {stage.detail.length > 64
                      ? `${stage.detail.slice(0, 64)}…`
                      : stage.detail}
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
