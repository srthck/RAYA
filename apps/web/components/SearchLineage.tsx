"use client";

/**
 * Evidence lineage: where did this result actually come from?
 *
 * A provider label alone ("Google Lens") tells a reviewer nothing about
 * provenance. This traces the whole chain of custody, and in particular makes
 * the one distinction that is easy to blur:
 *
 *     the ORIGINAL INPUT is hashed and never leaves the machine
 *     a BOUNDED SEARCH COPY is what goes to the provider
 *
 * Two objects, two digests, both shown. Steps that did not happen are rendered
 * as not-run rather than omitted, so a partial run reads as partial.
 */

import { shortHash } from "@/lib/format";
import type { VerificationResult } from "@/lib/types";

type NodeState = "done" | "skipped" | "failed";

interface LineageNode {
  label: string;
  value?: string | null;
  title?: string;
  state: NodeState;
  note?: string;
}

function buildNodes(result: VerificationResult): LineageNode[] {
  const search = result.search;
  const copy = result.search_copy;
  const match = result.match;
  const meta = (search?.metadata ?? {}) as Record<string, unknown>;

  const nodes: LineageNode[] = [
    {
      label: "Original input",
      value: `${result.input.width} × ${result.input.height} · ${result.input.mime}`,
      state: "done",
      note: "Never re-encoded, never published.",
    },
    {
      label: "Input SHA-256",
      value: shortHash(result.input.sha256, 16, 10),
      title: result.input.sha256,
      state: "done",
      note: "The canonical commitment.",
    },
    {
      label: "Bounded search copy",
      value: copy
        ? `${copy.width} × ${copy.height} · ${(copy.byte_size / 1000).toFixed(0)} KB · q${copy.jpeg_quality}`
        : "not created",
      state: copy ? "done" : "skipped",
      note: copy
        ? "Deterministic derivative — this is what left the machine."
        : undefined,
    },
    {
      label: "Search copy SHA-256",
      value: copy ? shortHash(copy.sha256, 16, 10) : "not created",
      title: copy?.sha256,
      state: copy ? "done" : "skipped",
    },
    {
      label: "Search provider",
      value: search?.provider ?? "not run",
      state: search ? "done" : "skipped",
      note:
        typeof meta.input_method === "string"
          ? meta.input_method === "direct_upload"
            ? "Uploaded directly; no public hosting used."
            : "Fetched by the provider from a public URL."
          : undefined,
    },
    {
      label: "Provider image id",
      value: typeof meta.image_id === "string" ? meta.image_id : "n/a",
      state: typeof meta.image_id === "string" ? "done" : "skipped",
    },
    {
      label: "Candidates discovered",
      value: search ? `${result.counts.results} (${result.counts.social} social)` : "not run",
      state: search ? "done" : "skipped",
    },
    {
      label: "Selected source",
      value: match?.page_url ?? "none verified",
      title: match?.page_url ?? undefined,
      state: match ? "done" : "skipped",
    },
    {
      label: "Source image SHA-256",
      value: match?.image_sha256 ? shortHash(match.image_sha256, 16, 10) : "not retrieved",
      title: match?.image_sha256 ?? undefined,
      state: match?.image_sha256 ? "done" : "skipped",
      note: match?.image_sha256 ? "Independently re-downloaded and hashed." : undefined,
    },
    {
      label: "Independent face comparison",
      value:
        result.similarity != null
          ? `${result.similarity.toFixed(4)} vs threshold ${(match?.verdict?.threshold ?? 0.4).toFixed(2)}`
          : "not run",
      state: result.similarity != null ? "done" : "skipped",
    },
    {
      label: "Evidence SHA-256",
      value: result.evidence ? shortHash(result.evidence.sha256, 16, 10) : "not created",
      title: result.evidence?.sha256,
      state: result.evidence ? "done" : "skipped",
    },
    {
      label: "IPFS",
      value: result.storage
        ? result.storage.published
          ? shortHash(result.storage.cid, 12, 8)
          : `${shortHash(result.storage.cid, 12, 8)} (local only)`
        : "not created",
      title: result.storage?.cid,
      state: result.storage?.published ? "done" : "skipped",
    },
    {
      label: result.anchor?.chain_name ?? "Ethereum Sepolia",
      value: result.anchor ? shortHash(result.anchor.tx_hash, 12, 8) : "not anchored",
      title: result.anchor?.tx_hash,
      state: result.anchor ? "done" : "skipped",
    },
    {
      label: "On-chain read-back",
      value: result.onchain
        ? result.onchain.evidence_hash.replace(/^0x/, "").toLowerCase() ===
          result.evidence?.sha256
          ? "hashes match"
          : "hash mismatch"
        : "not compared",
      state: result.onchain ? "done" : "skipped",
    },
  ];

  return nodes;
}

const COLOR: Record<NodeState, string> = {
  done: "var(--verified)",
  skipped: "var(--ink-quaternary)",
  failed: "var(--rejected)",
};

export function SearchLineage({ result }: { result: VerificationResult }) {
  const nodes = buildNodes(result);

  return (
    <div style={{ display: "grid", gap: 0 }}>
      {nodes.map((node, index) => {
        const last = index === nodes.length - 1;
        return (
          <div key={node.label} style={{ display: "flex", gap: "var(--s4)", minWidth: 0 }}>
            {/* Spine */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <span
                aria-hidden
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  marginTop: 6,
                  background: node.state === "done" ? COLOR[node.state] : "transparent",
                  border: `1.5px solid ${COLOR[node.state]}`,
                }}
              />
              {!last && (
                <span
                  aria-hidden
                  style={{
                    width: 1,
                    flex: 1,
                    minHeight: 26,
                    background: node.state === "done" ? "var(--verified)" : "var(--line)",
                    opacity: node.state === "done" ? 0.35 : 1,
                  }}
                />
              )}
            </div>

            <div style={{ paddingBottom: last ? 0 : "var(--s4)", minWidth: 0, flex: 1 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "var(--s3)",
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 500,
                    color: node.state === "done" ? "var(--ink)" : "var(--ink-tertiary)",
                  }}
                >
                  {node.label}
                </span>
                <span
                  className="mono"
                  style={{
                    fontSize: 11.5,
                    color: node.state === "done" ? "var(--ink-secondary)" : "var(--ink-quaternary)",
                    overflowWrap: "anywhere",
                    textAlign: "right",
                  }}
                  title={node.title}
                >
                  {node.value}
                </span>
              </div>
              {node.note && (
                <p
                  style={{
                    margin: "2px 0 0",
                    fontSize: 11.5,
                    color: "var(--ink-quaternary)",
                  }}
                >
                  {node.note}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
