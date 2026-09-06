"""Runtime configuration.

Everything that varies between machines lives here and nowhere else. Secrets
come from the environment; model paths and thresholds have defensible defaults
so a fresh clone runs without a config file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    # ---- face models -------------------------------------------------------
    models_dir: Path = REPO_ROOT / "models"
    yunet_model: str = "face_detection_yunet_2023mar.onnx"
    sface_model: str = "face_recognition_sface_2021dec.onnx"

    # Detection confidence for YuNet. 0.9 is the OpenCV Zoo demo default and
    # keeps false detections (texture, background faces) out of the pipeline.
    face_score_threshold: float = 0.9
    face_nms_threshold: float = 0.3
    face_top_k: int = 5000

    # A face smaller than this on its shortest side does not carry enough
    # signal for a trustworthy SFace embedding, so we refuse rather than
    # produce a confident-looking number from mush.
    min_face_size_px: int = 48

    # ---- verification ------------------------------------------------------
    # SFace's own published operating point for cosine similarity is 0.363.
    # We round up to 0.40 to buy margin against the extra degradation that
    # comes from web-sourced (recompressed, resized) candidate images.
    similarity_threshold: float = 0.40
    similarity_metric: Literal["cosine"] = "cosine"

    # ---- input limits ------------------------------------------------------
    max_upload_bytes: int = 15 * 1024 * 1024
    max_image_pixels: int = 50_000_000
    min_image_dimension: int = 64

    # ---- reverse search ----------------------------------------------------
    search_provider: str = "serpapi"
    serpapi_key: Optional[str] = None
    search_timeout_s: float = 45.0
    max_candidates: int = 40
    max_verified_candidates: int = 12

    # Google Lens needs a publicly fetchable image URL. If the API itself is
    # reachable from the internet set PUBLIC_BASE_URL; otherwise RAYA publishes
    # the input to IPFS first and hands Lens the gateway URL.
    public_base_url: Optional[str] = None

    # ---- candidate retrieval ----------------------------------------------
    # Off by default: the URLs we fetch are chosen by a third-party API, so
    # reaching private address space would be an SSRF. Tests that serve
    # fixtures from localhost enable it explicitly.
    allow_private_network: bool = False

    fetch_timeout_s: float = 20.0
    max_candidate_bytes: int = 12 * 1024 * 1024
    user_agent: str = "RAYA/1.0 (visual evidence verification; +https://github.com/raya)"

    # ---- IPFS --------------------------------------------------------------
    ipfs_provider: str = "auto"  # auto | pinata | kubo | local
    pinata_jwt: Optional[str] = None
    pinata_gateway: str = "https://gateway.pinata.cloud"
    kubo_api_url: str = "http://127.0.0.1:5001"
    ipfs_public_gateway: str = "https://ipfs.io"

    # ---- blockchain --------------------------------------------------------
    chain_rpc_url: str = "https://rpc.test2.btcs.network"
    chain_id: int = 1114
    chain_name: str = "Core Testnet2"
    chain_currency: str = "tCORE2"
    chain_explorer: str = "https://scan.test2.btcs.network"
    contract_address: Optional[str] = None
    deployer_private_key: Optional[str] = None
    chain_tx_timeout_s: float = 180.0

    # ---- storage -----------------------------------------------------------
    data_dir: Path = REPO_ROOT / ".raya-data"

    @property
    def yunet_path(self) -> Path:
        return self.models_dir / self.yunet_model

    @property
    def sface_path(self) -> Path:
        return self.models_dir / self.sface_model

    @property
    def search_configured(self) -> bool:
        return bool(self.serpapi_key)

    @property
    def chain_configured(self) -> bool:
        return bool(self.contract_address and self.deployer_private_key)

    @property
    def ipfs_configured(self) -> bool:
        return self.ipfs_provider != "off"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.data_dir.mkdir(parents=True, exist_ok=True)
    return _settings


def reset_settings() -> None:
    """Test hook: force the next `get_settings()` to re-read the environment."""
    global _settings
    _settings = None
