# Limitations

What RAYA cannot do, stated as plainly as what it can. Overstating what a face
similarity score means is the primary way a system like this causes harm, so
these are not footnotes — several of them are enforced in code, and the central
one ships inside every evidence record.

---

## 1. A similarity score is not an identity

RAYA reports that a face in the input image and a face in a retrieved source
image scored at or above a stated threshold under a named model. That is a
measurement, not a determination of who someone is.

RAYA never attaches a name to a face, never returns a "confidence that this is
person X", and never expresses similarity as a percentage — a percentage reads
as a probability of identity, which is exactly the claim being avoided.

Every evidence record carries a `claim` block spelling this out:

```json
"does_not_assert": "This is not an identity determination. It does not establish
who the person is, that the source post is authentic, or that the depicted
person authored or consented to it. Face recognition error rates vary with image
quality and demographic factors."
```

The disclaimer travels with the artifact, so a reader who never opens this file
still sees it.

## 2. Error rates vary with image quality and across demographic groups

Face recognition accuracy is not uniform. It degrades with blur, low resolution,
extreme pose, occlusion and poor lighting, and published evaluations
consistently find error rates that differ across demographic groups. A single
similarity number should not be read as a uniform confidence.

RAYA mitigates what it can and reports the rest:

- Faces below `MIN_FACE_SIZE_PX` (default 48 px) are refused rather than scored,
  because a confident-looking number from a 20-pixel face is worse than no
  number.
- Every detected face carries measured quality — size, sharpness (variance of
  the Laplacian), brightness, detector confidence — and these are shown in the
  UI and stored in the evidence.
- Landmark-based alignment is always applied before encoding, which removes the
  most common cause of spuriously low scores between two photos of one person.

It cannot correct for demographic differential performance, and does not claim
to.

## 3. The threshold is a policy choice, not a fact

The default is **0.40** cosine similarity. OpenCV publishes **0.363** as SFace's
operating point; RAYA rounds up for margin, because candidate images pulled off
the public web have been resized and recompressed at least once, which shifts
scores downward and widens their spread.

Lowering it finds more true matches *and* more false ones. Raising it does the
reverse. There is no threshold that eliminates both error types.

The value in force is recorded in every evidence bundle and anchored with it, so
a reader always knows what standard was applied.

Measured separation on the bundled fixtures:

| Pair | Similarity |
|------|-----------|
| Same person, different photograph | 0.79 |
| Different people | 0.15, 0.23 |

The threshold sits in that gap. A test asserts the gap stays wider than 0.3, so
a regression in the encoder fails the build rather than silently degrading
results.

## 4. Coverage is bounded by the search provider

RAYA can only verify candidates that the reverse image search returns. A source
that is not indexed, is private, is behind a login, was posted recently, or has
been removed will not be found.

**Absence of a match is not evidence of absence.** The evidence record for a
non-match says exactly this rather than implying the image is unpublished.

The provider is also a single point of dependency. The `ReverseSearchProvider`
interface exists so a second vendor can be added without touching verification
logic, but today only Google Lens via SerpApi is implemented.

## 5. Some sources cannot be independently retrieved

Major platforms block automated image fetching, serve placeholder images to
non-browser clients, or require authentication. When a candidate's image cannot
be downloaded, RAYA records it as `unreachable` and moves on.

Critically, it does **not** fall back to trusting the search provider's
thumbnail or its assertion of similarity. A candidate that cannot be
independently retrieved is never verified — it is reported as discovered but
unconfirmed. This is why a real run may find a plausible source and still return
no verified match.

## 6. An anchor proves integrity, not truth

The blockchain record shows that a specific hash existed at a specific block and
has not changed since. It says nothing about whether:

- the source post is authentic rather than staged or itself manipulated,
- the input image was manipulated before RAYA ever saw it,
- the person depicted consented to any of it.

RAYA verifies **provenance of the evidence**, not **veracity of the world**.

## 7. Evidence is public and effectively permanent

Bundles are published to IPFS. Content-addressed storage has no delete, and
pinning services replicate. This is why bundles contain hashes, public URLs,
scores and model names — never face images or embeddings.

The input is handled differently, and the distinction matters. RAYA does **not**
publish the original image anywhere. It hashes the original locally, then
derives a separate bounded copy and uploads only that to the search provider.
Two objects, two digests, both recorded in the evidence.

**Reverse image search is still not private.** The derivative leaves the machine
and is processed by a third party under their terms. If you do not want an image
sent to a search provider, do not run a search on it. What RAYA guarantees is
narrower and precise: the original bytes are never republished, and the face
embedding never leaves the machine at all.

## 8. Deepfakes and synthetic images are out of scope

RAYA does not detect whether an image is AI-generated or manipulated. A
convincing synthetic image of a real person could match that person's genuine
photographs. Nothing here is a manipulation detector, and it should not be
relied on as one.

## 9. Operational limits

- **Single-node, in-memory run state.** Uploads and in-flight runs live in one
  process; completed runs persist to disk. There is no horizontal scaling story.
- **No authentication.** The API is unauthenticated and intended for local or
  trusted-network use. Exposing it publicly would let anyone spend your search
  credits and gas.
- **Bounded concurrency.** Candidate retrieval is capped (default 4 concurrent,
  12 candidates verified per run) to stay a polite client of the sites fetched
  from. Large result sets are truncated, not exhaustively evaluated.
- **Detection input is bounded to 1024 px** on the long edge. The fixed-shape
  YuNet graph stops returning detections at very large resolutions, so input is
  downscaled for detection and coordinates scaled back; alignment still crops
  from full resolution. Very small faces in very large images may be missed.

## 10. What is replayed rather than live

The bundled demo uses a recorded search fixture and serves candidate images from
localhost, because the search API is paid and platforms block fetching. Those
runs are stamped `is_replay: true` in the evidence and labelled as replays in
the UI — they are never presented as fresh searches.

Everything else in a demo run is real: decoding, detection, encoding, HTTP
retrieval, hashing, canonicalization.
