"use client";

/**
 * The verification workspace.
 *
 * Three columns answer three questions at all times: where are we (left), what
 * is happening (centre), and what technically happened (right). Everything in
 * all three is driven by the SSE event stream -- see `lib/usePipeline.ts`.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";

import { CandidateWall } from "@/components/CandidateWall";
import { JourneyRail } from "@/components/JourneyRail";
import { MatchReveal } from "@/components/MatchReveal";
import { Nav } from "@/components/Nav";
import { TechPanel } from "@/components/TechPanel";
import { InputEvidence } from "@/components/InputEvidence";
import { RunTelemetry } from "@/components/RunTelemetry";
import { UploadZone } from "@/components/UploadZone";
import { Empty, Pill } from "@/components/atoms";
import { api } from "@/lib/api";
import type { RayaConfig, UploadResult } from "@/lib/types";
import { usePipeline } from "@/lib/usePipeline";

export default function VerifyPage() {
  const [verificationId, setVerificationId] = useState<string | null>(null);
  const [inputContext, setInputContext] = useState<{
    upload: UploadResult;
    previewUrl: string | null;
    fileName: string | null;
  } | null>(null);
  const [config, setConfig] = useState<RayaConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const { state } = usePipeline(verificationId);

  useEffect(() => {
    api
      .config()
      .then(setConfig)
      .catch(() =>
        setConfigError(
          "Could not reach the RAYA API. Start it with: uvicorn raya_api.main:app --port 8000",
        ),
      );
  }, []);

  const threshold = config?.threshold ?? 0.4;
  const searchReady = config?.search.configured ?? true;

  return (
    <main className="shell" style={{ paddingBottom: "var(--s9)" }}>
      <Nav />

      <div className="workspace">
        {/* ---- left: where are we -------------------------------------- */}
        <div className="workspace-rail">
          <JourneyRail state={state} />

          {verificationId && (
            <p
              className="mono"
              title={verificationId}
              style={{
                marginTop: "var(--s5)",
                fontSize: 10,
                lineHeight: 1.4,
                color: "var(--ink-quaternary)",
                overflowWrap: "anywhere",
              }}
            >
              {verificationId}
            </p>
          )}
        </div>

        {/* ---- centre: what is happening ------------------------------- */}
        <div className="workspace-main">
          {configError && (
            <div className="card" style={{ padding: "var(--s4)", borderColor: "var(--rejected)" }}>
              <p style={{ margin: 0, fontSize: 13.5, color: "var(--rejected)" }}>{configError}</p>
            </div>
          )}

          {!searchReady && !verificationId && (
            <div className="card" style={{ padding: "var(--s4)", borderColor: "var(--pending)" }}>
              <p style={{ margin: 0, fontSize: 13.5, fontWeight: 560 }}>
                Reverse image search is not configured.
              </p>
              <p className="body" style={{ marginTop: 4, fontSize: 13 }}>
                Set <code className="mono">SERPAPI_KEY</code> in <code className="mono">.env</code>{" "}
                to run a real search. RAYA will not fabricate candidates, so a run
                will stop at the search stage and say so.
              </p>
            </div>
          )}

          {!verificationId && (
            <>
              <div>
                <h1 className="h1" style={{ maxWidth: 560 }}>
                  Verify an image.
                </h1>
                <p className="lede" style={{ marginTop: "var(--s3)", maxWidth: 520 }}>
                  RAYA detects the face, searches the public web, and independently
                  verifies each candidate before preserving what it found.
                </p>
              </div>
              <UploadZone
                onStart={(id, context) => {
                  setInputContext(context);
                  setVerificationId(id);
                }}
              />
            </>
          )}

          {verificationId && (
            <>
              {/* Live telemetry, read entirely from the event stream. */}
              <RunTelemetry state={state} verificationId={verificationId} />

              {inputContext && (
                <InputEvidence
                  upload={inputContext.upload}
                  previewUrl={inputContext.previewUrl}
                  fileName={inputContext.fileName}
                  status={
                    state.failure
                      ? "FAILED"
                      : state.stages.face?.state === "done"
                        ? "COMPLETE"
                        : "RUNNING"
                  }
                />
              )}

              <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)", flexWrap: "wrap" }}>
                {!state.finished ? (
                  <Pill tone="pending">Running</Pill>
                ) : state.match ? (
                  <Pill tone="verified">Verified visual match</Pill>
                ) : (
                  <Pill tone="neutral">Complete</Pill>
                )}
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setVerificationId(null);
                    setInputContext(null);
                  }}
                >
                  New verification
                </button>
              </div>

              {/* Failure and degraded states, stated plainly */}
              <AnimatePresence>
                {state.failure && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="card"
                    style={{ padding: "var(--s5)", borderColor: "var(--rejected)" }}
                  >
                    <p className="h3">{failureHeadline(state.failure.code)}</p>
                    <p className="body" style={{ marginTop: "var(--s2)", fontSize: 13.5 }}>
                      {state.failure.message}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              {state.warnings.length > 0 && (
                <div style={{ display: "grid", gap: "var(--s2)" }}>
                  {state.warnings.map((warning, i) => (
                    <p
                      key={i}
                      style={{ margin: 0, fontSize: 12.5, color: "var(--pending)" }}
                    >
                      {warning.stage}: {warning.message}
                    </p>
                  ))}
                </div>
              )}

              {/* The match */}
              {state.match && (
                <MatchReveal
                  state={state}
                  verificationId={verificationId}
                  threshold={threshold}
                />
              )}

              {/* No match, but the pipeline ran */}
              {state.finished && !state.match && !state.failure && state.searchCounts && (
                <div className="card" style={{ padding: "var(--s5)" }}>
                  <p className="h3">No verified public social source found.</p>
                  <p className="body" style={{ marginTop: "var(--s2)", fontSize: 13.5 }}>
                    {state.candidates.filter((c) => c.is_social).length} social
                    candidate(s) were evaluated and none cleared the{" "}
                    {threshold.toFixed(2)} similarity threshold. Absence of a match
                    is not evidence that no such source exists.
                  </p>
                  <Link
                    href={`/evidence/${verificationId}`}
                    className="btn btn-ghost btn-sm"
                    style={{ marginTop: "var(--s4)" }}
                  >
                    View evidence
                  </Link>
                </div>
              )}

              {/* Candidates */}
              {state.candidates.length > 0 && (
                <CandidateWall
                  candidates={state.candidates}
                  threshold={threshold}
                  evaluating={state.evaluating}
                  matchId={state.match?.id}
                  verificationId={verificationId}
                  focusMatch={Boolean(state.match) && state.finished}
                />
              )}

              {state.candidates.length === 0 && !state.failure && !state.finished && (
                <Empty>Waiting for the search provider…</Empty>
              )}
            </>
          )}

          {/* Technical lives in the main column, in normal flow, beneath the
              work it describes. It is not a floating sidebar. */}
          <TechPanel state={state} config={config} />
        </div>

      </div>
    </main>
  );
}

function failureHeadline(code: string): string {
  const map: Record<string, string> = {
    no_face_detected: "No usable face detected",
    multiple_faces: "Multiple faces detected",
    face_too_small: "Face too small to compare reliably",
    invalid_image: "Image could not be read",
    image_too_large: "Image is too large",
    unsupported_format: "Unsupported image format",
    search_provider_not_configured: "Reverse image search is not configured",
    search_provider_error: "The search provider could not be reached",
    no_public_url: "The input image could not be made searchable",
  };
  return map[code] ?? "Verification could not complete";
}
