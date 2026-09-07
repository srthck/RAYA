# Architecture

## The thesis in one diagram

```
                              RAYA
                                |
                ----------------+----------------
                |                               |
         EVIDENCE ENGINE                 WORKSPACE
           FastAPI                        Next.js
                |                               |
           ORCHESTRATOR  <------- SSE ----------+
                |
      ----------+----------
      |         |         |
     FACE     SEARCH   EVIDENCE
    YuNet    Lens API   SHA-256
    SFace       |          |
      |         |         IPFS
      ----------+----------
                |
          ETHEREUM SEPOLIA
                |
          ON-CHAIN READ-BACK
                |
         INTEGRITY VERIFIED
```

Three layers, deliberately separated:

- **DISCOVER** — a reverse image search returns candidates. Its output is a
  lead, never a finding.
- **VERIFY** — RAYA re-downloads each candidate and compares faces with its own
  models. This is the only thing allowed to decide a match.
- **ANCHOR** — the result becomes a canonical record, hashed, stored and
  anchored, then read back and compared.

Keeping DISCOVER and VERIFY apart is the whole design. Collapsing them —
trusting the search engine's notion of similarity — is what makes the difference
between an evidence system and an API wrapper.

---

## Dependency inversion

The orchestrator depends on interfaces, never on vendors. Swapping a provider
means writing one class; no orchestration code changes.

| Interface | Implementations | File |
|-----------|----------------|------|
| `ReverseSearchProvider` | `GoogleLensProvider`, `ReplayProvider`, `NullProvider` | `core/raya/search/` |
| `FaceDetector` | `YuNetDetector` | `core/raya/face/detector.py` |
| `FaceEncoder` | `SFaceEncoder` | `core/raya/face/encoder.py` |
| `EvidenceStore` | `PinataStore`, `KuboStore`, `LocalStore` | `core/raya/storage/ipfs.py` |
| `BlockchainAnchor` | `CoreAnchor` | `core/raya/chain/anchor.py` |

`NullProvider` deserves note: it is not a stub that returns empty results, it is
one that **fails loudly**. A missing API key produces "search not configured",
never an empty list that would read as "nothing was found on the web".

---

## The eleven stages

Implemented in `core/raya/pipeline/orchestrator.py`.

| # | Stage | What happens | Can fail without ending the run |
|---|-------|--------------|--------------------------------|
| 01 | Input | Validate, decode, EXIF-orient, SHA-256 | no |
| 02 | Detection | YuNet; 0 faces stops, >1 asks | no |
| 03 | Encoding | Align + SFace 128-d embedding | no |
| 04a | Search copy | Build a bounded, deterministic derivative | no |
| 04 | Search | Upload the copy, search by `image_id` | no |
| 05 | Filtering | Platform classification | no |
| 06 | Verification | Retrieve, detect, encode, compare — per candidate | per candidate |
| 07 | Evidence | Canonical JSON + SHA-256 | no |
| 08 | IPFS | Content-addressed storage | **yes** |
| 09 | Anchor | Ethereum Sepolia transaction | **yes** |
| 10 | Read-back | Fresh `eth_call` | **yes** |
| 11 | Integrity | Compare local vs on-chain vs IPFS | — |

**Failures degrade, they never fabricate.** Stages 08–10 can fail while the run
keeps its verified face match; the result says `verified_not_anchored` and the
specific reason lands in `result.errors`. A face match and a blockchain anchor
are separate claims, and a failure in the second must not weaken or strengthen
the first.

### The search copy, and why the original is never published

SerpApi's `POST /image` endpoint accepts the image bytes directly and returns an
`image_id` that the Lens engine takes in place of `url`. So nothing has to be
publicly hosted to be searchable.

What is uploaded is a *derivative*, never the original:

| Object | Hash | Leaves the machine? |
|--------|------|--------------------|
| Original input | `input.sha256` | no — hashed locally, never republished |
| Bounded search copy | `search_copy.sha256` | yes — uploaded to the provider |

The copy is produced deterministically (`search/searchcopy.py`) by walking a
fixed edge ladder then a fixed quality ladder, so the same input always yields
byte-identical output and the recorded digest is reproducible. It must fit
SerpApi's 500 KB upload ceiling; a 4.5 MB portrait comes out at ~316 KB.

Keeping the two apart is what lets the evidence say exactly what was sent
without muddling it with the canonical input. IPFS is an evidence-preservation
layer only — never a prerequisite for search.

### Why detection is bounded to 1024 px

The fixed-input-shape YuNet 2023mar graph stops returning detections at very
large resolutions — a 2687×3356 portrait yields nothing at native size and one
face at 1024. Detection runs on a bounded copy and coordinates are scaled back,
so alignment still crops from full-resolution pixels. This is covered by
`test_detects_on_a_large_image`.

---

## The event log

`core/raya/events.py` is an append-only log with fan-out. Two features depend on
it, and both matter:

1. **The frontend renders from it over SSE.** There is no `setTimeout` progress
   anywhere in the UI. If a stage is on screen, the backend reached it.
2. **`/replay/{id}` re-emits the persisted log** at its original relative
   pacing, through the *same reducer* that drives the live view
   (`apps/web/lib/usePipeline.ts`). Replay is a recording, not an animation —
   it cannot show a stage the original run did not reach.

A late subscriber receives the full backlog before any live event, so a browser
that connects mid-run still renders earlier stages.

---

## Evidence determinism

The tamper-evidence claim rests entirely on byte-reproducibility.

`core/raya/util/canonical.py` follows RFC 8785 in shape: keys sorted by code
point, no insignificant whitespace, UTF-8 with non-ASCII emitted literally,
floats rounded to a fixed precision then rendered with shortest-round-trip
repr, NaN and Infinity rejected.

`EvidenceBundle` freezes one canonical byte string at creation. Everything
downstream — the IPFS upload, the anchor, the export — refers to that same
string, so a later change to the serializer cannot silently change the answer.

`FLOAT_PRECISION` is part of the schema contract; changing it changes every
hash, so it moves only with `schema_version`.

**What is never in the record:** face images, embeddings, names. The bundle goes
to IPFS, which is public and permanent. `test_evidence_contains_no_biometric_data`
walks the record structurally and fails if any numeric array long enough to be
an embedding appears.

---

## The contract

`RayaEvidenceAnchor.sol` — no owner, no admin, no pause, no upgrade path,
write-once, hashes only. Its absences are the design; see the README.

The **read-back** (stage 10) is deliberately a fresh `eth_call` rather than a
read of the transaction receipt or its logs: those are what we submitted.
Querying contract state is what proves the chain holds the value.

---

## Frontend

Next.js App Router, TypeScript, a custom token-based design system (no utility
framework), Framer Motion for animation that explains rather than decorates.

| Route | Purpose |
|-------|---------|
| `/` | The argument, told as a scroll |
| `/verify` | Three-column workspace: where are we / what is happening / what technically happened |
| `/evidence/[id]` | Inspector, live integrity re-check, tamper test, export |
| `/replay/[id]` | Recorded run, replayed |
| `/about` | Pipeline and limitations, given equal weight |

The API is proxied under `/api` via `next.config.mjs` rewrites so the browser
makes same-origin requests — `EventSource` has no CORS escape hatch, and the
stream carries the entire live UI. Note the destination is resolved at **build**
time.

---

## Testing

126 Python tests plus 17 Solidity tests. Nothing in the verification path is
mocked: `tests/test_pipeline.py` runs the real models against real photographs
served over a real HTTP server on an ephemeral port. Only the paid search API is
replaced, with a recorded fixture.

`tests/test_contract_abi.py` checks the hand-written Python ABI against the
compiled Hardhat artifact — signatures, output types, state mutability, event
indexing and struct field order — so the two cannot drift.
