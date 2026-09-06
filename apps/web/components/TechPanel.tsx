"use client";

/**
 * The right rail: what technically happened?
 *
 * Every stage leads with a semantic status word rather than an em dash. The
 * distinction is the point: NOT RUN, NOT CREATED, WAITING and UNAVAILABLE mean
 * four different things, and a reviewer needs to tell "this deployment has no
 * chain configured" apart from "the anchor failed" apart from "the anchor has
 * not happened yet". A blank would collapse all three.
 *
 * Nothing here is filled in optimistically: every value comes from an event the
 * backend actually emitted.
 */

import { Divider, Field, StatusBlock, type StatusWord } from "@/components/atoms";
import { formatBytes, formatSimilarity, shortHash } from "@/lib/format";
import type { RayaConfig } from "@/lib/types";
import type { PipelineState } from "@/lib/usePipeline";

export function TechPanel({
  state,
  config,
}: {
  state: PipelineState;
  config: RayaConfig | null;
}) {
  const started = state.events.length > 0;
  const similarity = state.match?.verdict?.similarity;
  const searchConfigured = config?.search.configured ?? false;
  const chainConfigured = config?.chain.configured ?? false;

  // ---- status derivation, from real stage state ---------------------------

  const stage = (id: keyof PipelineState["stages"]) => state.stages[id]?.state;

  const inputStatus: StatusWord = !started
    ? "WAITING"
    : state.input
      ? "COMPLETE"
      : "RUNNING";

  const searchStatus: StatusWord = !searchConfigured
    ? "UNAVAILABLE"
    : !started
      ? "WAITING"
      : stage("discover") === "done"
        ? "COMPLETE"
        : stage("discover") === "failed"
          ? "FAILED"
          : stage("discover") === "active"
            ? "RUNNING"
            : "WAITING";

  const verifyStatus: StatusWord = !started
    ? "WAITING"
    : state.match
      ? "PASS"
      : stage("verify") === "active"
        ? "RUNNING"
        : state.candidates.some((c) => c.status === "rejected")
          ? "REJECTED"
          : "NOT RUN";

  const evidenceStatus: StatusWord = state.evidence ? "COMPLETE" : "NOT CREATED";

  const ipfsStatus: StatusWord = state.storage
    ? state.storage.published
      ? "COMPLETE"
      : "UNAVAILABLE"
    : "NOT CREATED";

  const anchorStatus: StatusWord = !chainConfigured
    ? "UNAVAILABLE"
    : state.anchor
      ? "CONFIRMED"
      : stage("anchor") === "active"
        ? "PENDING"
        : stage("anchor") === "failed"
          ? "FAILED"
          : "NOT RUN";

  const integrityStatus: StatusWord = state.readback
    ? state.readback.matches
      ? "VERIFIED"
      : "MISMATCH"
    : state.anchor
      ? "PENDING"
      : "NOT RUN";

  return (
    <aside style={{ display: "flex", flexDirection: "column", gap: "var(--s5)", minWidth: 0 }}>
      {/* ---- static configuration -------------------------------------- */}
      <div>
        <p className="label" style={{ marginBottom: "var(--s3)" }}>
          Technical
        </p>
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field
            label="Detector"
            value={config ? `${config.detector.name} ${config.detector.version}` : "loading"}
          />
          <Field
            label="Encoder"
            value={
              config
                ? `${config.encoder.name} ${config.encoder.version} · ${config.encoder.dim}d`
                : "loading"
            }
          />
          <Field label="Metric" value={config ? `${config.metric} similarity` : "loading"} />
          <Field label="Threshold" value={config ? config.threshold.toFixed(2) : "loading"} />
        </div>
      </div>

      <Divider />

      {/* ---- 01 input ---------------------------------------------------- */}
      <StatusBlock title="This run" status={inputStatus}>
        {state.input && (
          <div style={{ display: "grid", gap: "var(--s3)" }}>
            <Field
              label="Input SHA-256"
              value={shortHash(state.input.sha256)}
              title={state.input.sha256}
            />
            <Field
              label="Dimensions"
              value={`${state.input.width} × ${state.input.height}`}
            />
            <Field label="Size" value={formatBytes(state.input.byte_size)} />
            <Field
              label="Faces found"
              value={state.faces.length ? String(state.faces.length) : "0"}
            />
          </div>
        )}
      </StatusBlock>

      <Divider />

      {/* ---- 03 discover ------------------------------------------------- */}
      <StatusBlock
        title="Search"
        status={searchStatus}
        reason={
          !searchConfigured
            ? "Search provider credentials are not configured."
            : undefined
        }
      >
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field label="Provider" value={config?.search.display_name ?? "SerpApi"} mono={false} />
          {/* The derivative that actually left the machine -- deliberately
              shown next to, and distinct from, the input hash above. */}
          {state.searchCopy && (
            <>
              <Field
                label="Search copy SHA-256"
                value={shortHash(state.searchCopy.sha256)}
                title={state.searchCopy.sha256}
              />
              <Field
                label="Search copy"
                value={`${state.searchCopy.width} × ${state.searchCopy.height} · ${formatBytes(
                  state.searchCopy.byteSize,
                )}`}
              />
            </>
          )}
          <Field
            label="Results"
            value={state.searchCounts ? String(state.searchCounts.results) : "not run"}
          />
          <Field
            label="Social candidates"
            value={
              state.candidates.length
                ? String(state.candidates.filter((c) => c.is_social).length)
                : "not run"
            }
          />
        </div>
      </StatusBlock>

      <Divider />

      {/* ---- 04 verify --------------------------------------------------- */}
      <StatusBlock title="Verify" status={verifyStatus}>
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field
            label="Compared"
            value={
              state.candidates.filter(
                (c) => c.status === "verified" || c.status === "rejected",
              ).length || "not run"
            }
          />
          <Field
            label="Similarity"
            value={similarity != null ? formatSimilarity(similarity) : "not run"}
            tone={
              similarity == null
                ? undefined
                : similarity >= (config?.threshold ?? 0.4)
                  ? "verified"
                  : "rejected"
            }
          />
        </div>
      </StatusBlock>

      <Divider />

      {/* ---- 05 evidence + IPFS ------------------------------------------ */}
      <StatusBlock title="Evidence" status={evidenceStatus}>
        <Field
          label="Evidence SHA-256"
          value={state.evidence ? shortHash(state.evidence.sha256) : "not created"}
          title={state.evidence?.sha256}
        />
      </StatusBlock>

      <StatusBlock
        title="IPFS"
        status={ipfsStatus}
        reason={
          state.storage && !state.storage.published
            ? "Stored locally with a computed CID; no pinning service configured."
            : undefined
        }
      >
        <Field
          label="CID"
          value={state.storage ? shortHash(state.storage.cid, 10, 6) : "not created"}
          title={state.storage?.cid}
        />
      </StatusBlock>

      <Divider />

      {/* ---- 06/07/08 anchor, read-back, integrity ----------------------- */}
      <StatusBlock
        title="Anchor"
        status={anchorStatus}
        reason={
          !chainConfigured
            ? "No contract address or signing key is configured."
            : undefined
        }
      >
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field label="Network" value={config?.chain.chain_name ?? "Core Testnet2"} mono={false} />
          <Field
            label="Transaction"
            value={state.anchor ? shortHash(state.anchor.txHash) : "not run"}
            title={state.anchor?.txHash}
          />
          <Field
            label="Block"
            value={state.anchor ? `#${state.anchor.blockNumber}` : "not run"}
          />
        </div>
      </StatusBlock>

      <StatusBlock title="Integrity" status={integrityStatus}>
        <Field
          label="Local = on-chain"
          value={
            state.readback
              ? state.readback.matches
                ? "match"
                : "mismatch"
              : "not compared"
          }
          tone={state.readback ? (state.readback.matches ? "verified" : "rejected") : undefined}
        />
      </StatusBlock>
    </aside>
  );
}
