"use client";

/**
 * Match preview: input face, score, source face.
 *
 * Rendered only once a real comparison has completed. Until then the panel
 * states what it is waiting for rather than showing an empty frame, because a
 * blank comparison reads as a comparison that returned nothing.
 *
 * The score is a raw cosine value beside the threshold it was judged against.
 * Never a percentage: a percentage reads as a probability of identity, which
 * is precisely the claim RAYA does not make.
 */

import Link from "next/link";
import { motion } from "framer-motion";

import { formatSimilarity } from "@/lib/format";
import type { PipelineState } from "@/lib/usePipeline";

function Face({ src, label }: { src: string | null; label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0, flex: 1 }}>
      <span className="label" style={{ fontSize: 9.5, textAlign: "center" }}>
        {label}
      </span>
      <div
        style={{
          aspectRatio: "1 / 1",
          borderRadius: "var(--radius-lg)",
          overflow: "hidden",
          border: "1px solid var(--line)",
          background: "var(--bg-sunken)",
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
    </div>
  );
}

export function MatchPreview({
  state,
  verificationId,
  threshold,
}: {
  state: PipelineState;
  verificationId: string;
  threshold: number;
}) {
  const match = state.match;
  const rejected = state.candidates.filter((c) => c.status === "rejected");
  const comparedSomething = match || rejected.length > 0;

  return (
    <section className="panel" aria-label="Match preview">
      <div className="panel-head">
        <h2 className="panel-title">Match preview</h2>
        {match && (
          <Link
            href={`/evidence/${verificationId}`}
            style={{ fontSize: 12.5, color: "var(--accent)" }}
          >
            View details →
          </Link>
        )}
      </div>

      {!comparedSomething && (
        <p className="body" style={{ fontSize: 13 }}>
          {state.stages.verify?.state === "active"
            ? "Comparing candidates…"
            : "No comparison has run yet. A face comparison appears here once a candidate has been retrieved and scored."}
        </p>
      )}

      {comparedSomething && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          style={{ display: "grid", gap: "var(--s4)" }}
        >
          <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--s4)" }}>
            <Face
              src={`/api/v1/verifications/${verificationId}/assets/input-face.jpg`}
              label="Input face"
            />

            <div style={{ textAlign: "center", flex: "none", paddingBottom: 4 }}>
              <div
                className="numeral"
                style={{
                  fontSize: 26,
                  fontWeight: 620,
                  lineHeight: 1,
                  color: match ? "var(--verified)" : "var(--rejected)",
                }}
              >
                {formatSimilarity(
                  (match ?? rejected[0])?.verdict?.similarity ?? null,
                )}
              </div>
              <p className="label" style={{ fontSize: 9, marginTop: 4 }}>
                Similarity
              </p>
              <p
                className="mono"
                style={{ fontSize: 11, color: "var(--ink-tertiary)", marginTop: "var(--s3)" }}
              >
                {threshold.toFixed(2)}
              </p>
              <p className="label" style={{ fontSize: 9, marginTop: 2 }}>
                Threshold
              </p>
            </div>

            <Face
              src={
                (match ?? rejected[0])?.has_preview
                  ? `/api/v1/verifications/${verificationId}/assets/candidate-${(match ?? rejected[0]).id}.jpg`
                  : null
              }
              label="Source face"
            />
          </div>

          <div style={{ textAlign: "center" }}>
            <span className={`pill pill-${match ? "verified" : "rejected"}`}>
              <span className="dot" aria-hidden />
              {match ? "Verified visual match" : "Rejected — below threshold"}
            </span>
          </div>

          {/* The product's central claim, placed where the score is most likely
              to be over-read. */}
          <div
            style={{
              display: "flex",
              gap: "var(--s3)",
              padding: "var(--s4)",
              borderRadius: "var(--radius-lg)",
              background: "var(--accent-soft)",
              border: "1px solid var(--line)",
            }}
          >
            <span aria-hidden style={{ color: "var(--accent)", fontSize: 14, lineHeight: 1.2 }}>
              ◈
            </span>
            <div style={{ minWidth: 0 }}>
              <p style={{ margin: 0, fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>
                Discovery isn&apos;t proof.
              </p>
              <p
                className="body"
                style={{ marginTop: 3, fontSize: 12.5, lineHeight: 1.5 }}
              >
                Reverse search discovered the candidate. RAYA independently
                re-downloaded the source and compared the detected face against
                it. This is not an identity determination.
              </p>
            </div>
          </div>
        </motion.div>
      )}
    </section>
  );
}
