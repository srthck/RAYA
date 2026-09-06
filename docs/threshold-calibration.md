# Threshold calibration

RAYA ships a cosine-similarity threshold of **0.40**. This documents how that
number was chosen, on what data, and what it does and does not mean.

Reproduce with:

```bash
python scripts/fetch_calibration_set.py --per-identity 4
python benchmarks/calibrate.py
```

## The dataset

Three fixture photographs are enough to show the encoder separates people at
all. They are nowhere near enough to choose an operating point, so a larger set
was assembled.

| | |
|---|---|
| Source | Wikimedia Commons, public-domain portraits (largely US federal and NASA works) |
| Images | 88 |
| Identities | 23 |
| Genuine pairs (same person) | 128 |
| Impostor pairs (different people) | 3,700 |
| Total comparisons | 3,828 |

LFW, the standard benchmark, is unreachable from this environment, so the set is
built by searching the Commons File namespace by name and keeping only images
where the detector finds **exactly one** face of at least 80 px. Roughly three
quarters of search hits are discarded by that rule.

### Known weakness of the set

The identity label is the filename match, which is imperfect. Spot-checking the
worst genuine pairs in a first pass found two systematic failure modes, both now
filtered at fetch time:

- a Marine photographed aboard a **ship named after** John Kerry;
- a speaker at a **Hillary Clinton campaign rally** who is not Hillary Clinton.

Residual noise is possible. Crucially, label noise here is **conservative**: a
mislabelled image inflates *both* error rates (it puts different people into
genuine pairs and the same person into impostor pairs). It cannot flatter the
result. The measured FNMR should therefore be read as an upper bound.

## Score distributions

| | n | min | p05 | median | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| Genuine | 128 | 0.0762 | 0.2482 | 0.6337 | 0.9625 | 1.0000 |
| Impostor | 3,700 | −0.2245 | −0.0492 | 0.1049 | 0.2557 | **0.3773** |

The number that matters most is the impostor **maximum of 0.3773**. Across 3,700
different-person comparisons, none scored above 0.378.

## Threshold sweep

| Threshold | FMR | FNMR | TPR | False matches | False non-matches |
|---:|---:|---:|---:|---:|---:|
| 0.26 | 0.0465 | 0.0703 | 0.9297 | 172 | 9 |
| 0.30 | 0.0157 | 0.1641 | 0.8359 | 58 | 21 |
| 0.34 | 0.0038 | 0.1719 | 0.8281 | 14 | 22 |
| 0.36 | 0.0014 | 0.1719 | 0.8281 | 5 | 22 |
| 0.38 | 0.0000 | 0.1875 | 0.8125 | 0 | 24 |
| **0.40** | **0.0000** | **0.2031** | **0.7969** | **0** | **26** |
| 0.44 | 0.0000 | 0.2266 | 0.7734 | 0 | 29 |
| 0.50 | 0.0000 | 0.2578 | 0.7422 | 0 | 33 |

- **Equal error rate**: 0.0465 at threshold 0.26.
- **Lowest zero-FMR threshold on this set**: 0.38.
- **Shipped operating point (0.40)**: FMR 0.0000, FNMR 0.2031, TPR 0.7969.

## Why 0.40

RAYA's failure modes are not symmetric. A false **match** publishes an evidence
record asserting that a person appears at a source they may have nothing to do
with, and then anchors it immutably. A false **non-match** produces "no verified
public social source found", which the product already states is not evidence of
absence. The first error is far more damaging, so the threshold is chosen to
drive FMR to zero rather than to minimise total error.

At the equal error rate (0.26) this set produces **172 false matches**. At 0.40
it produces **none**, with 0.023 of margin above the highest impostor score
observed.

0.40 also sits above OpenCV's published SFace operating point of 0.363, which
buys headroom against the extra degradation of candidate images pulled off the
public web — resized and recompressed at least once before RAYA ever sees them.

The cost is recall: about one genuine pair in five is missed at 0.40.

## What the misses actually look like

The lowest genuine scores are not label noise. The worst three pairs all involve
one John Kerry photograph, which was visually confirmed to be correctly
labelled — it is simply a hard image: extreme downward gaze, eyes almost closed,
harsh direct flash and red-eye.

That is a real limitation of the model under pose and lighting, and it is the
concrete form of the caveat stated throughout the product: **face recognition
performance varies with image quality**. A verification against a photograph
like this one will fail, and RAYA will report no verified match rather than
lowering its bar.

## What this calibration is not

- **Not a population-level accuracy claim.** 23 identities of mostly
  high-quality official portraiture is a small, unrepresentative sample.
- **Not a demographic fairness evaluation.** The set is not balanced by age, sex
  or skin tone, and no per-group error rates are computed. Published evaluations
  consistently find face recognition error rates differ across demographic
  groups; nothing here contradicts or measures that.
- **Not transferable.** These numbers describe SFace `2021dec`
  (`0ba9fbfa01b5270c…`) on this set. A different model, or a different class of
  imagery, needs its own calibration.

The threshold is an **empirical operating point for this implementation, model
and test set** — not a proof of identity, and not a universal constant. The
value used in each run is recorded in that run's evidence record so a reader
always knows which standard was applied.
