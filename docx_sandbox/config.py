from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCX_SANDBOX_",
        env_file=".env",
        extra="ignore",
    )
    service_token: str = ""
    service_version: str = "1"
    job_image_digest: str = Field(..., pattern=r"^sha256:[0-9a-f]{64}$")
    max_request_bytes: int = 800_000
    max_concurrency: int = 4
    completed_job_retention_seconds: int = 3600
    timeout_seconds: int = 45
    memory_bytes: int = 512 * 1024 * 1024
    nano_cpus: int = 1_000_000_000
    pids_limit: int = 64
    max_output_bytes: int = 20 * 1024 * 1024
    assets_dir: str = "/assets"


@lru_cache
def get_settings() -> SandboxSettings:
    return SandboxSettings()
