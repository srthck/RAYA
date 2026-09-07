# RAYA

**Find the source. Verify the face. Anchor the evidence.**

```
INPUT
  |
FACE                    YuNet detection, SFace encoding -- both local
  |
SEARCH COPY             bounded, deterministic derivative -- the original is never published
  |
REVERSE SEARCH          direct upload -> image_id -> Google Lens (SerpApi)
  |
INDEPENDENT VERIFICATION    we re-download and re-compare, ourselves
  |
EVIDENCE                canonical JSON -> SHA-256
  |
IPFS                    content-addressed storage
  |
ETHEREUM SEPOLIA           write-once anchor
  |
READ-BACK               fresh eth_call, compared to the local hash
  |
INTEGRITY VERIFIED
```

Reverse search **discovers** a candidate. Independent face verification
**validates** it. Cryptographic evidence **preserves** what was verified.
Anchoring makes that evidence **tamper-evident**.

> **Discovery isn't proof.** A search engine returning a visually similar image
> is a lead, not a finding. RAYA re-downloads every candidate image and runs its
> own detector and encoder against it. The search engine proposes; RAYA decides
> — and shows you every candidate it rejected.

---

## Demo

Five cases, all running the real pipeline. No API key required.

```bash
python scripts/fetch_models.py     # ~39 MB, checksummed
python demo/run_demo.py
```

| Case | What it shows | Result |
|------|---------------|--------|
| A | Positive — genuine match | `verified` at similarity **0.8140** |
| B | Hard negative — different person | `rejected` at **0.1353** |
| C | Many candidates — one passes | 5 candidates → verified / rejected / not-social / no-face / unreachable |
| D | No face — stops early | `no_face_detected`, no search performed |
| E | Tamper — one field altered | **TAMPERING DETECTED** |

Case C is the one to look at: it produces five different outcomes in a single
run, which is what distinguishes a pipeline that reasons over candidates from
one that returns the first result.

The demo serves candidate images from a local HTTP server and replays a recorded
search fixture, because social platforms block automated fetching and the search
API is paid. Everything else is real: real decoding, real detection, real
encoding, real TCP downloads, real hashing. Replayed runs are stamped
`is_replay: true` in the evidence and labelled as replays in the UI.

---

## Run it locally

**Requires** Python 3.10+, Node 18+.

```bash
git clone <repo> && cd raya

# 1. Backend
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on Unix
pip install -r requirements.txt
python scripts/fetch_models.py

# 2. Configure
cp .env.example .env              # see "Configuration" below

# 3. API  (port 8000 -- the frontend proxy expects this)
PYTHONPATH="core:apps/api" uvicorn raya_api.main:app --port 8000
#   Windows PowerShell:
#   $env:PYTHONPATH="core;apps/api"; uvicorn raya_api.main:app --port 8000

# 4. Frontend
cd apps/web && npm install && npm run dev
```

Open <http://localhost:3000>.

Without credentials RAYA still runs and reports honestly: face detection and
encoding work, and the run stops at the search stage saying search is
unavailable. **It never fabricates candidates to fill the gap.**

### Configuration

| Variable | Needed for | Without it |
|----------|-----------|------------|
| `SERPAPI_KEY` | Real reverse image search | Run stops: "search unavailable" |
| `PINATA_JWT` | Publishing evidence to IPFS | Local CID computed, marked `published: false` |
| `CONTRACT_ADDRESS`, `DEPLOYER_PRIVATE_KEY` | Anchoring on chain | Match still verified, reported "not anchored" |

Every degraded state is surfaced in the UI and recorded in the evidence. There
is no silent fallback.

> **What leaves the machine:** RAYA hashes the original input locally and never
> republishes it. To search, it derives a separate bounded copy (deterministic,
> under SerpApi's 500 KB upload limit), uploads *that* directly for an
> `image_id`, and queries Lens by id. Both objects are hashed and recorded, so
> the evidence is unambiguous about what was sent. Reverse image search is still
> not private — the derivative is processed by a third party. The face embedding
> never leaves the machine at all.

### IPFS (evidence preservation)

IPFS stores the finished evidence record. It is **not** a prerequisite for
search — nothing is published in order to make an image searchable.

```bash
# Option A: a pinning service (recommended for a real run)
PINATA_JWT=...            # evidence is pinned; CID resolves publicly

# Option B: a local node
IPFS_PROVIDER=kubo        # requires `ipfs daemon` on 127.0.0.1:5001

# Option C: nothing configured
# A genuine CIDv1 is computed and the bundle written to .raya-data/ipfs,
# but published=false and the UI shows IPFS as UNAVAILABLE. Nothing is
# claimed to be on the network that is not.
```

---

## Blockchain

**Ethereum Sepolia**, chain id **11155111**, RPC `https://ethereum-sepolia-rpc.publicnode.com`,
explorer `https://sepolia.etherscan.io`.

```bash
cd blockchain
npm install
npm test                                   # contract test suite
npm run deploy                             # deploys, then round-trips a record
# copy the printed CONTRACT_ADDRESS into .env
```

The contract ([`RayaEvidenceAnchor.sol`](blockchain/contracts/RayaEvidenceAnchor.sol))
is deliberately small, and what it *doesn't* have is the design:

- **No owner, no admin, no pause, no upgrade path.** A mutable anchor is not an
  anchor.
- **Write-once.** `anchor()` reverts on an existing id rather than overwriting.
- **No token, no NFT, no DAO.** Anchoring is open; the record stores who
  submitted it.
- **Only hashes.** No image, no face, no biometric template is ever written on
  chain. That data is public and permanent — the boundary is not negotiable.

**The read-back is the point.** A submitted transaction proves nothing: it can
revert, be dropped, or land with different data. RAYA waits for the receipt,
checks `status == 1`, then makes a *fresh* `eth_call` and compares the stored
hash to the locally computed one. Only that comparison produces the words
"integrity verified".

---

## Architecture

The pipeline talks to interfaces, never to vendors:

```
ReverseSearchProvider          FaceDetector -> YuNet
  |- GoogleLensProvider        FaceEncoder  -> SFace
  |- ReplayProvider            EvidenceStore -> Pinata | Kubo | Local
  \- NullProvider              BlockchainAnchor -> Core
```

```
raya/
  core/raya/          face/ search/ candidates/ evidence/ chain/ storage/ pipeline/
  apps/api/           FastAPI + SSE event stream
  apps/web/           Next.js workspace
  blockchain/         Solidity + Hardhat
  tests/              126 tests
  demo/               five demonstration cases
  docs/               architecture, limitations, threat model, compliance
```

**The frontend has no simulated progress.** Every stage, candidate tile and hash
on screen is rendered in response to an SSE event the backend actually emitted
(`core/raya/events.py`). Because the event log is persisted, `/replay/{id}` is a
*recording* played at its original pacing — not a scripted animation.

Full detail: [docs/architecture.md](docs/architecture.md).

---

## Verify the evidence yourself

Every run produces a canonical record whose bytes are byte-reproducible.

```bash
curl -sO http://localhost:8000/v1/verifications/<ID>/evidence
sha256sum evidence.json      # must equal the anchored hash
```

`evidence.json` is the canonical serialization — sorted keys, no insignificant
whitespace, fixed float precision (RFC 8785 in shape). `evidence.pretty.json` is
for reading and will *not* match. Two parties holding the same logical record
compute the same digest; that is the entire basis of the tamper-evidence claim.

---

## Tests

```bash
pytest                        # 126 tests (1 skipped)
cd blockchain && npm test     # contract tests
```

Nothing in the verification path is mocked. `tests/test_pipeline.py` runs the
real models against real photographs served over a real HTTP server; only the
paid search API is replaced, with a recorded fixture.

The measured baseline the whole product rests on, from 88 public-domain
portraits across 23 identities (3,828 pairs — `python benchmarks/calibrate.py`):

| | Value |
|---|---|
| Highest impostor score across 3,700 pairs | **0.3773** |
| False match rate at 0.40 | **0.0000** |
| False non-match rate at 0.40 | 0.2031 |
| Equal error rate | 0.0465 at threshold 0.26 |

0.40 is set to drive false matches to zero, not to minimise total error: a false
match publishes and anchors a claim about a person, whereas a false non-match
says "no verified source found", which the product already states is not
evidence of absence.

Method and caveats: [docs/threshold-calibration.md](docs/threshold-calibration.md).
It is an empirical operating point for this model and set — not a universal
constant, and not proof of identity.

---

## Limitations

Stated as plainly as the features, because overstating a face similarity score
is the main way a system like this becomes harmful.

- **A similarity score is not an identity.** RAYA reports that two faces scored
  above a stated threshold under a named model. It never attaches a name, and
  the evidence record itself carries this disclaimer.
- **Error rates vary with image quality and across demographic groups.** Blur,
  resolution, pose and lighting all shift scores. A single number is not a
  uniform confidence.
- **The threshold is a policy choice.** 0.40 buys margin against recompressed
  web images. It is recorded in every bundle so a reader knows what applied.
- **Coverage is bounded by the search provider.** RAYA can only verify what the
  search returns. Absence of a match is *not* evidence of absence.
- **Some sources cannot be retrieved.** Platforms block automated fetching; such
  candidates are recorded as discovered-but-unretrievable, never accepted on the
  provider's word.
- **An anchor proves integrity, not truth.** It shows a hash existed at a time
  and has not changed — not that the source post is authentic.

Full list: [docs/limitations.md](docs/limitations.md) ·
Threat model: [docs/threat-model.md](docs/threat-model.md)

---

## Privacy

Face detection and encoding run locally via OpenCV. No face image or embedding
is sent to a third-party face API, written into the evidence bundle, uploaded to
IPFS, or anchored on chain. What is published is hashes, public URLs, a
similarity score, and the names of the models used.

This is enforced by a test, not just a promise: `test_evidence_contains_no_biometric_data`
walks the record and fails if any numeric array long enough to be an embedding
appears anywhere in it.

---

## Requirement coverage

| Requirement | Implementation | Where |
|-------------|---------------|-------|
| Detect face | YuNet (OpenCV Zoo, pinned) | `core/raya/face/detector.py` |
| Encode face | SFace, 128-d, cosine | `core/raya/face/encoder.py` |
| Genuine reverse search | Google Lens via SerpApi | `core/raya/search/serpapi.py` |
| Matching social post | Runtime retrieval + classification | `core/raya/candidates/` |
| No hardcoded results | `NullProvider` fails loudly instead | `core/raya/search/fallback.py` |
| Blockchain record | Ethereum Sepolia, write-once contract | `blockchain/contracts/` |
| Tamper-evident | Canonical JSON → SHA-256 → on-chain | `core/raya/evidence/` |
| Run instructions | This file | above |
| Limitations | Documented and shipped in-product | `docs/limitations.md` |

Detailed mapping: [docs/compliance.md](docs/compliance.md).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModelMissingError` on startup | ONNX models not fetched | `python scripts/fetch_models.py` |
| Run stops at `search_unavailable` | No `SERPAPI_KEY` | Add the key to `.env`. This is correct behaviour, not a bug — RAYA never fabricates candidates. |
| `Search copy is N KB; the provider limit is 500 KB` | Input produced an oversized derivative | Should not occur; `benchmarks/calibrate.py` and the test suite bound this. File an issue with the image dimensions. |
| IPFS shows `UNAVAILABLE` with a CID present | No pinning service configured | Set `PINATA_JWT`, or run a local `ipfs daemon` with `IPFS_PROVIDER=kubo`. |
| `RPC reports chain id X, but CHAIN_ID is configured as 11155111` | Pointing at the wrong network | Check `CHAIN_RPC_URL`. RAYA refuses to anchor to an unexpected chain rather than writing to the wrong one. |
| `insufficient ETH for gas` | Unfunded deployer key | Fund the address from a Sepolia faucet (Google Cloud, Alchemy or Chainlink). |
| `this verification id is already anchored` | Re-anchoring an existing run | Expected: records are write-once by design. |
| Frontend can't reach the API | API not on port 8000 | `NEXT_PUBLIC_API_URL` is resolved at **build** time — set it before `npm run build`, not before `npm start`. |
| No faces found in a large photo | — | Detection is bounded to 1024 px on the long edge; very small faces in very large images may be missed. |
| Zero candidates from a live search | Genuinely no indexed matches | Reported as `no_search_results`, distinct from `no_verified_match`. |

---

## Licence

MIT — see [LICENSE](LICENSE).
