"use client";

/**
 * The chain of custody, as a horizontal strip.
 *
 * Answers "where did this result come from?" at a glance: the original input,
 * the bounded derivative that was actually sent outward, the provider, the
 * candidates, the independent comparison, and the preservation chain.
 *
 * Each step's state is derived from real pipeline state -- a step is `done`
 * only when the artifact it names actually exists. Nothing here advances on a
 * timer, and the strip cannot show a stage the backend did not reach.
 */

import type { PipelineState } from "@/lib/usePipeline";

type StepState = "idle" | "active" | "done";

interface Step {
  key: string;
  caption: string;
  glyph: string;
  state: StepState;
  detail?: string;
}

function buildSteps(state: PipelineState): Step[] {
  const stage = (id: keyof PipelineState["stages"]) => state.stages[id]?.state;
  const done = (v: boolean): StepState => (v ? "done" : "idle");

  return [
    {
      key: "input",
      caption: "Input",
      glyph: "IN",
      state: done(Boolean(state.input)),
      detail: state.input?.sha256,
    },
    {
      key: "copy",
      caption: "Search copy",
      glyph: "SC",
      state: done(Boolean(state.searchCopy)),
      detail: state.searchCopy?.sha256,
    },
    {
      key: "provider",
      caption: "SerpApi",
      glyph: "SA",
      state:
        stage("discover") === "done"
          ? "done"
          : stage("discover") === "active"
            ? "active"
            : "idle",
    },
    {
      key: "lens",
      caption: "Lens",
      glyph: "GL",
      state: done(Boolean(state.searchCounts)),
    },
    {
      key: "candidates",
      caption: "Candidates",
      glyph: String(state.candidates.length || ""),
      state: done(state.candidates.length > 0),
    },
    {
      key: "source",
      caption: "Source",
      glyph: "SRC",
      state: done(Boolean(state.match?.image_sha256)),
      detail: state.match?.image_sha256 ?? undefined,
    },
    {
      key: "sface",
      caption: "SFace",
      glyph: "SF",
      state:
        stage("verify") === "done"
          ? "done"
          : stage("verify") === "active"
            ? "active"
            : "idle",
    },
    {
      key: "evidence",
      caption: "Evidence",
      glyph: "EV",
      state: done(Boolean(state.evidence)),
      detail: state.evidence?.sha256,
    },
    {
      key: "ipfs",
      caption: "IPFS",
      glyph: "IP",
      state: done(Boolean(state.storage?.published)),
      detail: state.storage?.cid,
    },
    {
      key: "core",
      caption: "Core",
      glyph: "CO",
      state: done(Boolean(state.anchor)),
      detail: state.anchor?.txHash,
    },
    {
      key: "integrity",
      caption: "Integrity",
      glyph: "IX",
      state: done(Boolean(state.readback?.matches)),
    },
  ];
}

export function LineageStrip({ state }: { state: PipelineState }) {
  const steps = buildSteps(state);
  const reached = steps.filter((s) => s.state === "done").length;

  return (
    <section className="panel" aria-label="Search lineage">
      <div className="panel-head">
        <h2 className="panel-title">Search lineage</h2>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-tertiary)" }}>
          {reached} of {steps.length} complete
        </span>
      </div>

      <div className="lineage-strip">
        {steps.map((step, index) => (
          <div key={step.key} style={{ display: "contents" }}>
            {index > 0 && (
              <span className="lineage-arrow" aria-hidden>
                →
              </span>
            )}
            <div
              className="lineage-step"
              data-state={step.state}
              title={step.detail ? `${step.caption}: ${step.detail}` : step.caption}
            >
              <span className="lineage-dot">{step.glyph}</span>
              <span className="lineage-caption">{step.caption}</span>
            </div>
          </div>
        ))}
      </div>

      <p
        className="body"
        style={{ marginTop: "var(--s3)", fontSize: 11.5, color: "var(--ink-tertiary)" }}
      >
        The original input is hashed locally and never published. Only the
        bounded search copy is sent to the provider.
      </p>
    </section>
  );
}
