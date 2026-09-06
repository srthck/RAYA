"use client";

/**
 * The verification workspace.
 *
 * Two columns: where the run is (Journey), and what is happening (main).
 * Everything in both is driven by the SSE event stream -- see
 * `lib/usePipeline.ts`. The run itself is rendered by `RunView`, which is
 * shared with `/replay/[id]` so a recording looks exactly like the run it
 * records.
 */

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { JourneyRail } from "@/components/JourneyRail";
import { Nav } from "@/components/Nav";
import { RunView } from "@/components/RunView";
import { TechPanel } from "@/components/TechPanel";
import { UploadZone } from "@/components/UploadZone";
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
          <div className="rail-surface">
            <JourneyRail state={state} />
          </div>
        </div>

        {/* ---- centre: what is happening ------------------------------- */}
        <div className="workspace-main">
          {configError && (
            <div className="state-block" data-tone="rejected">
              <p className="state-title">API unreachable</p>
              <p className="state-body">{configError}</p>
            </div>
          )}

          {!verificationId && (
            <>
              <div style={{ paddingTop: "var(--s4)" }}>
                <h1 className="h1" style={{ maxWidth: 600 }}>
                  Verify an image.
                </h1>
                <p className="lede" style={{ marginTop: "var(--s4)", maxWidth: 540 }}>
                  RAYA detects the face, searches the public web, and
                  independently verifies each candidate before preserving what it
                  found.
                </p>
              </div>

              {!searchReady && (
                <div className="state-block" data-tone="pending">
                  <p className="state-title">Search not configured</p>
                  <p className="state-body">
                    No reverse image search provider is configured, so a run will
                    stop after encoding the face.
                  </p>
                  <p className="state-aside">
                    No candidates will be fabricated. RAYA performs a real search
                    or none at all.
                  </p>
                </div>
              )}

              <UploadZone
                onStart={(id, context) => {
                  setInputContext(context);
                  setVerificationId(id);
                }}
              />

              {/* Before a run there is no instrument to read, so the models
                  and thresholds this deployment will use are shown instead. */}
              <section className="section" style={{ marginTop: "var(--s5)" }}>
                <div className="section-head">
                  <h2 className="section-title">Model provenance</h2>
                  <p className="section-note">
                    The exact weight files behind every score
                  </p>
                </div>
                <TechPanel state={state} config={config} />
              </section>
            </>
          )}

          {verificationId && (
            <>
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  paddingTop: "var(--s4)",
                }}
              >
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

              <AnimatePresence>
                {state.failure && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="state-block"
                    data-tone="rejected"
                  >
                    <p className="state-title">{failureHeadline(state.failure.code)}</p>
                    <p className="state-body">{state.failure.message}</p>
                  </motion.div>
                )}
              </AnimatePresence>

              <RunView
                state={state}
                verificationId={verificationId}
                config={config}
                threshold={threshold}
                upload={inputContext?.upload ?? null}
                previewUrl={inputContext?.previewUrl ?? null}
                fileName={inputContext?.fileName ?? null}
              />
            </>
          )}
        </div>
      </div>

      <footer
        style={{
          marginTop: "var(--s9)",
          paddingTop: "var(--s5)",
          borderTop: "1px solid var(--line)",
          display: "flex",
          justifyContent: "space-between",
          gap: "var(--s4)",
          flexWrap: "wrap",
        }}
      >
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-tertiary)" }}>
          RAYA · Visual evidence verification
        </span>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-tertiary)" }}>
          A similarity score is not an identity.
        </span>
      </footer>
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
