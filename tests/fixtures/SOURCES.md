# Test fixtures

Downscaled to 720 px on the long edge so the repository stays small while the
images remain real photographs -- synthetic or generated faces would not
exercise the detector or the encoder meaningfully.

| File | Source | Licence |
|------|--------|---------|
| `subject_a.jpg` | Official presidential portrait of Barack Obama (Pete Souza, White House) | Public domain (US federal government work) |
| `subject_a_alt.jpg` | A second, different official portrait of the same subject | Public domain (US federal government work) |
| `subject_b.jpg` | Official presidential portrait of Joe Biden (Adam Schultz, White House) | Public domain (US federal government work) |
| `no_face.jpg` | Generated gradient, contains no face | n/a |
| `two_faces.jpg` | `subject_a.jpg` and `subject_b.jpg` composited side by side | Public domain |

These are used only as local test inputs for face detection and similarity
scoring. They are not distributed as verification results and no identity claim
is attached to them.

## Measured baseline

Recorded from the models pinned in `scripts/fetch_models.py`, and asserted by
`tests/test_face.py`:

| Pair | Cosine similarity | Against the 0.40 threshold |
|------|-------------------|----------------------------|
| `subject_a` vs `subject_a_alt` (same person, different photo) | 0.79 | pass |
| `subject_a` vs `subject_b` (different people) | 0.15 | reject |
| `subject_a_alt` vs `subject_b` (different people) | 0.23 | reject |

The gap between 0.79 and 0.23 is the margin the threshold sits in.
