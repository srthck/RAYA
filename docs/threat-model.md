# Threat model

What could make RAYA produce a wrong or misleading result, and what stops it.

Each entry names the mitigation and, where one exists, the test that holds it in
place. Residual risk is stated rather than waved away.

---

## T1 — The search engine returns a visually similar person

**The core threat.** Reverse image search optimises for visual similarity, not
identity. A lookalike, a sibling, or someone with similar framing and lighting
will legitimately appear in results.

**Mitigation.** The search provider gets no vote. RAYA re-downloads the
candidate image and runs its own detector and encoder, and a candidate is
accepted only if *that* comparison clears the threshold.

**Evidence it works.** Demo case B: the search returns a different person, and
RAYA rejects it at 0.1353 against a 0.40 threshold. Demo case C mixes a
lookalike with the true source; only the true source passes.
`test_the_lookalike_is_rejected_by_our_own_comparison`.

**Residual risk.** Two genuinely similar-looking people can score above
threshold. This is why RAYA reports a *visual match*, never an identity.

---

## T2 — Evidence altered after verification

**Mitigation.** The record is canonicalized and hashed; the digest is anchored
in a write-once contract and read back with a fresh call. Any change to any
field produces a different digest.

**Evidence it works.** Demo case E alters `match.similarity` from 0.81405 to
0.96405 and the hash diverges completely. `TestTamperDetection`, and on the
contract side `detects a tampered evidence hash`.

**Residual risk.** None for detection — but the anchor proves the record is
unchanged, not that it was true when written.

---

## T3 — The anchor itself is overwritten

**Mitigation.** `anchor()` reverts with `AlreadyAnchored` on an existing id.
There is no owner, no admin, no upgrade path, so no key exists that could
rewrite history.

**Evidence it works.** `refuses to overwrite an existing record`, `refuses an
overwrite from a different account too`, `leaves the original intact after a
rejected overwrite`.

**Residual risk.** Anchoring is open, so anyone can anchor anything. The record
stores `submitter`; readers must judge the source. RAYA does not claim an anchor
implies endorsement.

---

## T4 — A transaction is submitted but does not land as intended

**Mitigation.** RAYA never treats "submitted" as success. It simulates the call
first (catching reverts for free), waits for the receipt, checks `status == 1`,
then makes a **fresh `eth_call`** and compares the stored hash against the local
one. Only that comparison yields "integrity verified".

**Residual risk.** A chain reorg after confirmation. The block number and hash
are recorded so a later re-check can detect it; `/v1/verifications/{id}/integrity`
re-reads the chain on demand.

---

## T5 — Server-side request forgery via candidate URLs

**Real, not theoretical.** RAYA fetches URLs chosen by a third-party API in
response to user-supplied input.

**Mitigation.** Every URL is resolved and checked against private address space
before the request, and **again on the final URL after redirects** — a public
hostname can resolve to `127.0.0.1` or a cloud metadata address, and a redirect
chain can start public and end private. Only `http`/`https` are allowed.
Response size is capped during streaming, not merely trusted from
`Content-Length`, and non-image content types are refused.

**Evidence it works.** `TestSsrfGuard` covers loopback, link-local metadata
(`169.254.169.254`), RFC1918, IPv6 loopback, and non-HTTP schemes.

**Residual risk.** DNS rebinding between the check and the connection. Mitigating
fully requires pinning the resolved address into the connection, which httpx does
not expose cleanly.

---

## T6 — Path traversal through a verification id

**Mitigation.** Run ids reach `RunStore` from URLs and become filesystem paths.
Ids are validated against an alphanumeric-plus-`-_` allowlist; `load`, `exists`
and `asset` all return "not found" rather than raising or escaping. Asset
filenames additionally reject separators and `..`.

**Evidence it works.** `test_path_traversal_is_refused`.

---

## T7 — A source disappears after verification

**Mitigation.** The evidence records the post URL, the image URL, the final
fetched URL, the SHA-256 of the retrieved bytes, dimensions and MIME type. If
the post is deleted, the record still documents what was retrieved and when.

**Residual risk.** RAYA does not archive the source image itself, so the bytes
cannot be re-examined later — only their hash compared. Archiving third-party
images has copyright and privacy consequences that were judged worse than this
gap.

---

## T8 — A false match from the face model

**Mitigation.** A threshold with deliberate margin (0.40 against SFace's
published 0.363), a minimum face size, quality metrics reported alongside every
score, mandatory landmark alignment, and — most importantly — no absolute
identity claim anywhere in the product or the record.

**Residual risk.** Irreducible. Face recognition has a non-zero false match rate
that varies with image quality and across demographic groups. This is why the
`claim` block ships inside every bundle.

---

## T9 — The provider fabricates or is compromised

**Mitigation.** A compromised provider can only propose candidates; it cannot
make one verify. To force a false positive it would have to supply an image that
genuinely matches the subject's face under our models — at which point the match
is real, whatever the provider's motive.

**Residual risk.** A provider can *withhold* results, producing a false negative.
Undetectable from our side, which is why absence of a match is explicitly not
treated as evidence of absence.

---

## T10 — Biometric data leaking into public storage

**Mitigation.** Embeddings never leave the process. The evidence schema has no
field for them; `FaceEmbedding.to_public_dict()` exposes only model name and
dimensionality. Bundles carry hashes, URLs, scores and model names.

**Evidence it works.** `test_evidence_contains_no_biometric_data` walks the
record structurally and fails on any numeric array long enough to be an
embedding — a substring check would have passed accidentally on the
`embedding_exported` flag, so the test is written to catch the real thing.

**Residual risk.** The *input image* is published to IPFS to make it searchable
at all. Irreducible given a URL-based search API, and stated in the UI before a
run.

---

## T11 — Misuse of the tool itself

RAYA performs face search against public social media. That is dual-use: it
supports provenance and journalism, and it could support stalking.

**Mitigations in the product.** No identity claims, no name resolution, no
profile enumeration, no bulk or batch mode, no stored gallery of faces to search
against, no authentication-bypassing retrieval. Every run is a single image
against public search results.

**Residual risk.** Real. The design deliberately withholds the features that
would make it an effective surveillance tool — RAYA is built to verify a
specific claim about a specific image, not to find people.

---

## Out of scope

- **Manipulated or AI-generated inputs.** RAYA is not a deepfake detector.
- **Authentication and multi-tenancy.** The API is unauthenticated and intended
  for local or trusted-network use.
- **Denial of service.** Concurrency and size caps exist to be a polite client,
  not to withstand attack.
- **Key management.** `DEPLOYER_PRIVATE_KEY` is a testnet key in a `.env` file.
  Never put a key holding real value there.
