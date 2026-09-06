"use client";

/**
 * The result frame.
 *
 * Deliberately restrained. The headline states what was established -- a
 * verified *visual match*, never an identity -- and the score is shown as a raw
 * cosine value beside the threshold it was judged against, so the reader can
 * see the decision rather than being handed a verdict.
 */

import Link from "next/link";
import { motion } from "framer-motion";

import { Field, Pill } from "@/components/atoms";
import { formatSimilarity, hostOf, shortHash } from "@/lib/format";
import type { PipelineState } from "@/lib/usePipeline";

function FacePane({ src, caption }: { src: string | null; caption: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--s2)", minWidth: 0 }}>
      <div
        style={{
          aspectRatio: "1 / 1",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          background: "var(--bg-inset)",
          border: "1px solid var(--line)",
        }}
      >
        {src && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={caption}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        )}
      </div>
      <span className="label">{caption}</span>
    </div>
  );
}

export function MatchReveal({
  state,
  verificationId,
  threshold,
}: {
  state: PipelineState;
  verificationId: string;
  threshold: number;
}) {
  const match = state.match;
  if (!match) return null;

  const similarity = match.verdict?.similarity ?? 0;
  const anchored = Boolean(state.anchor);
  const integrityVerified = state.integrity?.verified && state.integrity?.anchored;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
      style={{ display: "flex", flexDirection: "column", gap: "var(--s6)" }}
    >
      <div>
        <Pill tone="verified">Verified visual match</Pill>
        <h2 className="h1" style={{ marginTop: "var(--s4)", maxWidth: 620 }}>
          Public visual match, independently verified.
        </h2>
        <p className="body" style={{ marginTop: "var(--s3)", maxWidth: 560, fontSize: 14 }}>
          RAYA re-downloaded the source image and compared faces with its own
          models. This is not an identity determination.
        </p>
      </div>

      {/* ---- the comparison ------------------------------------------ */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto 1fr",
          gap: "var(--s5)",
          alignItems: "center",
          maxWidth: 620,
        }}
      >
        <FacePane
          src={`/api/v1/verifications/${verificationId}/assets/input-face.jpg`}
          caption="Input face"
        />

        <div style={{ textAlign: "center" }}>
          <motion.div
            className="numeral"
            initial={{ opacity: 0, scale: 0.94 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.55, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            style={{
              fontSize: "clamp(2.2rem, 5vw, 3.4rem)",
              fontWeight: 560,
              color: "var(--verified)",
              lineHeight: 1,
            }}
          >
            {formatSimilarity(similarity)}
          </motion.div>
          <p className="label" style={{ marginTop: "var(--s2)" }}>
            SFace cosine
          </p>
          <p
            className="mono"
            style={{ fontSize: 11, color: "var(--ink-tertiary)", marginTop: 2 }}
          >
            threshold {threshold.toFixed(2)}
          </p>
        </div>

        <FacePane
          src={
            match.has_preview
              ? `/api/v1/verifications/${verificationId}/assets/candidate-${match.id}.jpg`
              : null
          }
          caption="Source face"
        />
      </div>

      {/* ---- the source ---------------------------------------------- */}
      <div style={{ display: "grid", gap: "var(--s3)", maxWidth: 620 }}>
        <Field label="Platform" value={match.platform_label} />
        <Field
          label="Source"
          value={
            match.page_url ? (
              <a
                href={match.page_url}
                target="_blank"
                rel="noopener noreferrer nofollow"
                style={{ color: "var(--ink)", textDecoration: "underline", textUnderlineOffset: 3 }}
              >
                {hostOf(match.page_url)} ↗
              </a>
            ) : (
              "—"
            )
          }
        />
        <Field
          label="Source image SHA-256"
          value={shortHash(match.image_sha256, 16, 8)}
          title={match.image_sha256 ?? undefined}
        />
      </div>

      {/* ---- what was established ------------------------------------ */}
      <div style={{ display: "grid", gap: "var(--s2)", maxWidth: 620 }}>
        <Checklist label="Discovered by reverse image search" ok />
        <Checklist label="Public social source" ok={match.is_social} />
        <Checklist label="Source image independently retrieved" ok={Boolean(match.image_sha256)} />
        <Checklist label="Face verified against threshold" ok />
        <Checklist label="Evidence hashed" ok={Boolean(state.evidence)} />
        <Checklist
          label={
            state.storage?.published
              ? "Evidence stored on IPFS"
              : "Evidence stored locally (not published to IPFS)"
          }
          ok={Boolean(state.storage?.published)}
          degraded={Boolean(state.storage && !state.storage.published)}
        />
        <Checklist
          label={anchored ? "Evidence anchored on chain" : "Evidence not anchored"}
          ok={anchored}
          degraded={!anchored}
        />
        <Checklist
          label={
            integrityVerified
              ? "On-chain hash matches local hash"
              : "Integrity not confirmed against a chain"
          }
          ok={Boolean(integrityVerified)}
          degraded={!integrityVerified}
        />
      </div>

      <div style={{ display: "flex", gap: "var(--s2)", flexWrap: "wrap" }}>
        <Link href={`/evidence/${verificationId}`} className="btn btn-sm">
          View evidence
        </Link>
        {match.page_url && (
          <a
            href={match.page_url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="btn btn-ghost btn-sm"
          >
            Open source ↗
          </a>
        )}
        {state.anchor && (
          <a
            href={state.anchor.explorerTxUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost btn-sm"
          >
            View transaction ↗
          </a>
        )}
      </div>
    </motion.section>
  );
}

function Checklist({
  label,
  ok,
  degraded,
}: {
  label: string;
  ok: boolean;
  degraded?: boolean;
}) {
  const color = ok ? "var(--verified)" : degraded ? "var(--pending)" : "var(--ink-quaternary)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)" }}>
      <span aria-hidden style={{ color, fontSize: 13, width: 12 }}>
        {ok ? "✓" : degraded ? "—" : "·"}
      </span>
      <span style={{ fontSize: 13.5, color: ok ? "var(--ink)" : "var(--ink-secondary)" }}>
        {label}
      </span>
    </div>
  );
}
