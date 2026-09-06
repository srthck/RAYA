"""Face detection and recognition.

The assertions here are the empirical basis for RAYA's central claim. If the
encoder stopped separating people, every downstream layer -- evidence, IPFS,
the chain -- would faithfully preserve a meaningless result.
"""

from __future__ import annotations

import pytest

from raya.errors import FaceTooSmallError


class TestDetection:
    def test_finds_a_single_face(self, detector, decoded):
        faces = detector.detect(decoded["subject_a"].bgr)
        assert len(faces) == 1
        assert faces[0].score >= 0.9

    def test_finds_both_faces_in_a_two_subject_image(self, detector, decoded):
        faces = detector.detect(decoded["two_faces"].bgr)
        assert len(faces) == 2

    def test_finds_no_face_in_an_image_without_one(self, detector, decoded):
        assert detector.detect(decoded["no_face"].bgr) == []

    def test_orders_faces_largest_first(self, detector, decoded):
        faces = detector.detect(decoded["two_faces"].bgr)
        areas = [f.area for f in faces]
        assert areas == sorted(areas, reverse=True)
        assert [f.index for f in faces] == list(range(len(faces)))

    def test_boxes_stay_inside_the_image(self, detector, decoded):
        image = decoded["subject_a"]
        for face in detector.detect(image.bgr):
            x, y, w, h = face.bbox
            assert x >= 0 and y >= 0
            assert x + w <= image.width
            assert y + h <= image.height

    def test_reports_five_landmarks(self, detector, decoded):
        face = detector.detect(decoded["subject_a"].bgr)[0]
        assert len(face.landmarks) == 5

    def test_reports_quality_metrics(self, detector, decoded):
        face = detector.detect(decoded["subject_a"].bgr)[0]
        quality = face.quality
        assert quality.size_px > 0
        assert 0 < quality.relative_area <= 1
        assert quality.sharpness > 0
        assert 0 <= quality.brightness <= 255

    def test_detects_on_a_large_image(self, detector, decoded, settings):
        """A high-resolution photo must not silently yield zero faces.

        The fixed-shape YuNet graph stops detecting at native resolution on
        large images, so the detector bounds its input and scales coordinates
        back. This guards that path against regression.
        """
        import cv2

        original = decoded["subject_a"].bgr
        upscaled = cv2.resize(original, (original.shape[1] * 4, original.shape[0] * 4))
        faces = detector.detect(upscaled)
        assert len(faces) == 1

        # Coordinates must be in the upscaled image's space, not the detector's
        # internal downscaled one.
        x, y, w, h = faces[0].bbox
        assert w > original.shape[1] // 2
        assert x + w <= upscaled.shape[1]

    def test_handles_an_empty_array(self, detector):
        import numpy as np

        assert detector.detect(np.zeros((0, 0, 3), dtype=np.uint8)) == []


class TestEncoding:
    def test_produces_a_128_dimensional_embedding(self, detector, encoder, decoded):
        image = decoded["subject_a"]
        face = detector.detect(image.bgr)[0]
        embedding = encoder.encode(image.bgr, face)
        assert embedding.dim == 128
        assert embedding.vector.shape == (128,)

    def test_alignment_produces_a_112px_crop(self, detector, encoder, decoded):
        image = decoded["subject_a"]
        face = detector.detect(image.bgr)[0]
        aligned = encoder.align(image.bgr, face)
        assert aligned.shape[:2] == (112, 112)

    def test_is_deterministic(self, detector, encoder, decoded):
        """The same pixels must always give the same vector.

        Evidence records name the model that produced a score; that is only
        meaningful if the model is reproducible.
        """
        import numpy as np

        image = decoded["subject_a"]
        face = detector.detect(image.bgr)[0]
        first = encoder.encode(image.bgr, face)
        second = encoder.encode(image.bgr, face)
        np.testing.assert_array_equal(first.vector, second.vector)

    def test_refuses_a_face_below_the_minimum_size(self, detector, encoder, decoded, settings):
        import cv2

        image = decoded["subject_a"].bgr
        tiny = cv2.resize(image, (image.shape[1] // 12, image.shape[0] // 12))
        faces = detector.detect(tiny)
        if not faces:
            pytest.skip("no face survived the downscale; nothing to assert")
        if faces[0].quality.size_px >= settings.min_face_size_px:
            pytest.skip("face is still above the minimum size")
        with pytest.raises(FaceTooSmallError):
            encoder.encode(tiny, faces[0])

    def test_embedding_is_never_published(self, detector, encoder, decoded):
        """The public view of an embedding must not contain the vector."""
        image = decoded["subject_a"]
        face = detector.detect(image.bgr)[0]
        public = encoder.encode(image.bgr, face).to_public_dict()
        assert public == {"model": "SFace-2021dec", "dim": 128, "exported": False}
        assert "vector" not in public


class TestSimilarity:
    def test_identical_images_score_one(self, encoder, embeddings):
        score = encoder.similarity(embeddings["subject_a"], embeddings["subject_a"])
        assert score == pytest.approx(1.0, abs=1e-4)

    def test_same_person_different_photo_passes(self, encoder, embeddings, settings):
        score = encoder.similarity(embeddings["subject_a"], embeddings["subject_a_alt"])
        assert score > settings.similarity_threshold
        # Measured at 0.79; the floor guards against a real regression while
        # leaving room for model or preprocessing changes.
        assert score > 0.6, f"same-person similarity collapsed to {score:.4f}"

    def test_different_people_are_rejected(self, encoder, embeddings, settings):
        for other in ("subject_a", "subject_a_alt"):
            score = encoder.similarity(embeddings[other], embeddings["subject_b"])
            assert score < settings.similarity_threshold, (
                f"{other} vs subject_b scored {score:.4f}, above the threshold"
            )

    def test_the_threshold_sits_in_a_real_margin(self, encoder, embeddings):
        """Same-person and different-person scores must not overlap.

        This is the property that makes a threshold meaningful at all. Measured
        margin is roughly 0.79 against 0.23.
        """
        same = encoder.similarity(embeddings["subject_a"], embeddings["subject_a_alt"])
        different = max(
            encoder.similarity(embeddings["subject_a"], embeddings["subject_b"]),
            encoder.similarity(embeddings["subject_a_alt"], embeddings["subject_b"]),
        )
        assert same - different > 0.3, f"margin collapsed: same={same:.3f} diff={different:.3f}"

    def test_similarity_is_symmetric(self, encoder, embeddings):
        a, b = embeddings["subject_a"], embeddings["subject_b"]
        assert encoder.similarity(a, b) == pytest.approx(encoder.similarity(b, a), abs=1e-6)

    def test_compare_reports_the_decision(self, encoder, embeddings, settings):
        passing = encoder.compare(embeddings["subject_a"], embeddings["subject_a_alt"])
        assert passing.passed is True
        assert passing.metric == "cosine"
        assert passing.threshold == settings.similarity_threshold
        assert passing.reference_model == "SFace-2021dec"

        failing = encoder.compare(embeddings["subject_a"], embeddings["subject_b"])
        assert failing.passed is False

    def test_threshold_is_honoured(self, encoder, embeddings):
        """A raised threshold must actually reject a formerly passing pair."""
        result = encoder.compare(
            embeddings["subject_a"], embeddings["subject_a_alt"], threshold=0.99
        )
        assert result.passed is False
