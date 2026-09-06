"use client";

/**
 * Replay a stored verification.
 *
 * This re-emits the event log the backend actually wrote, at its original
 * pacing, through the same reducer that drives the live workspace. It is a
 * recording, not a re-enactment: nothing here can show a stage the original run
 * did not reach.
 */

import { use, useState } from "react";
import Link from "next/link";

import { CandidateWall } from "@/components/CandidateWall";
import { JourneyRail } from "@/components/JourneyRail";
import { Nav } from "@/components/Nav";
import { Pill } from "@/components/atoms";
import { usePipeline } from "@/lib/usePipeline";

const SPEEDS = [1, 2, 4];

export default function ReplayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [speed, setSpeed] = useState(2);
  const [runId, setRunId] = useState<string | null>(id);

  const { state } = usePipeline(runId, { replay: true, speed });

  const restart = () => {
    setRunId(null);
    // Remounting the EventSource is what restarts the replay.
    setTimeout(() => setRunId(id), 40);
  };

  return (
    <main className="shell" style={{ paddingBottom: "var(--s9)" }}>
      <Nav />

      <div style={{ paddingTop: "var(--s6)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)", flexWrap: "wrap" }}>
          <Pill tone="neutral">Replay</Pill>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-tertiary)" }}>
            {id}
          </span>
        </div>

        <h1 className="h1" style={{ marginTop: "var(--s4)", maxWidth: 620 }}>
          Replaying the recorded run.
        </h1>
        <p className="body" style={{ marginTop: "var(--s3)", maxWidth: 560, fontSize: 14 }}>
          These are the events the pipeline emitted during the original
          verification, replayed in order at their real relative timings.
        </p>

        <div style={{ display: "flex", gap: "var(--s2)", marginTop: "var(--s5)", flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={restart}>
            Restart
          </button>
          <span className="label" style={{ marginLeft: "var(--s2)" }}>
            Speed
          </span>
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setSpeed(s);
                restart();
              }}
              style={{
                borderColor: speed === s ? "var(--ink)" : "var(--line-strong)",
                color: speed === s ? "var(--ink)" : "var(--ink-tertiary)",
              }}
            >
              {s}×
            </button>
          ))}
          <Link href={`/evidence/${id}`} className="btn btn-ghost btn-sm">
            View evidence
          </Link>
        </div>

        <div className="replay-grid" style={{ marginTop: "var(--s7)" }}>
          <div style={{ position: "sticky", top: "var(--s5)" }}>
            <JourneyRail state={state} />
          </div>

          <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--s5)" }}>
            <div style={{ display: "flex", gap: "var(--s4)", flexWrap: "wrap" }}>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-tertiary)" }}>
                {state.events.length} events replayed
              </span>
              {state.finished && (
                <span className="mono" style={{ fontSize: 11.5, color: "var(--verified)" }}>
                  replay complete
                </span>
              )}
            </div>

            {state.candidates.length > 0 && (
              <CandidateWall
                candidates={state.candidates}
                threshold={0.4}
                evaluating={state.evaluating}
                matchId={state.match?.id}
                verificationId={id}
                focusMatch={Boolean(state.match) && state.finished}
              />
            )}

            {/* The raw event log, so the replay can be checked against it. */}
            <details>
              <summary
                style={{ cursor: "pointer", fontSize: 12.5, color: "var(--ink-tertiary)" }}
              >
                Event log
              </summary>
              <div
                className="scroll-y mono"
                style={{
                  marginTop: "var(--s3)",
                  maxHeight: 320,
                  padding: "var(--s3)",
                  background: "var(--bg-sunken)",
                  border: "1px solid var(--line)",
                  borderRadius: "var(--radius)",
                  fontSize: 11,
                  lineHeight: 1.8,
                }}
              >
                {state.events.map((event) => (
                  <div key={event.seq} style={{ display: "flex", gap: "var(--s3)" }}>
                    <span style={{ color: "var(--ink-quaternary)", width: 28 }}>
                      {String(event.seq).padStart(3, "0")}
                    </span>
                    <span style={{ color: "var(--ink-secondary)" }}>{event.type}</span>
                  </div>
                ))}
              </div>
            </details>
          </div>
        </div>
      </div>

    </main>
  );
}
