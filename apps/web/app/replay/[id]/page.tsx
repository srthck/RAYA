"use client";

/**
 * Replay a stored verification.
 *
 * Re-emits the event log the backend actually wrote, at its original pacing,
 * through the same reducer and the same `RunView` as the live workspace. It is
 * a recording, not a re-enactment: nothing here can show a stage the original
 * run did not reach, and a replay that looked different from the run it
 * records would be worth very little.
 */

import { use, useEffect, useState } from "react";
import Link from "next/link";

import { JourneyRail } from "@/components/JourneyRail";
import { Nav } from "@/components/Nav";
import { RunView } from "@/components/RunView";
import { Pill } from "@/components/atoms";
import { api } from "@/lib/api";
import type { RayaConfig } from "@/lib/types";
import { usePipeline } from "@/lib/usePipeline";

const SPEEDS = [1, 2, 4];

export default function ReplayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [speed, setSpeed] = useState(2);
  const [runId, setRunId] = useState<string | null>(id);
  const [config, setConfig] = useState<RayaConfig | null>(null);

  const { state } = usePipeline(runId, { replay: true, speed });

  useEffect(() => {
    api.config().then(setConfig).catch(() => undefined);
  }, []);

  const restart = () => {
    setRunId(null);
    // Remounting the EventSource is what restarts the replay.
    setTimeout(() => setRunId(id), 40);
  };

  return (
    <main className="shell" style={{ paddingBottom: "var(--s9)" }}>
      <Nav />

      <div className="workspace">
        <div className="workspace-rail">
          <div className="rail-surface">
            <JourneyRail state={state} />
          </div>
        </div>

        <div className="workspace-main">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--s3)",
              flexWrap: "wrap",
              paddingTop: "var(--s4)",
            }}
          >
            <Pill tone="neutral">Replay</Pill>
            <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-tertiary)" }}>
              {state.events.length} events
              {state.finished ? " · complete" : ""}
            </span>

            <span style={{ flex: 1 }} />

            <button type="button" className="btn btn-ghost btn-sm" onClick={restart}>
              Restart
            </button>
            {SPEEDS.map((s) => (
              <button
                key={s}
                type="button"
                className="btn btn-ghost btn-sm"
                aria-pressed={speed === s}
                onClick={() => {
                  setSpeed(s);
                  restart();
                }}
                style={{
                  borderColor: speed === s ? "var(--accent)" : "var(--line-strong)",
                  color: speed === s ? "var(--accent)" : "var(--ink-tertiary)",
                }}
              >
                {s}×
              </button>
            ))}
            <Link href={`/evidence/${id}`} className="btn btn-ghost btn-sm">
              Evidence
            </Link>
          </div>

          <p className="body" style={{ fontSize: 13, maxWidth: "62ch" }}>
            These are the events the pipeline emitted during the original
            verification, replayed in order at their real relative timings.
          </p>

          <RunView
            state={state}
            verificationId={id}
            config={config}
            threshold={config?.threshold ?? 0.4}
            previewUrl={`/api/v1/verifications/${id}/assets/input-face.jpg`}
          />
        </div>
      </div>
    </main>
  );
}
