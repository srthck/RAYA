"use client";

/**
 * The evidence record for one verification.
 *
 * Three things a reviewer can do here that are not decoration:
 *   - re-run the integrity check live against the chain,
 *   - run the tamper test and watch the hash diverge,
 *   - download the canonical bytes and check them with `sha256sum`.
 */

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";

import { Nav } from "@/components/Nav";
import { SearchLineage } from "@/components/SearchLineage";
import { CopyHash, Divider, Empty, Field, Pill } from "@/components/atoms";
import { api, ApiError } from "@/lib/api";
import {
  formatBytes,
  formatDuration,
  formatSimilarity,
  formatTime,
  hostOf,
  shortHash,
  statusTone,
} from "@/lib/format";
import type { TamperResult, VerificationResult } from "@/lib/types";

export default function EvidencePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [result, setResult] = useState<VerificationResult | null>(null);
  const [evidenceRecord, setEvidenceRecord] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tamper, setTamper] = useState<TamperResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [recheck, setRecheck] = useState<{ summary: string; verified: boolean } | null>(null);

  useEffect(() => {
    api
      .result(id)
      .then(setResult)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not load this verification."),
      );
    // Read the canonical record for model provenance. A failure here is not
    // fatal: a run that produced no evidence simply has none to show.
    fetch(api.evidenceUrl(id, true))
      .then((r) => (r.ok ? r.json() : null))
      .then(setEvidenceRecord)
      .catch(() => undefined);
  }, [id]);

  const runTamper = useCallback(async () => {
    setBusy("tamper");
    try {
      setTamper(await api.tamper(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Tamper test failed.");
    } finally {
      setBusy(null);
    }
  }, [id]);

  const runIntegrity = useCallback(async () => {
    setBusy("integrity");
    try {
      const response = await api.integrity(id);
      setRecheck({
        summary: response.integrity?.summary ?? "No checks could be performed.",
        verified: Boolean(response.integrity?.verified),
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Integrity check failed.");
    } finally {
      setBusy(null);
    }
  }, [id]);

  if (error) {
    return (
      <main className="shell">
        <Nav />
        <p style={{ color: "var(--rejected)", marginTop: "var(--s7)" }}>{error}</p>
      </main>
    );
  }

  if (!result) {
    return (
      <main className="shell">
        <Nav />
        <p className="body" style={{ marginTop: "var(--s7)" }}>
          Loading evidence…
        </p>
      </main>
    );
  }

  const match = result.match;
  const anchored = Boolean(result.anchor);
  // Model provenance lives in the evidence record itself, so what is shown
  // here is exactly what was hashed and (when anchored) committed.
  const verification = (evidenceRecord?.verification ?? {}) as Record<string, any>;
  const detector = verification.detector as
    | { name: string; version: string; model_sha256?: string | null }
    | undefined;
  const encoder = verification.encoder as
    | { name: string; version: string; dim: number; metric: string; model_sha256?: string | null }
    | undefined;

  return (
    <main className="shell" style={{ paddingBottom: "var(--s9)" }}>
      <Nav />

      <div style={{ paddingTop: "var(--s6)", maxWidth: 900 }}>
        {/* ---- header ------------------------------------------------- */}
        <Pill tone={statusTone(result.status)}>{result.headline}</Pill>

        <h1 className="h1" style={{ marginTop: "var(--s4)" }}>
          Evidence record
        </h1>
        <p
          className="mono"
          style={{ marginTop: "var(--s2)", color: "var(--ink-tertiary)", fontSize: 12.5 }}
        >
          {result.verification_id}
        </p>

        <div style={{ display: "flex", gap: "var(--s2)", marginTop: "var(--s5)", flexWrap: "wrap" }}>
          <a href={api.evidenceUrl(id)} className="btn btn-sm" download>
            Download evidence.json
          </a>
          <a href={api.exportUrl(id)} className="btn btn-ghost btn-sm" download>
            Export bundle (.zip)
          </a>
          <Link href={`/replay/${id}`} className="btn btn-ghost btn-sm">
            Replay verification
          </Link>
        </div>

        {/* ---- integrity ---------------------------------------------- */}
        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Integrity" />

          <div className="card" style={{ padding: "var(--s5)", marginTop: "var(--s4)" }}>
            <div style={{ display: "grid", gap: "var(--s4)" }}>
              <div style={{ display: "grid", gap: "var(--s3)" }}>
                <Field
                  label="Evidence SHA-256 (local)"
                  value={
                    <CopyHash
                      value={result.evidence?.sha256}
                      label="Evidence hash"
                      display={shortHash(result.evidence?.sha256, 20, 12)}
                    />
                  }
                />
                <Field
                  label="Evidence hash (on chain)"
                  value={
                    result.onchain ? (
                      <CopyHash
                        value={result.onchain.evidence_hash}
                        display={shortHash(result.onchain.evidence_hash, 20, 12)}
                      />
                    ) : (
                      "not anchored"
                    )
                  }
                  tone={result.onchain ? undefined : "pending"}
                />
              </div>

              {result.integrity && (
                <div style={{ display: "grid", gap: "var(--s2)" }}>
                  {result.integrity.checks.map((check) => (
                    <div
                      key={check.name}
                      style={{ display: "flex", gap: "var(--s3)", alignItems: "baseline" }}
                    >
                      <span
                        className="mono"
                        style={{
                          fontSize: 10.5,
                          width: 44,
                          color: !check.performed
                            ? "var(--ink-quaternary)"
                            : check.passed
                              ? "var(--verified)"
                              : "var(--rejected)",
                        }}
                      >
                        {!check.performed ? "SKIP" : check.passed ? "PASS" : "FAIL"}
                      </span>
                      <span style={{ fontSize: 13, color: "var(--ink-secondary)" }}>
                        {check.label}
                        {check.detail && (
                          <span style={{ color: "var(--ink-quaternary)" }}> — {check.detail}</span>
                        )}
                      </span>
                    </div>
                  ))}
                  <p style={{ margin: "var(--s2) 0 0", fontSize: 13, fontWeight: 500 }}>
                    {result.integrity.summary}
                  </p>
                </div>
              )}

              <div style={{ display: "flex", gap: "var(--s2)", flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={runIntegrity}
                  disabled={busy !== null}
                >
                  {busy === "integrity" ? "Checking…" : "Re-check against chain"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={runTamper}
                  disabled={busy !== null || !result.evidence}
                >
                  {busy === "tamper" ? "Running…" : "Run tamper test"}
                </button>
              </div>

              {recheck && (
                <p
                  style={{
                    margin: 0,
                    fontSize: 13,
                    color: recheck.verified ? "var(--verified)" : "var(--pending)",
                  }}
                >
                  {recheck.summary}
                </p>
              )}
            </div>
          </div>

          {/* ---- tamper demonstration --------------------------------- */}
          <AnimatePresence>
            {tamper && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="card"
                style={{
                  padding: "var(--s5)",
                  marginTop: "var(--s3)",
                  borderColor: tamper.detected ? "var(--verified)" : "var(--rejected)",
                }}
              >
                <p className="label">Tamper test</p>
                <p style={{ margin: "var(--s2) 0 var(--s4)", fontSize: 13.5 }}>
                  Altered <code className="mono">{tamper.field_path}</code> from{" "}
                  <code className="mono">{String(tamper.original_value)}</code> to{" "}
                  <code className="mono">{String(tamper.tampered_value)}</code> on a copy of
                  the record, then re-hashed it. Compared against the{" "}
                  {tamper.compared_against}.
                </p>

                <div style={{ display: "grid", gap: "var(--s3)" }}>
                  <Field
                    label="Original hash"
                    value={shortHash(tamper.original_hash, 24, 12)}
                    tone="verified"
                    title={tamper.original_hash}
                  />
                  <Field
                    label="Hash after tampering"
                    value={shortHash(tamper.tampered_hash, 24, 12)}
                    tone="rejected"
                    title={tamper.tampered_hash}
                  />
                </div>

                <p
                  style={{
                    margin: "var(--s4) 0 0",
                    fontSize: 14,
                    fontWeight: 560,
                    color: tamper.detected ? "var(--verified)" : "var(--rejected)",
                  }}
                >
                  {tamper.detected ? "Tampering detected" : "Tampering NOT detected"}
                </p>
                <p className="body" style={{ marginTop: 4, fontSize: 13 }}>
                  {tamper.summary}
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        {/* ---- the match ---------------------------------------------- */}
        {match && (
          <section style={{ marginTop: "var(--s7)" }}>
            <Divider label="Verified source" />
            <div style={{ display: "grid", gap: "var(--s3)", marginTop: "var(--s4)" }}>
              <Field label="Platform" value={match.platform_label} />
              <Field
                label="Post URL"
                value={
                  match.page_url ? (
                    <a
                      href={match.page_url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      style={{ textDecoration: "underline", textUnderlineOffset: 3 }}
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
                value={<CopyHash value={match.image_sha256} display={shortHash(match.image_sha256, 20, 12)} />}
              />
              <Field
                label="Similarity"
                value={formatSimilarity(match.verdict?.similarity)}
                tone="verified"
              />
              <Field
                label="Threshold"
                value={match.verdict?.threshold.toFixed(2) ?? "—"}
              />
            </div>
          </section>
        )}

        {/* ---- provenance ---------------------------------------------- */}
        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Evidence lineage" />
          <p className="body" style={{ margin: "var(--s4) 0 var(--s5)", fontSize: 13.5, maxWidth: 620 }}>
            Where this result came from, end to end. Note that the original
            input and the bounded search copy are separate objects with separate
            digests: the original was hashed locally and never published, and
            only the derivative was sent to the search provider.
          </p>
          <SearchLineage result={result} />
        </section>

        {/* ---- inspector ---------------------------------------------- */}
        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Inspector" />
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
              gap: "var(--s4)",
              marginTop: "var(--s4)",
            }}
          >
            <Field label="Created" value={formatTime(result.created_at)} mono={false} />
            <Field label="Duration" value={formatDuration(result.duration_ms)} />
            <Field label="Schema" value={result.evidence?.schema_version ?? "—"} />
            <Field label="Input SHA-256" value={shortHash(result.input.sha256, 14, 8)} title={result.input.sha256} />
            <Field label="Input size" value={formatBytes(result.input.byte_size)} />
            <Field
              label="Dimensions"
              value={`${result.input.width} × ${result.input.height}`}
            />
            <Field
              label="Search copy SHA-256"
              value={
                result.search_copy ? shortHash(result.search_copy.sha256, 14, 8) : "not created"
              }
              title={result.search_copy?.sha256}
            />
            <Field
              label="Search copy size"
              value={
                result.search_copy
                  ? `${result.search_copy.width} × ${result.search_copy.height} · ${formatBytes(result.search_copy.byte_size)}`
                  : "not created"
              }
            />
            <Field label="Search provider" value={result.search?.provider ?? "not run"} />
            <Field
              label="Search time"
              value={result.search ? formatTime(result.search.queried_at) : "not run"}
              mono={false}
            />
            <Field
              label="Result position"
              value={match ? `#${match.position}` : "n/a"}
            />
            <Field
              label="Detector"
              value={
                detector ? `${detector.name} ${detector.version}` : "—"
              }
            />
            <Field
              label="Detector model SHA-256"
              value={detector?.model_sha256 ? shortHash(detector.model_sha256, 12, 8) : "—"}
              title={detector?.model_sha256 ?? undefined}
            />
            <Field
              label="Face model"
              value={encoder ? `${encoder.name} ${encoder.version} · ${encoder.dim}d` : "—"}
            />
            <Field
              label="Face model SHA-256"
              value={encoder?.model_sha256 ? shortHash(encoder.model_sha256, 12, 8) : "—"}
              title={encoder?.model_sha256 ?? undefined}
            />
            <Field label="Metric" value={encoder?.metric ?? "cosine"} />
            <Field label="Results" value={String(result.counts.results)} />
            <Field label="Social candidates" value={String(result.counts.social)} />
            <Field label="Compared" value={String(result.counts.compared)} />
            <Field label="Rejected" value={String(result.counts.rejected)} tone="rejected" />
            <Field
              label="IPFS CID"
              value={
                result.storage ? (
                  result.storage.gateway_url ? (
                    <a
                      href={result.storage.gateway_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ textDecoration: "underline", textUnderlineOffset: 3 }}
                    >
                      {shortHash(result.storage.cid, 12, 8)} ↗
                    </a>
                  ) : (
                    shortHash(result.storage.cid, 12, 8)
                  )
                ) : (
                  "—"
                )
              }
              tone={result.storage && !result.storage.published ? "pending" : undefined}
            />
            <Field label="Chain" value={result.anchor?.chain_name ?? "not anchored"} tone={anchored ? undefined : "pending"} />
            <Field
              label="Contract"
              value={shortHash(result.anchor?.contract_address, 10, 8)}
              title={result.anchor?.contract_address}
            />
            <Field
              label="Transaction"
              value={
                result.anchor ? (
                  <a
                    href={result.anchor.explorer_tx_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ textDecoration: "underline", textUnderlineOffset: 3 }}
                  >
                    {shortHash(result.anchor.tx_hash, 10, 8)} ↗
                  </a>
                ) : (
                  "—"
                )
              }
            />
            <Field label="Block" value={result.anchor ? `#${result.anchor.block_number}` : "—"} />
          </div>

          {result.storage && !result.storage.published && result.storage.detail && (
            <p style={{ marginTop: "var(--s4)", fontSize: 13, color: "var(--pending)" }}>
              {result.storage.detail}
            </p>
          )}
        </section>

        {/* ---- rejected candidates ------------------------------------ */}
        {result.candidates && result.candidates.length > 0 && (
          <section style={{ marginTop: "var(--s7)" }}>
            <Divider label={`All candidates (${result.candidates.length})`} />
            <div className="scroll-x" style={{ marginTop: "var(--s4)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
                <thead>
                  <tr>
                    {["Platform", "Source", "Outcome", "Similarity", "Image SHA-256"].map((h) => (
                      <th
                        key={h}
                        className="label"
                        style={{ textAlign: "left", padding: "0 var(--s3) var(--s2) 0" }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.candidates.map((candidate) => (
                    <tr key={candidate.id} style={{ borderTop: "1px solid var(--line)" }}>
                      <td style={{ padding: "8px var(--s3) 8px 0", fontSize: 12.5 }}>
                        {candidate.platform_label}
                      </td>
                      <td className="mono" style={{ padding: "8px var(--s3) 8px 0", fontSize: 11.5, color: "var(--ink-tertiary)" }}>
                        {hostOf(candidate.page_url)}
                      </td>
                      <td style={{ padding: "8px var(--s3) 8px 0", fontSize: 12 }}>
                        <span
                          style={{
                            color:
                              candidate.status === "verified"
                                ? "var(--verified)"
                                : candidate.status === "rejected"
                                  ? "var(--rejected)"
                                  : "var(--ink-tertiary)",
                          }}
                        >
                          {candidate.status}
                        </span>
                      </td>
                      <td className="numeral" style={{ padding: "8px var(--s3) 8px 0", fontSize: 12 }}>
                        {formatSimilarity(candidate.verdict?.similarity)}
                      </td>
                      <td className="mono" style={{ padding: "8px 0", fontSize: 11, color: "var(--ink-quaternary)" }}>
                        {candidate.image_sha256 ? shortHash(candidate.image_sha256, 8, 6) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ---- what this does not claim -------------------------------- */}
        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Scope of this record" />
          <p className="body" style={{ marginTop: "var(--s4)", maxWidth: 620, fontSize: 13.5 }}>
            This record asserts that a face in the input image and a face in an
            independently retrieved source image scored at or above the stated
            threshold under the named model. It is not an identity
            determination: it does not establish who the person is, that the
            source post is authentic, or that the depicted person consented to
            it. Face recognition error rates vary with image quality and across
            demographic groups.
          </p>
        </section>

        {/* ---- verify it yourself -------------------------------------- */}
        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Verify this yourself" />
          <pre
            className="mono scroll-x"
            style={{
              marginTop: "var(--s4)",
              padding: "var(--s4)",
              background: "var(--bg-sunken)",
              border: "1px solid var(--line)",
              borderRadius: "var(--radius)",
              fontSize: 12,
              lineHeight: 1.7,
            }}
          >
{`# download the canonical bytes and hash them
curl -sO ${typeof window !== "undefined" ? window.location.origin : ""}${api.evidenceUrl(id)}
sha256sum evidence.json

# must equal
${result.evidence?.sha256 ?? "—"}`}
          </pre>
          {!result.evidence && <Empty>No evidence was produced for this run.</Empty>}
        </section>
      </div>
    </main>
  );
}
