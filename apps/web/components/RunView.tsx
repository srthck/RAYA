"use client";

/**
 * One verification, as an editorial document.
 *
 * Shared by `/verify` (live SSE) and `/replay/[id]` (the persisted event log).
 * Both drive the identical reducer, so there is one UI rather than a live view
 * and a separate replay view -- a replay that looked different from the run it
 * records would be worth very little.
 *
 * Composition, top to bottom, is the argument the product makes:
 *
 *   instrumentation   where the run is
 *   input evidence    what is being examined
 *   discovery         what the search proposed
 *   verification      what RAYA independently decided        <- the climax
 *   preservation      what was hashed, stored and anchored
 *   provenance        which models produced the number
 *
 * Only two things are boxed: the input evidence sheet and the verification
 * result, because those are the artifacts. Everything else is a titled band on
 * a hairline, so the page reads as a document rather than a grid of cards.
 */

import Link from "next/link";

import { CandidateWall } from "@/components/CandidateWall";
import { InputEvidence } from "@/components/InputEvidence";
import { LineageStrip } from "@/components/LineageStrip";
import { RunInstrument } from "@/components/RunInstrument";
import { TechPanel } from "@/components/TechPanel";
import { VerificationResult } from "@/components/VerificationResult";
import type { RayaConfig, UploadResult } from "@/lib/types";
import type { PipelineState } from "@/lib/usePipeline";

/** A designed state block. Never a raw error string. */
function StateBlock({
  title,
  body,
  aside,
  tone = "neutral",
}: {
  title: string;
  body: string;
  aside?: string;
  tone?: "neutral" | "pending" | "rejected";
}) {
  return (
    <div className="state-block" data-tone={tone}>
      <p className="state-title">{title}</p>
      <p className="state-body">{body}</p>
      {aside && <p className="state-aside">{aside}</p>}
    </div>
  );
}

/**
 * Turn whatever the discovery stage actually did into a designed state.
 *
 * The backend's message is shown as the reason, but it is framed rather than
 * dumped: a heading that names the state, one plain sentence, and -- when
 * search could not run -- the assurance that nothing was invented to fill the
 * gap, which is the whole point.
 */
function DiscoveryState({ state }: { state: PipelineState }) {
  const discover = state.stages.discover?.state;
  const warning = state.warnings.find(
    (w) => w.stage === "search" || w.stage === "search_prepare",
  );
  const reason = warning?.message ?? state.failure?.message;

  if (discover === "failed") {
    return (
      <StateBlock
        tone="rejected"
        title="Search unavailable"
        body={reason ?? "The reverse image search could not be completed."}
        aside="No candidates were fabricated. RAYA performs a real search or none at all."
      />
    );
  }

  if (discover === "skipped") {
    return (
      <StateBlock
        tone="pending"
        title="Search not configured"
        body={
          reason ??
          "No reverse image search provider is configured for this deployment."
        }
        aside="No candidates were fabricated. RAYA performs a real search or none at all."
      />
    );
  }

  if (discover === "active") {
    return (
      <StateBlock
        title="Discovering sources"
        body="Searching the public web for images that resemble the input."
      />
    );
  }

  if (state.searchCounts && state.candidates.length === 0) {
    return (
      <StateBlock
        title="No results"
        body="The reverse image search returned no results for this image."
        aside="Absence of a result is not evidence that no such source exists."
      />
    );
  }

  return (
    <StateBlock
      title="Waiting"
      body="Discovery begins once the face has been detected and encoded."
    />
  );
}

export function RunView({
  state,
  verificationId,
  config,
  threshold,
  upload,
  previewUrl,
  fileName,
}: {
  state: PipelineState;
  verificationId: string;
  config: RayaConfig | null;
  threshold: number;
  /** Present only for a live run, where the browser still holds the file. */
  upload?: UploadResult | null;
  previewUrl?: string | null;
  fileName?: string | null;
}) {
  const hasCandidates = state.candidates.length > 0;
  const scored = state.candidates.some(
    (c) => c.status === "verified" || c.status === "rejected",
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--s7)" }}>
      {/* ---- where the run is ------------------------------------------- */}
      <section className="section">
        <RunInstrument state={state} verificationId={verificationId} />
      </section>

      {/* ---- what is being examined ------------------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="section-title">Input evidence</h2>
        </div>
        <div className="sheet">
          <InputEvidence
            state={state}
            upload={upload ?? null}
            previewUrl={previewUrl ?? null}
            fileName={fileName ?? null}
          />
        </div>
      </section>

      {/* ---- what the search proposed ----------------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="section-title">Discovery</h2>
          {hasCandidates && (
            <p className="section-note">
              {state.candidates.filter((c) => c.is_social).length} social ·{" "}
              {state.candidates.filter((c) => !c.is_social).length} filtered out
            </p>
          )}
        </div>

        {hasCandidates ? (
          <CandidateWall
            candidates={state.candidates}
            threshold={threshold}
            evaluating={state.evaluating}
            matchId={state.match?.id}
            verificationId={verificationId}
            focusMatch={Boolean(state.match) && state.finished}
          />
        ) : (
          <DiscoveryState state={state} />
        )}
      </section>

      {/* ---- what RAYA independently decided ---------------------------- */}
      {scored && (
        <section className="section">
          <div className="section-head">
            <h2 className="section-title">Independent verification</h2>
            <p className="section-note">
              RAYA re-downloaded the source and compared it with its own models
            </p>
          </div>
          <VerificationResult
            state={state}
            verificationId={verificationId}
            threshold={threshold}
          />
        </section>
      )}

      {/* ---- what was preserved ----------------------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="section-title">Chain of custody</h2>
          {state.evidence && (
            <Link
              href={`/evidence/${verificationId}`}
              className="section-note"
              style={{ color: "var(--accent)" }}
            >
              Full evidence record →
            </Link>
          )}
        </div>
        <LineageStrip state={state} />
      </section>

      {/* ---- which models produced the number --------------------------- */}
      <section className="section">
        <div className="section-head">
          <h2 className="section-title">Model provenance</h2>
          <p className="section-note">
            The exact weight files behind every score, so it is reproducible
          </p>
        </div>
        <TechPanel state={state} config={config} />
      </section>
    </div>
  );
}
