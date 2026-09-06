"use client";

/**
 * Every candidate the search returned, with what happened to it.
 *
 * Rejections are shown, not hidden. A wall that only ever displays the winner
 * gives a reviewer no way to tell whether the pipeline reasoned or got lucky --
 * so each tile carries its outcome, its reason and, where one was measured, its
 * similarity score against the threshold.
 */

import { AnimatePresence, motion } from "framer-motion";

import { Pill } from "@/components/atoms";
import { candidateStatusLabel, formatSimilarity, hostOf, shortHash } from "@/lib/format";
import type { Candidate } from "@/lib/types";

function tone(status: string) {
  if (status === "verified") return "verified" as const;
  if (status === "rejected") return "rejected" as const;
  if (status === "discovered") return "pending" as const;
  return "neutral" as const;
}

/** A one-line bar showing where a score sits relative to the threshold. */
function ScoreBar({ value, threshold }: { value: number; threshold: number }) {
  // Cosine similarity is defined on [-1, 1]; map to [0, 1] for display so a
  // negative score is still positioned honestly rather than clipped to zero.
  const pos = Math.max(0, Math.min(1, (value + 1) / 2));
  const mark = Math.max(0, Math.min(1, (threshold + 1) / 2));
  const passed = value >= threshold;

  return (
    <div style={{ position: "relative", height: 3, background: "var(--bg-inset)", borderRadius: 2 }}>
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${pos * 100}%` }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        style={{
          position: "absolute",
          inset: 0,
          background: passed ? "var(--verified)" : "var(--rejected)",
          borderRadius: 2,
        }}
      />
      <span
        aria-hidden
        title={`threshold ${threshold}`}
        style={{
          position: "absolute",
          left: `${mark * 100}%`,
          top: -3,
          width: 1,
          height: 9,
          background: "var(--ink)",
          opacity: 0.55,
        }}
      />
    </div>
  );
}

export function CandidateTile({
  candidate,
  threshold,
  evaluating,
  dimmed,
  verificationId,
}: {
  candidate: Candidate;
  threshold: number;
  evaluating: boolean;
  dimmed: boolean;
  verificationId: string | null;
}) {
  const similarity = candidate.verdict?.similarity;

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: dimmed ? 0.32 : 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="card"
      style={{
        padding: "var(--s4)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--s3)",
        borderColor:
          candidate.status === "verified" ? "var(--verified)" : "var(--line)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--s2)" }}>
        <div style={{ minWidth: 0 }}>
          <p
            style={{
              margin: 0,
              fontSize: 13.5,
              fontWeight: 560,
              letterSpacing: "-0.01em",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={candidate.title ?? undefined}
          >
            {candidate.platform_label}
            {candidate.is_post_url && (
              <span style={{ color: "var(--ink-tertiary)", fontWeight: 400 }}> · post</span>
            )}
          </p>
          <p
            className="mono"
            style={{
              margin: "2px 0 0",
              fontSize: 11,
              color: "var(--ink-tertiary)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {hostOf(candidate.page_url)}
          </p>
        </div>

        {evaluating ? (
          <Pill tone="pending">Evaluating</Pill>
        ) : (
          <Pill tone={tone(candidate.status)}>
            {candidateStatusLabel(candidate.status)}
          </Pill>
        )}
      </div>

      {candidate.has_preview && verificationId && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`/api/v1/verifications/${verificationId}/assets/candidate-${candidate.id}.jpg`}
          alt=""
          style={{
            width: "100%",
            height: 120,
            objectFit: "cover",
            borderRadius: "var(--radius)",
            background: "var(--bg-sunken)",
          }}
        />
      )}

      {similarity != null ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <span className="label">Similarity</span>
            <span
              className="numeral"
              style={{
                fontSize: 15,
                fontWeight: 560,
                color:
                  similarity >= threshold ? "var(--verified)" : "var(--rejected)",
              }}
            >
              {formatSimilarity(similarity)}
            </span>
          </div>
          <ScoreBar value={similarity} threshold={threshold} />
        </div>
      ) : (
        candidate.reason && (
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-tertiary)" }}>
            {candidate.reason}
          </p>
        )
      )}

      {candidate.image_sha256 && (
        <p
          className="mono"
          style={{ margin: 0, fontSize: 10.5, color: "var(--ink-quaternary)" }}
          title={`Retrieved image SHA-256: ${candidate.image_sha256}`}
        >
          retrieved · {shortHash(candidate.image_sha256, 8, 4)}
        </p>
      )}

      {candidate.page_url && (
        <a
          href={candidate.page_url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          style={{ fontSize: 12.5, color: "var(--ink-secondary)" }}
        >
          Open source ↗
        </a>
      )}
    </motion.article>
  );
}

export function CandidateWall({
  candidates,
  threshold,
  evaluating,
  matchId,
  verificationId,
  focusMatch,
}: {
  candidates: Candidate[];
  threshold: number;
  evaluating: Set<string>;
  matchId?: string;
  verificationId: string | null;
  focusMatch: boolean;
}) {
  const social = candidates.filter((c) => c.is_social);
  const filtered = candidates.filter((c) => !c.is_social);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "var(--s4)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--s3)" }}>
        <p className="label">Candidates</p>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-tertiary)" }}>
          {social.length} social · {filtered.length} filtered out
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(238px, 1fr))",
          gap: "var(--s3)",
        }}
      >
        <AnimatePresence mode="popLayout">
          {social.map((candidate) => (
            <CandidateTile
              key={candidate.id}
              candidate={candidate}
              threshold={threshold}
              evaluating={evaluating.has(candidate.id)}
              dimmed={focusMatch && candidate.id !== matchId}
              verificationId={verificationId}
            />
          ))}
        </AnimatePresence>
      </div>

      {filtered.length > 0 && (
        <details>
          <summary
            style={{
              cursor: "pointer",
              fontSize: 12.5,
              color: "var(--ink-tertiary)",
              listStyle: "none",
            }}
          >
            {filtered.length} result{filtered.length === 1 ? "" : "s"} were not
            public social sources — show
          </summary>
          <ul
            style={{
              margin: "var(--s3) 0 0",
              padding: 0,
              listStyle: "none",
              display: "grid",
              gap: 6,
            }}
          >
            {filtered.map((candidate) => (
              <li
                key={candidate.id}
                className="mono"
                style={{ fontSize: 11.5, color: "var(--ink-quaternary)" }}
              >
                {hostOf(candidate.page_url)} — {candidateStatusLabel(candidate.status)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
