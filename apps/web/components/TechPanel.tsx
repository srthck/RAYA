"use client";

/**
 * The right rail: what technically happened?
 *
 * Every value here was measured by the backend. Nothing is filled in
 * optimistically, so an empty slot means that step has not happened yet --
 * which is information in itself.
 */

import { Divider, Field } from "@/components/atoms";
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
  const similarity = state.match?.verdict?.similarity;

  return (
    <aside style={{ display: "flex", flexDirection: "column", gap: "var(--s5)" }}>
      <div>
        <p className="label" style={{ marginBottom: "var(--s3)" }}>
          Technical
        </p>
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field
            label="Detector"
            value={config ? `${config.detector.name} ${config.detector.version}` : "—"}
          />
          <Field
            label="Encoder"
            value={
              config
                ? `${config.encoder.name} ${config.encoder.version} · ${config.encoder.dim}d`
                : "—"
            }
          />
          <Field label="Metric" value={config?.metric ?? "cosine"} />
          <Field
            label="Threshold"
            value={config ? config.threshold.toFixed(2) : "—"}
          />
        </div>
      </div>

      <Divider />

      <div>
        <p className="label" style={{ marginBottom: "var(--s3)" }}>
          This run
        </p>
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field
            label="Input SHA-256"
            value={shortHash(state.input?.sha256)}
            title={state.input?.sha256}
          />
          <Field
            label="Dimensions"
            value={
              state.input ? `${state.input.width} × ${state.input.height}` : "—"
            }
          />
          <Field label="Size" value={formatBytes(state.input?.byte_size)} />
          <Field
            label="Faces found"
            value={state.faces.length ? String(state.faces.length) : "—"}
          />
        </div>
      </div>

      <Divider />

      <div>
        <p className="label" style={{ marginBottom: "var(--s3)" }}>
          Search
        </p>
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field label="Provider" value={state.searchProvider ?? "—"} />
          <Field
            label="Results"
            value={state.searchCounts ? String(state.searchCounts.results) : "—"}
          />
          <Field
            label="Social candidates"
            value={
              state.candidates.length
                ? String(state.candidates.filter((c) => c.is_social).length)
                : "—"
            }
          />
          <Field
            label="Compared"
            value={
              state.candidates.filter(
                (c) => c.status === "verified" || c.status === "rejected",
              ).length || "—"
            }
          />
        </div>
      </div>

      <Divider />

      <div>
        <p className="label" style={{ marginBottom: "var(--s3)" }}>
          Result
        </p>
        <div style={{ display: "grid", gap: "var(--s3)" }}>
          <Field
            label="Similarity"
            value={formatSimilarity(similarity)}
            tone={
              similarity == null
                ? undefined
                : similarity >= (config?.threshold ?? 0.4)
                  ? "verified"
                  : "rejected"
            }
          />
          <Field
            label="Evidence SHA-256"
            value={shortHash(state.evidence?.sha256)}
            title={state.evidence?.sha256}
          />
          <Field
            label="IPFS CID"
            value={shortHash(state.storage?.cid, 10, 6)}
            title={state.storage?.cid}
            tone={
              state.storage && !state.storage.published ? "pending" : undefined
            }
          />
          <Field
            label="Network"
            value={config?.chain.chain_name ?? "—"}
          />
          <Field
            label="Transaction"
            value={shortHash(state.anchor?.txHash)}
            title={state.anchor?.txHash}
          />
        </div>
      </div>

      {/* Capabilities that are switched off are stated, not hidden -- a
          reviewer should be able to see at a glance what this deployment
          could and could not do. */}
      {config && (!config.search.configured || !config.chain.configured) && (
        <>
          <Divider />
          <div style={{ display: "grid", gap: "var(--s2)" }}>
            <p className="label">Not configured</p>
            {!config.search.configured && (
              <p className="mono" style={{ fontSize: 11, color: "var(--pending)" }}>
                Reverse image search — set SERPAPI_KEY
              </p>
            )}
            {!config.chain.configured && (
              <p className="mono" style={{ fontSize: 11, color: "var(--pending)" }}>
                Blockchain anchor — set CONTRACT_ADDRESS
              </p>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
