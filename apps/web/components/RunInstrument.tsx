"use client";

/**
 * Run telemetry as an instrument readout.
 *
 * Large tabular figures on a hairline rule rather than a dashboard tile. Every
 * value comes from the event stream: elapsed is the difference between the
 * first and last backend event timestamps, never a client stopwatch, and a
 * figure that has not been produced yet shows an em dash rather than a zero,
 * because a zero reads as a measurement.
 */

import { motion } from "framer-motion";

import { STAGE_ORDER, type PipelineState, type StageState } from "@/lib/usePipeline";

const GLYPH: Partial<Record<StageState, string>> = { done: "✓", failed: "✕" };

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div className="instrument-value" data-muted={value === "—"}>
        {value}
      </div>
      <div className="instrument-label">{label}</div>
    </div>
  );
}

export function RunInstrument({
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

  const status = state.failure
    ? "Failed"
    : !state.finished
      ? "Running"
      : state.match
        ? "Verified match"
        : "Complete";
  const statusColor = state.failure
    ? "var(--rejected)"
    : !state.finished
      ? "var(--accent)"
      : state.match
        ? "var(--verified)"
        : "var(--ink-secondary)";

  return (
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--s4)",
          flexWrap: "wrap",
          marginBottom: "var(--s4)",
        }}
      >
        <span
          style={{
            fontSize: 15,
            fontWeight: 600,
            letterSpacing: "-0.015em",
            color: statusColor,
          }}
        >
          {status}
        </span>
        <span
          className="mono"
          title={verificationId}
          style={{ fontSize: 11, color: "var(--ink-tertiary)", overflowWrap: "anywhere" }}
        >
          {verificationId}
        </span>
      </div>

      <div className="instrument">
        <Figure label="Elapsed" value={elapsed} />
        <Figure label="Events" value={events.length ? String(events.length) : "—"} />
        <Figure label="Faces" value={state.faces.length ? String(state.faces.length) : "—"} />
        <Figure
          label="Candidates"
          value={state.candidates.length ? String(state.candidates.length) : "—"}
        />
        <Figure label="Compared" value={compared ? String(compared) : "—"} />
        <Figure
          label="Similarity"
          value={
            state.match?.verdict?.similarity != null
              ? state.match.verdict.similarity.toFixed(4)
              : "—"
          }
        />
      </div>

      {/* Eight-stage progression. A node fills only when the backend reports
          that stage done, and a connector only when the stage before it is
          done, so the strip cannot run ahead of the pipeline. */}
      <div className="stepper" aria-hidden>
        <div className="stepper-track">
          {STAGE_ORDER.map((entry, index) => {
            const stage = state.stages[entry.id];
            const previous = index > 0 ? state.stages[STAGE_ORDER[index - 1].id] : null;
            return (
              <div key={entry.id} style={{ display: "contents" }}>
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
          {STAGE_ORDER.map((entry) => (
            <span
              key={entry.id}
              className="stepper-label"
              data-on={state.stages[entry.id].state !== "idle" ? "true" : "false"}
            >
              {entry.label}
            </span>
          ))}
        </div>
      </div>

      {/* The stepper is shorthand; the accessible statement of pipeline
          position lives here, in words. */}
      <p className="visually-hidden" role="status">
        {STAGE_ORDER.map((e) => `${e.label}: ${state.stages[e.id].state}`).join(". ")}
      </p>
    </div>
  );
}
