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
import { CopyHash, Divider, Empty, Field, Pill, Receipt } from "@/components/atoms";
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
  // Each line is bound to something the run actually achieved, so a partial
  // run shows a partial list rather than a uniform wall of ticks.
  const PROVES: [string, boolean][] = [
    ["A candidate source was discovered.", Boolean(result.search)],
    ["A face was detected locally.", result.faces.length > 0],
    ["The candidate exceeded the configured similarity threshold.", Boolean(result.match)],
    ["Evidence was canonically generated.", Boolean(result.evidence)],
    ["Evidence was hashed.", Boolean(result.evidence)],
    ["Evidence was preserved on IPFS.", Boolean(result.storage?.published)],
    ["Evidence was anchored on chain.", Boolean(result.anchor)],
    ["The on-chain commitment was read back.", Boolean(result.onchain)],
    [
      "Local and on-chain hashes matched.",
      Boolean(result.integrity?.anchored && result.integrity?.verified),
    ],
  ];
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
        {/* ---- forensic receipt ---------------------------------------- */}
        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Observed" />
          <p className="body" style={{ margin: "var(--s3) 0 var(--s4)", fontSize: 12.5 }}>
            What RAYA received and measured directly.
          </p>
          <Receipt
            rows={[
              ["Verification ID", result.verification_id, result.verification_id],
              ["Created", formatTime(result.created_at)],
              ["Input SHA-256", shortHash(result.input.sha256, 20, 12), result.input.sha256],
              ["Input size", formatBytes(result.input.byte_size)],
              ["Input dimensions", `${result.input.width} x ${result.input.height}`],
              ["Input type", result.input.mime],
            ]}
          />
        </section>

        <section style={{ marginTop: "var(--s6)" }}>
          <Divider label="Derived" />
          <p className="body" style={{ margin: "var(--s3) 0 var(--s4)", fontSize: 12.5 }}>
            Artifacts RAYA produced from the input, and what was sent outward.
          </p>
          <Receipt
            rows={[
              [
                "Search copy SHA-256",
                result.search_copy ? shortHash(result.search_copy.sha256, 20, 12) : "NOT CREATED",
                result.search_copy?.sha256,
              ],
              [
                "Search copy",
                result.search_copy
                  ? `${result.search_copy.width} x ${result.search_copy.height} - ${formatBytes(result.search_copy.byte_size)} - q${result.search_copy.jpeg_quality}`
                  : "NOT CREATED",
              ],
              ["Search provider", result.search?.provider ?? "NOT RUN"],
              ["Search time", result.search ? formatTime(result.search.queried_at) : "NOT RUN"],
              ["Result position", match ? `#${match.position}` : "N/A"],
              ["Candidates", result.search ? String(result.counts.results) : "NOT RUN"],
              ["Social candidates", result.search ? String(result.counts.social) : "NOT RUN"],
              ["Compared", result.search ? String(result.counts.compared) : "NOT RUN"],
            ]}
          />
        </section>

        <section style={{ marginTop: "var(--s6)" }}>
          <Divider label="Verified" />
          <p className="body" style={{ margin: "var(--s3) 0 var(--s4)", fontSize: 12.5 }}>
            The independent comparison, and the exact models that performed it.
          </p>
          <Receipt
            rows={[
              ["Source platform", match?.platform_label ?? "NONE VERIFIED"],
              ["Source URL", match?.page_url ?? "NONE VERIFIED", match?.page_url ?? undefined],
              [
                "Source image URL",
                match?.image_url ?? "NONE VERIFIED",
                match?.image_url ?? undefined,
              ],
              [
                "Source image SHA-256",
                match?.image_sha256 ? shortHash(match.image_sha256, 20, 12) : "NOT RETRIEVED",
                match?.image_sha256 ?? undefined,
              ],
              ["Detector", detector ? `${detector.name} ${detector.version}` : "unknown"],
              [
                "Detector model SHA-256",
                detector?.model_sha256 ? shortHash(detector.model_sha256, 16, 10) : "unknown",
                detector?.model_sha256 ?? undefined,
              ],
              [
                "Face model",
                encoder ? `${encoder.name} ${encoder.version} - ${encoder.dim}d` : "unknown",
              ],
              [
                "Face model SHA-256",
                encoder?.model_sha256 ? shortHash(encoder.model_sha256, 16, 10) : "unknown",
                encoder?.model_sha256 ?? undefined,
              ],
              ["Metric", encoder?.metric ?? "cosine"],
              [
                "Threshold",
                (match?.verdict?.threshold ?? verification.threshold ?? 0.4).toFixed(2),
              ],
              [
                "Similarity",
                result.similarity != null ? formatSimilarity(result.similarity) : "NOT RUN",
              ],
              [
                "Decision",
                result.similarity == null
                  ? "NOT RUN"
                  : match
                    ? "PASS - verified visual match"
                    : "REJECT - below threshold",
              ],
            ]}
          />
        </section>

        <section style={{ marginTop: "var(--s6)" }}>
          <Divider label="Anchored" />
          <p className="body" style={{ margin: "var(--s3) 0 var(--s4)", fontSize: 12.5 }}>
            Where the evidence was preserved and committed.
          </p>
          <Receipt
            rows={[
              [
                "Evidence SHA-256",
                result.evidence ? shortHash(result.evidence.sha256, 20, 12) : "NOT CREATED",
                result.evidence?.sha256,
              ],
              [
                "IPFS CID",
                result.storage
                  ? result.storage.published
                    ? shortHash(result.storage.cid, 14, 10)
                    : `${shortHash(result.storage.cid, 14, 10)} (local only)`
                  : "NOT CREATED",
                result.storage?.cid,
              ],
              ["Network", result.anchor?.chain_name ?? "NOT RUN"],
              [
                "Contract",
                result.anchor ? shortHash(result.anchor.contract_address, 12, 10) : "NOT RUN",
                result.anchor?.contract_address,
              ],
              [
                "Transaction",
                result.anchor ? shortHash(result.anchor.tx_hash, 14, 10) : "NOT RUN",
                result.anchor?.tx_hash,
              ],
              ["Block", result.anchor ? `#${result.anchor.block_number}` : "NOT RUN"],
            ]}
          />
        </section>

        <section style={{ marginTop: "var(--s6)" }}>
          <Divider label="Integrity checked" />
          <p className="body" style={{ margin: "var(--s3) 0 var(--s4)", fontSize: 12.5 }}>
            The fresh read-back, and what it compared.
          </p>
          <Receipt
            rows={[
              [
                "On-chain evidence hash",
                result.onchain ? shortHash(result.onchain.evidence_hash, 20, 12) : "NOT READ BACK",
                result.onchain?.evidence_hash,
              ],
              [
                "Read-back",
                result.onchain
                  ? result.onchain.evidence_hash.replace(/^0x/, "").toLowerCase() ===
                    result.evidence?.sha256
                    ? "MATCH"
                    : "MISMATCH"
                  : "NOT RUN",
              ],
              [
                "Integrity",
                result.integrity?.anchored && result.integrity?.verified
                  ? "VERIFIED"
                  : "NOT VERIFIED",
              ],
            ]}
          />
          {result.integrity && (
            <p className="body" style={{ marginTop: "var(--s4)", fontSize: 13 }}>
              {result.integrity.summary}
            </p>
          )}
        </section>

        {/* ---- what this proves, and what it does not ------------------- */}
        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="What this proves" />
          <div style={{ display: "grid", gap: "var(--s2)", marginTop: "var(--s4)", maxWidth: 640 }}>
            {PROVES.map(([label, ok]) => (
              <div key={label} style={{ display: "flex", gap: "var(--s3)" }}>
                <span
                  aria-hidden
                  style={{
                    width: 12,
                    fontSize: 13,
                    color: ok ? "var(--verified)" : "var(--ink-quaternary)",
                  }}
                >
                  {ok ? "✓" : "·"}
                </span>
                <span style={{ fontSize: 13.5, color: ok ? "var(--ink)" : "var(--ink-quaternary)" }}>
                  {label}
                </span>
              </div>
            ))}
          </div>

          <p className="label" style={{ marginTop: "var(--s6)" }}>
            What this does not prove
          </p>
          <div style={{ display: "grid", gap: "var(--s2)", marginTop: "var(--s3)", maxWidth: 640 }}>
            {[
              "The real-world identity of any person.",
              "The authenticity of the underlying source.",
              "That no unindexed source exists.",
              "Certainty beyond the limitations of the face model.",
            ].map((line) => (
              <div key={line} style={{ display: "flex", gap: "var(--s3)" }}>
                <span aria-hidden style={{ width: 12, fontSize: 13, color: "var(--ink-quaternary)" }}>
                  &times;
                </span>
                <span style={{ fontSize: 13.5, color: "var(--ink-secondary)" }}>{line}</span>
              </div>
            ))}
          </div>
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
