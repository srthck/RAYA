"""The build step and the runtime must resolve the same model files.

These tests exist because of a real deployment failure: the build ran
`scripts/fetch_models.py`, reported "All models present and verified", and the
API then reported the YuNet model missing. Any disagreement between the two
about *where* the models live, or *what* they are called, produces exactly that
symptom, so both properties are asserted here rather than assumed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_fetch_models():
    """Import scripts/fetch_models.py without requiring it to be a package."""
    spec = importlib.util.spec_from_file_location(
        "raya_fetch_models", REPO_ROOT / "scripts" / "fetch_models.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fetcher():
    return load_fetch_models()


class TestModelPathResolution:
    def test_repo_root_is_derived_from_file_not_cwd(self):
        """Both modules must anchor on __file__, whatever the process cwd is."""
        from raya.config import REPO_ROOT as CONFIG_ROOT

        fetch = load_fetch_models()
        assert CONFIG_ROOT == REPO_ROOT
        assert fetch.REPO_ROOT == REPO_ROOT

    def test_default_models_dir_agrees(self, fetcher):
        from raya.config import DEFAULT_MODELS_DIR

        assert fetcher.DEFAULT_MODELS_DIR == DEFAULT_MODELS_DIR
        assert DEFAULT_MODELS_DIR == REPO_ROOT / "models"

    def test_model_filenames_do_not_drift(self, fetcher, settings):
        """The fetcher downloads exactly the files the loaders look for."""
        downloaded = {model["name"] for model in fetcher.MODELS}
        expected = {settings.yunet_model, settings.sface_model}
        assert downloaded == expected

    def test_resolved_paths_are_absolute_and_under_models_dir(self, settings):
        for path in (settings.yunet_path, settings.sface_path):
            assert path.is_absolute()
            assert path.parent == settings.models_dir

    def test_models_dir_override_moves_both_sides(self, monkeypatch, tmp_path):
        """MODELS_DIR must move the runtime and the fetcher together."""
        from raya.config import Settings

        monkeypatch.setenv("MODELS_DIR", str(tmp_path))
        moved = Settings()
        assert moved.models_dir == tmp_path
        assert moved.yunet_path.parent == tmp_path

        fetch = load_fetch_models()
        assert fetch._models_dir_from_env() == tmp_path


class TestModelReport:
    def test_report_names_the_directory_and_both_models(self, settings):
        from raya.config import model_report

        report = model_report(settings)
        lines = report.splitlines()
        assert lines[0] == f"MODEL_DIR={settings.models_dir}"
        assert lines[1] == f"YuNet exists={settings.yunet_path.exists()}"
        assert lines[2] == f"SFace exists={settings.sface_path.exists()}"

    def test_report_is_truthful_about_a_missing_directory(self, tmp_path):
        from raya.config import Settings, model_report

        empty = Settings(models_dir=tmp_path / "nowhere")
        report = model_report(empty)
        assert "YuNet exists=False" in report
        assert "SFace exists=False" in report
