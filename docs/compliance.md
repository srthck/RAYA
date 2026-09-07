# Requirement coverage

Every requirement mapped to the code that implements it and the test or artifact
that proves it, so a reviewer can check a claim without reading the whole tree.

---

## Core requirements

| # | Requirement | Implementation | Proof |
|---|-------------|---------------|-------|
| 1 | Detect a face in the input image | YuNet (OpenCV Zoo `2023mar`, SHA-256 pinned) | `core/raya/face/detector.py` · `TestDetection` (8 tests) |
| 2 | Encode the face | SFace (`2021dec`), 128-d, cosine | `core/raya/face/encoder.py` · `TestEncoding` (5 tests) |
| 3 | Genuine reverse image search | Google Lens via SerpApi: bounded copy uploaded to `POST /image`, then Lens queried by `image_id`. Original input never published. | `core/raya/search/serpapi.py`, `search/searchcopy.py` · `tests/test_search_copy.py` (25 tests) |
| 4 | Find a matching public social post | Platform classifier + runtime retrieval + independent comparison | `core/raya/candidates/` · `TestFullRun` |
| 5 | No hardcoded results | `NullProvider` raises `SearchProviderNotConfiguredError`; there is no code path that invents a candidate | `core/raya/search/fallback.py` · run without `SERPAPI_KEY` |
| 6 | Blockchain record | Ethereum Sepolia (chain id 11155111), write-once contract | `blockchain/contracts/RayaEvidenceAnchor.sol` · 17 contract tests |
| 7 | Tamper-evident | Canonical JSON → SHA-256 → IPFS → on-chain, with read-back | `core/raya/evidence/` · `TestTamperDetection` · demo case E |
| 8 | Public source code | This repository | — |
| 9 | Run instructions | README "Run it locally" | verified from a clean clone |
| 10 | Documented limitations | Shipped in-product *and* in docs | `docs/limitations.md` · `/about` · `claim` block in every bundle |
| 11 | End-to-end demonstration | Five cases, real pipeline | `python demo/run_demo.py` |
| 12 | Threshold justified empirically | 88 portraits, 23 identities, 3,828 pairs; FMR 0.0000 at 0.40 | `benchmarks/calibrate.py` · `docs/threshold-calibration.md` |
| 13 | Model provenance reproducible | Detector and encoder file SHA-256 in every record | `core/raya/face/*.py` · evidence `verification.detector/encoder` |

### Live execution status

The requirement list above distinguishes **implemented and tested** from
**executed against live third-party services**. As of this revision:

| Stage | Implemented | Tested | Executed live |
|-------|:---:|:---:|:---:|
| Face detection / encoding | yes | yes | yes |
| Bounded search copy | yes | yes | yes |
| SerpApi upload -> `image_id` -> Lens | yes | yes (mock transport) | yes — live Google Lens, 40 results |
| Real social candidate | yes | yes (fixture) | yes — 10 candidates retrieved and compared |
| Independent verification | yes | yes | yes — 8 verified, 2 rejected, best 0.9558 |
| Evidence + canonical hash | yes | yes | yes |
| IPFS pinning | yes | yes | yes — pinned, byte-exact round-trip |
| Ethereum Sepolia deploy + anchor | yes | yes (Hardhat chain) | yes — contract `0x866704a12566dbbF2a86d6dEd0a7cB7238864032` |
| Fresh read-back + integrity | yes | yes | yes — `eth_call` matched the local hash |
| Tamper detection | yes | yes | yes — detected against the on-chain record |

Nothing here is simulated: an unconfigured capability is reported as
UNAVAILABLE or NOT RUN in the UI and omitted from the evidence record, and a
row only reads "yes" once it has actually run against the live service.

The end-to-end live run behind this table:

| | |
|---|---|
| Verification | `VER-20260907-A09ACFB94F1F` |
| Discovered | 40 Google Lens results, 6 social, 4 compared, 3 verified, 1 rejected |
| Match | a public Facebook post, cosine similarity **0.5956** against a 0.40 threshold |
| Evidence SHA-256 | `e6bde70e11fd451ae017efc2e59387582789ca1e1503099f59ffab12bd101577` |
| IPFS | `QmTjMB4HUEPxpKGVhqFC6rfz8uEpQeAu1SX6Hg1V4UV1MG` (Pinata, published) |
| Anchor tx | [`0xf1e436da…76bfa6`](https://sepolia.etherscan.io/tx/0xf1e436da2675ae7d228964e4e37a99600f6eeaf5d35f6014ae3976fda076bfa6), block 11655688 |
| Read-back | fresh `eth_call` returned the same digest; `verifyEvidence()` agreed |
| Tamper | altering `match.similarity` produced `eafc1ed5…836a62`, rejected by the contract |

---

## How requirement 5 is enforced

"No hardcoded results" is the requirement most easily faked, so it is worth
stating exactly how RAYA satisfies it.

There is **no fallback that produces candidates**. The provider registry returns
one of three things:

- `GoogleLensProvider` — live API call, when `SERPAPI_KEY` is set.
- `ReplayProvider` — a *recorded* live response from disk, used by tests and the
  offline demo. Every response is stamped `is_replay: true`; the flag travels
  into the evidence record and the UI labels the run a replay.
- `NullProvider` — raises. It does not return an empty list, because an empty
  list would read as "nothing was found on the web" rather than "no search ran".

Verify it yourself: unset `SERPAPI_KEY` and start a run. The pipeline reaches
face encoding, then stops with `search_unavailable` and an explicit message.

---

## How requirement 7 is enforced

Four independent properties, each tested:

1. **Determinism** — the same logical record always produces the same bytes.
   `TestCanonicalJson` (9 tests) covers key order, whitespace, float precision,
   negative zero, NaN rejection and round-tripping.
   `TestIntegrity` additionally asserts that a run with nothing external to
   compare against is *not* described as "integrity verified".
2. **Immutability of the anchor** — `anchor()` reverts on an existing id, from
   any account, leaving the original intact.
3. **Read-back** — a fresh `eth_call` after confirmation, compared to the local
   hash. Only then is "integrity verified" reported.
4. **Detection** — altering one field changes the digest.

---

## Verification stages

| Stage | Module | Failure is fatal? |
|-------|--------|-------------------|
| 01 Input validation and hashing | `util/imaging.py`, `util/hashing.py` | yes |
| 02 Face detection | `face/detector.py` | yes |
| 03 Face encoding | `face/encoder.py` | yes |
| 04a Bounded search copy | `search/searchcopy.py` | yes |
| 04 Reverse search (upload -> image_id) | `search/` | yes |
| 05 Candidate filtering | `candidates/platforms.py` | yes |
| 06 Independent verification | `candidates/verifier.py` | per candidate |
| 07 Evidence construction | `evidence/schema.py` | yes |
| 08 IPFS storage | `storage/ipfs.py` | **no** |
| 09 Blockchain anchor | `chain/anchor.py` | **no** |
| 10 On-chain read-back | `chain/anchor.py` | **no** |
| 11 Integrity comparison | `evidence/integrity.py` | — |

Stages 08–10 are non-fatal by design: a verified face match and a successful
anchor are separate claims. The run reports `verified_not_anchored` rather than
discarding a real result or overstating a partial one.

---

## Failure states

Every one is a distinct, reported status — none is silently converted into a
success or a generic error.

| Condition | Status | Behaviour |
|-----------|--------|-----------|
| No face | `no_face_detected` | Stops before any search |
| Several faces | `multiple_faces` | Asks which is the subject; will not guess |
| Face too small | `face_unusable` | Refuses to score rather than produce a weak number |
| Undecodable input | `invalid_input` | Typed error to the UI |
| No search key | `search_unavailable` | Says so; invents nothing |
| Provider error/timeout | `search_unavailable` | Provider message surfaced verbatim |
| No results | `no_search_results` | Distinct from "no match" |
| No social sources | `no_social_candidates` | Distinct from "no match" |
| All candidates rejected | `no_verified_match` | Evidence still produced |
| Source unreachable | per-candidate `unreachable` | Run continues; never trusts the provider's thumbnail |
| IPFS unavailable | non-fatal | Local CID, `published: false` |
| Chain unavailable | `verified_not_anchored` | Match preserved, reported as not anchored |
| Nothing external to compare | `verified_not_anchored` | Reported as self-consistent only — never "integrity verified" |
| Hash mismatch | `integrity.failed` | Reported, never suppressed |

---

## Test inventory

```
tests/test_face.py           21   detection, encoding, similarity separation
tests/test_evidence.py       35   canonicalization, hashing, integrity, tamper, CID
tests/test_candidates.py     33   platform classification, SSRF guard, filtering
tests/test_pipeline.py       23   end-to-end runs, failure modes, events, persistence
tests/test_search_copy.py    25   search-copy bounds/determinism, upload, image_id,
                                  expiry, provider failures, credential absence
tests/test_retrieval_cascade.py 15  image_url -> thumbnail -> page metadata cascade
tests/test_contract_abi.py   17   Python ABI vs compiled artifact, bp round-trip
                            ---
                            169   168 passing, 1 skipped, plus 17 Solidity tests
```

Run with `pytest` and `cd blockchain && npm test`.

---

## Independent verification by a reviewer

Nothing below requires trusting this document.

```bash
# 1. The models are the ones claimed
python scripts/fetch_models.py          # verifies pinned SHA-256 of each

# 2. The face layer actually separates people
pytest tests/test_face.py -v

# 3. The pipeline reasons over candidates
python demo/run_demo.py --case C

# 4. Tampering is detected
python demo/run_demo.py --case E

# 5. The evidence hash is reproducible
sha256sum .raya-data/runs/<ID>/evidence.json
cat .raya-data/runs/<ID>/evidence.sha256

# 6. The contract behaves as described
cd blockchain && npm test
```
