# Benchmarks

Measured, not asserted. Reproduce with:

```bash
python benchmarks/bench.py --runs 25
```

## Stage costs

25 runs after warm-up, 576×720 input, Windows 11, Python 3.10, OpenCV 5.0.0,
CPU only (no GPU, no ONNX Runtime acceleration).

| Stage | Median | Mean | p95 | Max |
|-------|-------:|-----:|----:|----:|
| SHA-256 of input bytes | 0.07 ms | 0.07 ms | 0.08 ms | 0.09 ms |
| Decode + validate | 2.84 ms | 2.86 ms | 3.36 ms | 3.46 ms |
| Face detection (YuNet) | 18.12 ms | 18.39 ms | 20.10 ms | 25.04 ms |
| Alignment (112×112 crop) | 0.05 ms | 0.05 ms | 0.06 ms | 0.06 ms |
| Face encoding (SFace) | 8.46 ms | 8.60 ms | 10.01 ms | 11.05 ms |
| Similarity comparison | 0.00 ms | 0.01 ms | 0.01 ms | 0.02 ms |
| Evidence canonicalize + hash | 0.05 ms | 0.06 ms | 0.06 ms | 0.16 ms |
| **Full local path, 1 candidate** | **58.38 ms** | **60.62 ms** | **71.58 ms** | **71.58 ms** |

Model load costs ~250 ms once at process start. Models are constructed once and
shared, which is why the API builds them at startup rather than per request.

## What this means

**The local pipeline is not the bottleneck.** A full verification against one
candidate — decode, detect, encode, decode, detect, encode, compare, hash —
takes under 60 ms. A real run is dominated by network latency:

| Stage | Typical | Why |
|-------|---------|-----|
| Reverse image search | 2–10 s | Third-party API round trip |
| Candidate retrieval | 0.2–3 s each | Downloading from social CDNs |
| IPFS pin | 1–5 s | Pinning service |
| Chain anchor + confirmation | 3–15 s | Block time on Core Testnet2 |

So the design choices that matter for responsiveness are about concurrency and
not blocking the event loop, not about model speed:

- Candidate retrieval runs with bounded concurrency (default 4) — capped to stay
  a polite client of the sites fetched from, not because CPU is scarce.
- Every CPU-bound call (decode, detect, encode) is dispatched with
  `asyncio.to_thread`, so the SSE stream keeps flowing during a run.
- `web3.py` is synchronous, so the whole submit-and-wait is moved off the event
  loop too.

## Cosine similarity separation

The measurement the product actually depends on, from `tests/fixtures`:

| Pair | Similarity | Against 0.40 |
|------|-----------:|--------------|
| Same person, different photograph | 0.7931 | pass |
| Different people | 0.2309 | reject |
| Different people | 0.1488 | reject |
| Identical image | 1.0000 | pass |

Separation between the same-person score and the nearest different-person score
is **0.56**. `test_the_threshold_sits_in_a_real_margin` fails the build if that
margin falls below 0.3.

These are three public-domain official portraits — a sample far too small to
estimate error rates from. It demonstrates that the pipeline discriminates; it
does **not** establish an accuracy figure, and none is claimed. See
[limitations.md](limitations.md).

## Contract gas

From `npx hardhat test`:

| Operation | Gas |
|-----------|----:|
| `anchor()` | 253,501 |

Reads (`getRecord`, `verifyEvidence`, `isAnchored`) are `view` and cost nothing
off-chain. The test asserts anchoring stays under 300,000 gas, so a change that
makes anchoring expensive fails the build.

Cost is dominated by one `string` (the IPFS CID) and three `bytes32` slots.
Storing the CID on chain is a deliberate trade: it means the anchor alone is
enough to locate the evidence, without a separate index.

## Frontend

`npm run build`, Next.js 15.5.25:

| Route | Route JS | First load |
|-------|---------:|-----------:|
| `/` | 2.44 kB | 144 kB |
| `/about` | 4.25 kB | 110 kB |
| `/verify` | 5.55 kB | 155 kB |
| `/evidence/[id]` | 3.49 kB | 149 kB |
| `/replay/[id]` | 1.48 kB | 151 kB |

Shared baseline is 103 kB. There is no UI framework, no icon library and no CSS
framework — the design system is ~450 lines of CSS custom properties. Framer
Motion is the only sizeable dependency, and it earns its place: the motion
explains the pipeline rather than decorating it.
