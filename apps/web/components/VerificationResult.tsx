"use client";

/**
 * The climax: what RAYA independently decided.
 *
 * Two faces, one number, one decision. The score is a raw cosine value beside
 * the threshold it was judged against -- never a percentage, because a
 * percentage reads as a probability of identity and that is precisely the
 * claim RAYA does not make.
 *
 * A rejection is rendered with the same weight as a match. Showing only
 * successes would give a reviewer no way to tell whether the pipeline reasoned
 * or simply accepted the first result.
 *
 * `proves` / `does not prove` is bound to what the run actually achieved, so a
 * partial run shows a partial list rather than a wall of ticks.
 */

import { motion, useReducedMotion } from "framer-motion";

import { formatSimilarity, hostOf, shortHash } from "@/lib/format";
import type { PipelineState } from "@/lib/usePipeline";

function Face({
  src,
  label,
  caption,
}: {
  src: string | null;
  label: string;
  caption?: string;
}) {
  return (
    <div style={{ minWidth: 0, flex: 1 }}>
      <div
        style={{
          aspectRatio: "1 / 1",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          border: "1px solid var(--line)",
          background: "var(--bg-sunken)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        {src && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={label}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        )}
      </div>
      <p className="label" style={{ marginTop: "var(--s3)" }}>
        {label}
      </p>
      {caption && (
        <p
          className="mono"
          style={{ fontSize: 10.5, color: "var(--ink-tertiary)", marginTop: 2 }}
        >
          {caption}
        </p>
      )}
    </div>
  );
}

export function VerificationResult({
  state,
  verificationId,
  threshold,
}: {
  state: PipelineState;
  verificationId: string;
  threshold: number;
}) {
  const reduce = useReducedMotion();
  const match = state.match;
  const rejected = state.candidates.filter((c) => c.status === "rejected");
  const subject = match ?? rejected[0];
  if (!subject) return null;

  const similarity = subject.verdict?.similarity ?? 0;
  const passed = Boolean(match);
  const tone = passed ? "var(--verified)" : "var(--rejected)";

  const proves: [string, boolean][] = [
    ["A candidate source was discovered", Boolean(state.searchCounts)],
    ["A face was detected and encoded locally", state.faces.length > 0],
    ["The source image was independently retrieved", Boolean(subject.image_sha256)],
    [`The score ${passed ? "exceeded" : "did not reach"} the configured threshold`, true],
    ["Evidence was canonically generated and hashed", Boolean(state.evidence)],
    ["The evidence was anchored on chain", Boolean(state.anchor)],
    ["The anchored digest matched on read-back", Boolean(state.readback?.matches)],
  ];

  const doesNot = [
    "The real-world identity of any person",
    "That the source itself is authentic",
    "That no unindexed or private source exists",
    "Certainty beyond the limits of the face model",
  ];

  const rise = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 10 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.6, delay, ease: [0.16, 1, 0.3, 1] as const },
        };

  return (
    <div className="result-sheet">
      {/* ---- the comparison --------------------------------------------- */}
      <motion.div
        {...rise(0)}
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "clamp(var(--s4), 4vw, var(--s7))",
          maxWidth: 640,
        }}
      >
        <Face
          src={`/api/v1/verifications/${verificationId}/assets/input-face.jpg`}
          label="Input face"
          caption={shortHash(state.input?.sha256, 8, 6)}
        />

        <div style={{ flex: "none", textAlign: "center", paddingTop: "clamp(24px, 5vw, 56px)" }}>
          <motion.div {...rise(0.14)} className="result-score" style={{ color: tone }}>
            {formatSimilarity(similarity)}
          </motion.div>
          <p className="label" style={{ marginTop: "var(--s2)" }}>
            Similarity
          </p>
          <p
            className="mono"
            style={{ fontSize: 12, color: "var(--ink-tertiary)", marginTop: "var(--s4)" }}
          >
            {threshold.toFixed(2)}
          </p>
          <p className="label" style={{ marginTop: 2 }}>
            Threshold
          </p>
        </div>

        <Face
          src={
            subject.has_preview
              ? `/api/v1/verifications/${verificationId}/assets/candidate-${subject.id}.jpg`
              : null
          }
          label="Source face"
          caption={shortHash(subject.image_sha256, 8, 6)}
        />
      </motion.div>

      {/* ---- the decision ------------------------------------------------ */}
      <motion.div {...rise(0.26)} style={{ marginTop: "var(--s6)" }}>
        <p
          className="h2"
          style={{ color: tone, letterSpacing: "-0.03em" }}
        >
          {passed ? "Verified visual match" : "Rejected — below threshold"}
        </p>
        {subject.page_url && (
          <p className="body" style={{ marginTop: "var(--s2)", fontSize: 13.5 }}>
            {subject.platform_label} ·{" "}
            <a
              href={subject.page_url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              style={{ color: "var(--accent)", textDecoration: "underline", textUnderlineOffset: 3 }}
            >
              {hostOf(subject.page_url)} ↗
            </a>
          </p>
        )}
      </motion.div>

      {/* ---- the thesis --------------------------------------------------- */}
      <motion.div
        {...rise(0.34)}
        style={{
          marginTop: "var(--s6)",
          paddingTop: "var(--s5)",
          borderTop: "1px solid var(--line)",
        }}
      >
        <p
          className="h2"
          style={{ letterSpacing: "-0.03em", maxWidth: 20 + "ch" }}
        >
          Discovery isn&apos;t proof.
        </p>
        <p className="body" style={{ marginTop: "var(--s3)", maxWidth: "62ch", fontSize: 14 }}>
          Reverse search discovered this candidate. RAYA re-downloaded the source
          image itself and compared the detected face against it with its own
          models. The search engine proposed; RAYA decided.
        </p>
      </motion.div>

      {/* ---- what it does and does not establish -------------------------- */}
      <motion.div
        {...rise(0.42)}
        className="proof-grid"
        style={{ marginTop: "var(--s6)" }}
      >
        <div>
          <p className="label" style={{ marginBottom: "var(--s3)" }}>
            This establishes
          </p>
          <div style={{ display: "grid", gap: "var(--s2)" }}>
            {proves.map(([line, ok]) => (
              <div key={line} className="proof-item">
                <span
                  aria-hidden
                  style={{
                    color: ok ? "var(--verified)" : "var(--ink-quaternary)",
                    width: 12,
                    flex: "none",
                  }}
                >
                  {ok ? "✓" : "·"}
                </span>
                <span style={{ color: ok ? "var(--ink)" : "var(--ink-quaternary)" }}>
                  {line}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="label" style={{ marginBottom: "var(--s3)" }}>
            This does not establish
          </p>
          <div style={{ display: "grid", gap: "var(--s2)" }}>
            {doesNot.map((line) => (
              <div key={line} className="proof-item">
                <span aria-hidden style={{ color: "var(--ink-quaternary)", width: 12, flex: "none" }}>
                  ×
                </span>
                <span style={{ color: "var(--ink-secondary)" }}>{line}</span>
              </div>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
