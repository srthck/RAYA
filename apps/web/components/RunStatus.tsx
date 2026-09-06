"use client";

/**
 * Run status: the live state of one verification, at a glance.
 *
 * Every figure is read from the event stream. Elapsed is the difference
 * between the first and last backend event timestamps, so it measures what the
 * pipeline took rather than how long the browser has been open. Counts that
 * have not been produced yet render as an em dash rather than a zero, because
 * a zero reads as a measurement.
 *
 * The stepper is a compact echo of the Journey rail. A node fills only when
 * the backend reports that stage done, and a connector fills only when the
 * stage before it is done -- so the strip can never run ahead of the pipeline.
 */

import { motion } from "framer-motion";

import { Pill } from "@/components/atoms";
import { STAGE_ORDER, type PipelineState, type StageState } from "@/lib/usePipeline";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <span
        className="mono"
        style={{
          fontSize: 15,
          color: "var(--ink)",
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "-0.02em",
        }}
      >
        {value}
      </span>
      <span className="label" style={{ fontSize: 9.5 }}>
        {label}
      </span>
    </div>
  );
}

const GLYPH: Partial<Record<StageState, string>> = {
  done: "✓",
  failed: "✕",
};

export function RunStatus({
  state,
  verificationId,
}: {
  state: PipelineState;
  verificationId: string;
}) {
  const events = state.events;
  const first = events[0]?.at;
  const last = events[events.length - 1]?.at;
  const elapsed =
    first != null && last != null && last >= first ? `${(last - first).toFixed(2)}s` : "—";

  const compared = state.candidates.filter(
    (c) => c.status === "verified" || c.status === "rejected",
  ).length;

  const failed = Boolean(state.failure);
  const tone = failed
    ? ("rejected" as const)
    : !state.finished
      ? ("pending" as const)
      : state.match
        ? ("verified" as const)
        : ("neutral" as const);
  const statusWord = failed
    ? "Failed"
    : !state.finished
      ? "Processing"
      : state.match
        ? "Verified match"
        : "Complete";

  return (
    <section className="panel" aria-label="Run status">
      <div className="panel-head">
        <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)" }}>
          <h2 className="panel-title">Run status</h2>
          <Pill tone={tone}>{statusWord}</Pill>
        </div>
        <span
          className="mono"
          title={verificationId}
          style={{ fontSize: 11, color: "var(--ink-tertiary)", overflowWrap: "anywhere" }}
        >
          {verificationId}
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(74px, 1fr))",
          gap: "var(--s4)",
          paddingBottom: "var(--s5)",
        }}
      >
        <Stat label="Elapsed" value={elapsed} />
        <Stat label="Events" value={events.length ? String(events.length) : "—"} />
        <Stat label="Faces" value={state.faces.length ? String(state.faces.length) : "—"} />
        <Stat
          label="Candidates"
          value={state.candidates.length ? String(state.candidates.length) : "—"}
        />
        <Stat label="Compared" value={compared ? String(compared) : "—"} />
      </div>

      {/* ---- stepper ------------------------------------------------------ */}
      <div className="stepper" aria-hidden>
        <div className="stepper-track">
          {STAGE_ORDER.map((entry, index) => {
            const stage = state.stages[entry.id];
            const previous = index > 0 ? state.stages[STAGE_ORDER[index - 1].id] : null;
            return (
              <div
                key={entry.id}
                style={{ display: "contents" }}
              >
                {index > 0 && (
                  <motion.span
                    className="stepper-link"
                    data-filled={previous?.state === "done" ? "true" : "false"}
                    initial={false}
                  />
                )}
                <span className="stepper-node" data-state={stage.state}>
                  {GLYPH[stage.state] ?? ""}
                </span>
              </div>
            );
          })}
        </div>

        <div className="stepper-labels">
          {STAGE_ORDER.map((entry) => {
            const stage = state.stages[entry.id];
            return (
              <span
                key={entry.id}
                className="stepper-label"
                data-on={stage.state !== "idle" ? "true" : "false"}
              >
                {entry.label}
              </span>
            );
          })}
        </div>
      </div>

      {/* The stepper is decorative shorthand; the accessible statement of where
          the run is lives here, in words. */}
      <p className="visually-hidden" role="status">
        {STAGE_ORDER.map((e) => `${e.label}: ${state.stages[e.id].state}`).join(". ")}
      </p>
    </section>
  );
}
