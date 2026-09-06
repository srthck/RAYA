"use client";

/** Shared primitives: a labelled measurement, a status pill, a copyable hash. */

import { useState } from "react";

import { copyText } from "@/lib/format";
import type { Tone } from "@/lib/format";

export function Field({
  label,
  value,
  title,
  tone,
  mono = true,
}: {
  label: string;
  value: React.ReactNode;
  title?: string;
  tone?: Tone;
  mono?: boolean;
}) {
  const color =
    tone === "verified"
      ? "var(--verified)"
      : tone === "rejected"
        ? "var(--rejected)"
        : tone === "pending"
          ? "var(--pending)"
          : "var(--ink)";

  return (
    <div className="field">
      <span className="label">{label}</span>
      <span
        className={mono ? "field-value" : undefined}
        style={{ color, fontSize: mono ? undefined : 13.5 }}
        title={title}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

export function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span className={`pill pill-${tone}`}>
      <span className="dot" aria-hidden />
      {children}
    </span>
  );
}

/**
 * A hash rendered as evidence: full value on hover, one click to copy.
 * Reviewers check these against `sha256sum` output, so copying must be exact
 * and must never include the ellipsis.
 */
export function CopyHash({
  value,
  label,
  display,
}: {
  value: string | null | undefined;
  label?: string;
  display?: string;
}) {
  const [copied, setCopied] = useState(false);

  if (!value) return <span className="field-value">—</span>;

  return (
    <button
      type="button"
      onClick={async () => {
        if (await copyText(value)) {
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        }
      }}
      title={`${label ? `${label}: ` : ""}${value}\nClick to copy`}
      style={{
        background: "none",
        border: "none",
        padding: 0,
        cursor: "pointer",
        textAlign: "left",
        fontFamily: "var(--font-mono)",
        fontSize: 12.5,
        color: copied ? "var(--verified)" : "var(--ink)",
        letterSpacing: "-0.02em",
        transition: "color var(--dur-fast) var(--ease)",
      }}
    >
      {copied ? "copied" : (display ?? value)}
    </button>
  );
}

export function Divider({ label }: { label?: string }) {
  if (!label) return <hr className="rule" />;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)" }}>
      <span className="label">{label}</span>
      <hr className="rule" style={{ flex: 1 }} />
    </div>
  );
}

/** An explicitly empty state. Never a spinner that could imply progress. */
export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="body"
      style={{ fontSize: 13.5, color: "var(--ink-tertiary)", margin: 0 }}
    >
      {children}
    </p>
  );
}

/**
 * A semantic status word.
 *
 * An absent value must never look like a successful one. Rather than printing
 * an em dash everywhere, each stage says what it actually is: WAITING (will
 * run), NOT RUN (never attempted), UNAVAILABLE (cannot run as configured),
 * N/A (does not apply to this run), FAILED, or a real result.
 */
export type StatusWord =
  | "WAITING"
  | "RUNNING"
  | "NOT RUN"
  | "NOT CREATED"
  | "PENDING"
  | "CONFIRMED"
  | "UNAVAILABLE"
  | "N/A"
  | "FAILED"
  | "COMPLETE"
  | "PASS"
  | "REJECTED"
  | "MATCH"
  | "MISMATCH"
  | "VERIFIED";

const STATUS_TONE: Record<StatusWord, Tone> = {
  WAITING: "neutral",
  RUNNING: "pending",
  "NOT RUN": "neutral",
  "NOT CREATED": "neutral",
  PENDING: "pending",
  CONFIRMED: "verified",
  UNAVAILABLE: "pending",
  "N/A": "neutral",
  FAILED: "rejected",
  COMPLETE: "verified",
  PASS: "verified",
  REJECTED: "rejected",
  MATCH: "verified",
  MISMATCH: "rejected",
  VERIFIED: "verified",
};

const TONE_COLOR: Record<Tone, string> = {
  verified: "var(--verified)",
  rejected: "var(--rejected)",
  pending: "var(--pending)",
  neutral: "var(--ink-tertiary)",
};

export function Status({ value }: { value: StatusWord }) {
  return (
    <span
      className="mono"
      style={{
        fontSize: 11.5,
        fontWeight: 560,
        letterSpacing: "0.06em",
        color: TONE_COLOR[STATUS_TONE[value]],
      }}
    >
      {value}
    </span>
  );
}

/** A labelled section of the technical panel, headed by its status. */
export function StatusBlock({
  title,
  status,
  reason,
  children,
}: {
  title: string;
  status: StatusWord;
  reason?: string | null;
  children?: React.ReactNode;
}) {
  return (
    <div style={{ display: "grid", gap: "var(--s3)", minWidth: 0 }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--s2)",
        }}
      >
        <span className="label">{title}</span>
        <Status value={status} />
      </div>
      {reason && (
        <p
          style={{
            margin: 0,
            fontSize: 11,
            lineHeight: 1.45,
            color: "var(--pending)",
            overflowWrap: "anywhere",
          }}
        >
          {reason}
        </p>
      )}
      {children}
    </div>
  );
}

/**
 * A forensic receipt block: aligned label/value rows, values monospaced and
 * selectable, long digests wrapped rather than truncated out of existence.
 *
 * Each row is `[label, value, fullValue?]`. When `fullValue` is given the row
 * becomes click-to-copy, because these are numbers a reviewer checks against
 * `sha256sum` or an explorer and a partial copy is worse than none.
 */
export function Receipt({
  rows,
}: {
  rows: Array<[string, React.ReactNode, (string | null | undefined)?]>;
}) {
  return (
    <div style={{ display: "grid", gap: 0 }}>
      {rows.map(([label, value, full], index) => (
        <div
          key={label}
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(140px, 34%) minmax(0, 1fr)",
            gap: "var(--s4)",
            padding: "7px 0",
            borderTop: index === 0 ? "1px solid var(--line)" : "none",
            borderBottom: "1px solid var(--line)",
            alignItems: "baseline",
          }}
        >
          <span className="label" style={{ letterSpacing: "0.08em" }}>
            {label}
          </span>
          <span style={{ minWidth: 0 }}>
            {full ? (
              <CopyHash value={full} display={String(value)} />
            ) : (
              <span
                className="mono"
                style={{ fontSize: 12.5, color: "var(--ink)", overflowWrap: "anywhere" }}
              >
                {value}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
