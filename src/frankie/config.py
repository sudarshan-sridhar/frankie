"""Application configuration via pydantic-settings.

All runtime tunables (paths, network endpoints, API keys, log level) load from
environment variables and an optional .env file. The Settings singleton is
constructed once via get_settings() and reused everywhere; never read os.environ
directly in business logic.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = REPO_ROOT / "data"
CALIBRATION_DIR: Path = DATA_DIR / "calibration"
LOGS_DIR: Path = DATA_DIR / "logs"
DEFECTS_DIR: Path = DATA_DIR / "defects"


class Settings(BaseSettings):
    """Runtime configuration for Frankie."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", description="Claude API key (fallback only)")
    watsonx_api_key: str = Field(default="", description="IBM watsonx.ai API key")
    watsonx_project_id: str = Field(default="", description="IBM watsonx.ai project ID")
    granite_model_id: str = Field(
        default="ibm/granite-3-8b-instruct",
        description="Granite chat model used by primary reasoning path",
    )
    granite_vision_model_id: str = Field(
        default="ibm/granite-vision-3-2-2b",
        description="Granite vision model for image-grounded reasoning",
    )
    openai_api_key: str = Field(default="", description="OpenAI key for Whisper STT proxy")
    pi_host: str = Field(default="rpclaw@UMDCLAW.local", description="SSH target")
    camera_url: str = Field(default="", description="MJPEG camera URL or device index")
    log_level: str = Field(default="INFO", description="Python log level name")

    repo_root: Path = REPO_ROOT
    data_dir: Path = DATA_DIR
    calibration_dir: Path = CALIBRATION_DIR
    logs_dir: Path = LOGS_DIR
    defects_dir: Path = DEFECTS_DIR

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    pca9685_address: int = 0x40
    pca9685_frequency_hz: int = 50

    workspace_x_min_mm: float = 80.0
    workspace_x_max_mm: float = 230.0
    workspace_y_min_mm: float = -180.0
    workspace_y_max_mm: float = 180.0
    workspace_z_min_mm: float = 0.0
    workspace_z_max_mm: float = 200.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    return Settings()
