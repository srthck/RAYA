"use client";

/**
 * Landing page.
 *
 * The page is the argument. It states what RAYA does in three lines, then walks
 * the reader through the pipeline one idea at a time, ending on the sentence
 * that separates this from "I called an image API and stored the URL on a
 * blockchain": discovery isn't proof.
 *
 * No product nav, no pricing, no feature grid.
 */

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";

import { Nav } from "@/components/Nav";

const HERO_LINES = ["Discovery", "isn't proof."];

const BEATS = [
  {
    lead: "One image.",
    body: "You give RAYA a photograph. It is hashed before anything else happens, so every later claim refers to exactly these bytes.",
  },
  {
    lead: "One face.",
    body: "A local detector finds the face and a local encoder turns it into a vector. Neither the photograph nor the vector leaves the machine at this step.",
  },
  {
    lead: "The public web.",
    body: "A real reverse image search returns real candidates. RAYA filters them down to public social media sources.",
  },
  {
    lead: "Discovery isn't proof.",
    body: "So RAYA re-downloads each candidate image itself and compares faces with its own models. The search engine proposes. RAYA decides — and shows you every candidate it rejected.",
    emphasis: true,
  },
  {
    lead: "Evidence gets a fingerprint.",
    body: "What was verified becomes a canonical record with a SHA-256 digest. Same record, same bytes, same hash — anywhere, by anyone.",
  },
  {
    lead: "The fingerprint gets anchored.",
    body: "The digest goes onto Core Testnet2 and is read back from the chain and compared. Only then does RAYA say the evidence is intact.",
  },
];

export default function Landing() {
  const reduce = useReducedMotion();

  const rise = (delay = 0) => ({
    initial: reduce ? {} : { opacity: 0, y: 18 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: "-80px" },
    transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] as const, delay },
  });

  return (
    <main className="shell">
      <Nav minimal />

      {/* ---- hero ---------------------------------------------------- */}
      {/* Decorative entrance only. Nothing here reflects pipeline state --
          once a verification starts, real SSE events are the only source of
          truth for what is on screen. */}
      <section
        style={{
          padding: "clamp(64px, 15vh, 176px) 0 clamp(64px, 12vh, 132px)",
          maxWidth: 1140,
        }}
      >
        <motion.p
          className="label"
          initial={reduce ? {} : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55 }}
          style={{ letterSpacing: "0.36em", marginBottom: "var(--s5)" }}
        >
          RAYA · Visual evidence verification
        </motion.p>

        {/* The display type is near-black. The blue lives in the environment,
            never in the headline. */}
        {HERO_LINES.map((line, index) => (
          <motion.h1
            key={line}
            className="display"
            initial={reduce ? {} : { opacity: 0, y: 24, filter: "blur(12px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{
              duration: 0.95,
              delay: 0.1 + index * 0.14,
              ease: [0.16, 1, 0.3, 1],
            }}
            style={{ color: "var(--ink)" }}
          >
            {line}
          </motion.h1>
        ))}

        <motion.p
          className="lede"
          style={{ marginTop: "var(--s6)", maxWidth: 560 }}
          initial={reduce ? {} : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.42, ease: [0.16, 1, 0.3, 1] }}
        >
          RAYA discovers the source, verifies the face independently, and anchors
          the evidence.
        </motion.p>

        <motion.div
          style={{
            marginTop: "var(--s7)",
            display: "flex",
            gap: "var(--s3)",
            flexWrap: "wrap",
          }}
          initial={reduce ? {} : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.56, ease: [0.16, 1, 0.3, 1] }}
        >
          <Link href="/verify" className="btn">
            Start verification
          </Link>
          <Link href="/about" className="btn btn-ghost">
            How it works
          </Link>
        </motion.div>

        <motion.p
          className="mono"
          initial={reduce ? {} : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.9, delay: 0.72 }}
          style={{
            marginTop: "var(--s8)",
            fontSize: 11,
            color: "var(--ink-tertiary)",
            letterSpacing: "0.08em",
          }}
        >
          YuNet · SFace · SHA-256 · IPFS · Core Testnet2
        </motion.p>
      </section>

      <hr className="rule" />

      {/* ---- the pipeline, in words ---------------------------------- */}
      <section style={{ padding: "clamp(64px, 11vh, 140px) 0" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "clamp(56px, 9vh, 112px)" }}>
          {BEATS.map((beat, index) => (
            <motion.div
              key={beat.lead}
              {...rise()}
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr)",
                gap: "var(--s4)",
                maxWidth: 900,
              }}
            >
              <div
                className="mono"
                style={{ color: "var(--ink-quaternary)", fontSize: 11.5 }}
              >
                {String(index + 1).padStart(2, "0")}
              </div>
              <h2
                className="h1"
                style={{
                  maxWidth: 780,
                  color: beat.emphasis ? "var(--ink)" : "var(--ink)",
                }}
              >
                {beat.lead}
              </h2>
              <p
                className="lede"
                style={{ maxWidth: 620, marginTop: "var(--s1)" }}
              >
                {beat.body}
              </p>
            </motion.div>
          ))}
        </div>
      </section>

      <hr className="rule" />

      {/* ---- what it does not claim ---------------------------------- */}
      <motion.section {...rise()} style={{ padding: "clamp(56px, 10vh, 112px) 0" }}>
        <p className="label">What RAYA does not claim</p>
        <p
          className="h2"
          style={{ marginTop: "var(--s4)", maxWidth: 780, fontWeight: 460 }}
        >
          A similarity score is not an identity. RAYA reports that two faces
          scored above a stated threshold under a named model — never that it
          knows who someone is.
        </p>
        <p className="body" style={{ marginTop: "var(--s4)", maxWidth: 620 }}>
          Face recognition error rates vary with image quality and across
          demographic groups. Every verification carries that caveat inside the
          evidence record itself, not just in the documentation.
        </p>
      </motion.section>

      <hr className="rule" />

      {/* ---- close --------------------------------------------------- */}
      <motion.section
        {...rise()}
        style={{ padding: "clamp(72px, 14vh, 176px) 0 clamp(80px, 16vh, 200px)" }}
      >
        <h2 className="display" style={{ maxWidth: 1000, color: "var(--ink)" }}>
          Verify it
          <br />
          yourself.
        </h2>
        <p className="lede" style={{ marginTop: "var(--s6)", maxWidth: 560 }}>
          RAYA discovers the source, verifies the face independently, and anchors
          the evidence.
        </p>
        <div style={{ marginTop: "var(--s7)" }}>
          <Link href="/verify" className="btn">
            Start verification
          </Link>
        </div>
      </motion.section>

      <footer
        style={{
          borderTop: "1px solid var(--line)",
          padding: "var(--s5) 0 var(--s7)",
          display: "flex",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "var(--s3)",
        }}
      >
        <span className="mono" style={{ color: "var(--ink-quaternary)" }}>
          YuNet · SFace · SHA-256 · IPFS · Core Testnet2
        </span>
        <Link href="/about" className="mono" style={{ color: "var(--ink-tertiary)" }}>
          Limitations →
        </Link>
      </footer>
    </main>
  );
}
