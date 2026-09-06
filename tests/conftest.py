"""Shared test fixtures.

Tests run against the real models and the real fixture photographs. Mocking the
encoder would leave the one claim that matters -- that RAYA's own comparison
separates people -- completely untested.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "core"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure(config):
    config.addinivalue_line("markers", "network: requires outbound network access")
    config.addinivalue_line("markers", "models: requires the ONNX models on disk")


@pytest.fixture(scope="session")
def settings():
    from raya.config import Settings

    return Settings()


@pytest.fixture(scope="session")
def models_available(settings) -> bool:
    return settings.yunet_path.exists() and settings.sface_path.exists()


@pytest.fixture(scope="session")
def detector(settings, models_available):
    if not models_available:
        pytest.skip("models not downloaded; run scripts/fetch_models.py")
    from raya.face.detector import YuNetDetector

    # Session-scoped: loading SFace costs far more than every test in the suite.
    return YuNetDetector(settings)


@pytest.fixture(scope="session")
def encoder(settings, models_available):
    if not models_available:
        pytest.skip("models not downloaded; run scripts/fetch_models.py")
    from raya.face.encoder import SFaceEncoder

    return SFaceEncoder(settings)


@pytest.fixture(scope="session")
def image_bytes():
    return {path.stem: path.read_bytes() for path in FIXTURES.glob("*.jpg")}


@pytest.fixture(scope="session")
def decoded(settings, image_bytes):
    from raya.util.imaging import decode_image

    return {name: decode_image(data, settings) for name, data in image_bytes.items()}


@pytest.fixture(scope="session")
def embeddings(detector, encoder, decoded):
    """Embed the largest face in each single-subject fixture."""
    out = {}
    for name in ("subject_a", "subject_a_alt", "subject_b"):
        image = decoded[name]
        faces = detector.detect(image.bgr)
        assert faces, f"expected a face in {name}"
        out[name] = encoder.encode(image.bgr, faces[0])
    return out
