"use client";

/**
 * A compact telemetry strip for the active run.
 *
 * Every figure here is read from the event stream -- there are no derived
 * "scores", no progress percentage and no estimate. Elapsed time is the
 * difference between the first and last backend event timestamps, so it
 * measures what the pipeline actually took rather than how long the browser
 * has had the page open.
 *
 * When a value has not been produced yet it says so, rather than showing a
 * zero that would read as a measurement.
 */

import { motion } from "framer-motion";

import type { PipelineState } from "@/lib/usePipeline";

function Cell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "accent" | "verified" | "muted";
}) {
  const color =
    tone === "accent"
      ? "var(--accent)"
      : tone === "verified"
        ? "var(--verified)"
        : tone === "muted"
          ? "var(--ink-quaternary)"
          : "var(--ink)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
      <span className="label">{label}</span>
      <span
        className="mono"
        style={{
          fontSize: 13,
          color,
          overflowWrap: "anywhere",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </span>
    </div>
  );
}

export function RunTelemetry({
  state,
  verificationId,
}: {
  state: PipelineState;
  verificationId: string;
}) {
  const events = state.events;
  if (events.length === 0) return null;

  // Backend timestamps, not a client-side stopwatch.
  const first = events[0]?.at;
  const last = events[events.length - 1]?.at;
  const elapsed =
    first != null && last != null && last >= first
      ? `${(last - first).toFixed(2)}s`
      : "—";

  const compared = state.candidates.filter(
    (c) => c.status === "verified" || c.status === "rejected",
  ).length;

  const status = state.failure
    ? "FAILED"
    : state.finished
      ? state.match
        ? "MATCH"
        : "COMPLETE"
      : "RUNNING";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="surface"
      aria-label="Run telemetry"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))",
        gap: "var(--s4) var(--s5)",
        padding: "var(--s4) var(--s5)",
      }}
    >
      <Cell label="Run" value={verificationId.replace(/^VER-/, "")} tone="muted" />
      <Cell
        label="Status"
        value={status}
        tone={status === "MATCH" ? "verified" : status === "RUNNING" ? "accent" : undefined}
      />
      <Cell label="Elapsed" value={elapsed} />
      <Cell label="Events" value={String(events.length)} />
      <Cell label="Faces" value={state.faces.length ? String(state.faces.length) : "—"} />
      <Cell
        label="Candidates"
        value={state.candidates.length ? String(state.candidates.length) : "—"}
      />
      <Cell label="Compared" value={compared ? String(compared) : "—"} />
    </motion.div>
  );
}
