"use client";

/**
 * How RAYA works, and — given equal weight — what it cannot do.
 */

import Link from "next/link";

import { Nav } from "@/components/Nav";
import { Divider } from "@/components/atoms";

const STAGES = [
  ["01", "Input", "The image is validated, decoded and hashed with SHA-256 before anything else. Every later claim refers to exactly these bytes."],
  ["02", "Face detection", "YuNet locates faces locally. If none is found, the run stops. If several are found, RAYA asks which is the subject rather than guessing."],
  ["03", "Face encoding", "SFace turns the aligned face into a 128-dimensional vector. The vector never leaves the machine — it is not stored in the evidence, on IPFS or on chain."],
  ["04", "Bounded search copy", "The original input is never published or re-encoded. RAYA derives a separate, deterministically compressed copy that fits the provider's 500 KB upload limit, and hashes it in its own right. Two objects, two digests."],
  ["05", "Reverse image search", "The search copy is uploaded directly to the provider, which returns an image id, and Google Lens is queried by that id. With no API key configured, RAYA reports the search as unavailable; it never substitutes placeholder results."],
  ["06", "Candidate filtering", "Results are classified by platform. Only known public social sources become candidates, and everything filtered out is still counted and shown."],
  ["07", "Independent verification", "RAYA re-downloads each candidate image itself, detects a face with its own detector, encodes it with its own encoder, and compares. The search engine does not get a vote."],
  ["08", "Evidence", "A canonical JSON record is built and hashed. Canonical means byte-reproducible: the same logical record always yields the same digest."],
  ["09", "IPFS", "The bundle is stored under a content address, so the CID cannot later point at different content."],
  ["10", "Anchor", "The evidence hash, input hash, source hash and CID are written to a write-once contract on Ethereum Sepolia."],
  ["11", "Read-back", "After confirmation, RAYA makes a fresh call to the contract and compares the stored hash with the local one."],
  ["12", "Integrity", "Only if that comparison passes does RAYA say the evidence is intact. A submitted transaction is not treated as success."],
];

const LIMITS = [
  ["A similarity score is not an identity.", "RAYA reports that two faces scored above a threshold under a named model. It does not know who anyone is, and it never attaches a name."],
  ["Error rates vary with image quality and demographics.", "Blur, low resolution, extreme pose and lighting all shift scores, and published evaluations consistently find accuracy differences across demographic groups. A single score should not be read as a uniform confidence."],
  ["The threshold is a policy choice.", "0.40 was calibrated on 88 public-domain portraits across 23 identities (3,828 pairs). No different-person pair scored above 0.3773, so 0.40 gives zero false matches on that set, at the cost of missing roughly one genuine pair in five. It is chosen to drive false matches to zero rather than to minimise total error, and the value used is recorded in every evidence bundle."],
  ["Coverage is bounded by the search provider.", "RAYA can only verify candidates that the reverse image search returns. A source that is not indexed, is private, or is behind a login will not be found. Absence of a match is not evidence of absence."],
  ["Some sources cannot be retrieved.", "Platforms block automated image fetching. Such a candidate is recorded as discovered-but-unretrievable rather than silently dropped or, worse, accepted on the provider's word."],
  ["An anchor proves integrity, not truth.", "The chain shows a hash existed at a point in time and has not changed. It says nothing about whether the underlying source post is authentic."],
  ["Evidence is only as private as IPFS.", "Bundles are public and effectively permanent. That is why they contain hashes, URLs and scores — never face images or embeddings."],
];

export default function AboutPage() {
  return (
    <main className="shell" style={{ paddingBottom: "var(--s9)" }}>
      <Nav />

      <div style={{ paddingTop: "var(--s7)", maxWidth: 760 }}>
        <h1 className="h1">How RAYA works.</h1>
        <p className="lede" style={{ marginTop: "var(--s4)" }}>
          Reverse search discovers a candidate. Independent face verification
          validates it. Cryptographic evidence preserves what was verified.
          Anchoring makes that evidence tamper-evident.
        </p>

        <section style={{ marginTop: "var(--s8)" }}>
          <Divider label="The pipeline" />
          <ol style={{ listStyle: "none", padding: 0, margin: "var(--s5) 0 0" }}>
            {STAGES.map(([num, title, body]) => (
              <li
                key={num}
                style={{
                  display: "grid",
                  gridTemplateColumns: "40px minmax(0, 1fr)",
                  gap: "var(--s4)",
                  paddingBottom: "var(--s5)",
                }}
              >
                <span className="mono" style={{ color: "var(--ink-quaternary)", fontSize: 11.5 }}>
                  {num}
                </span>
                <div>
                  <h2 className="h3">{title}</h2>
                  <p className="body" style={{ marginTop: 4, fontSize: 13.5 }}>
                    {body}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Limitations" />
          <p className="body" style={{ margin: "var(--s4) 0 var(--s5)", fontSize: 13.5 }}>
            These are not caveats buried in a footer. Overstating what a face
            similarity score means is the main way a system like this becomes
            harmful, so the constraints are stated as plainly as the features.
          </p>
          <div style={{ display: "grid", gap: "var(--s5)" }}>
            {LIMITS.map(([title, body]) => (
              <div key={title}>
                <h3 className="h3">{title}</h3>
                <p className="body" style={{ marginTop: 4, fontSize: 13.5 }}>
                  {body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section style={{ marginTop: "var(--s7)" }}>
          <Divider label="Privacy" />
          <p className="body" style={{ marginTop: "var(--s4)", fontSize: 13.5 }}>
            Face detection and encoding run locally via OpenCV. The face
            embedding never leaves the machine: it is not sent to a third-party
            face API, not written into the evidence bundle, not uploaded to
            IPFS, and not anchored on chain. What is published is hashes, public
            URLs, a similarity score, and the names and file digests of the
            models used.
          </p>
          <p className="body" style={{ marginTop: "var(--s3)", fontSize: 13.5 }}>
            Reverse image search, however, is <em>not</em> private, and RAYA
            does not claim otherwise. Discovery requires an external provider,
            so RAYA sends it a bounded derivative of the input. The original
            bytes are hashed locally first and are never published — not to the
            provider, not to IPFS — but the derivative does leave the machine,
            and its own SHA-256 is recorded so there is no ambiguity about what
            was sent. IPFS is an evidence-preservation layer only; it is never a
            prerequisite for running a search.
          </p>
        </section>

        <div style={{ marginTop: "var(--s8)" }}>
          <Link href="/verify" className="btn">
            Start verification
          </Link>
        </div>
      </div>
    </main>
  );
}
