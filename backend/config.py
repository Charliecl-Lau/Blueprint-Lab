from functools import lru_cache
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str = ""
    llm_provider: str = "google"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_evaluation_model: Optional[str] = None
    llm_temperature: float = 0.2
    llm_top_p: float = 0.95
    llm_seed: Optional[int] = None
    llm_max_output_tokens: int = 32768
    docx_generation_backend: Literal["legacy", "self_hosted_code", "agentic_tools"] = "legacy"
    docx_tool_max_revisions: int = 2
    docx_tool_max_operations_per_turn: int = 100
    docx_tool_max_review_pages: int = 25
    docx_tool_max_review_image_bytes: int = 20 * 1024 * 1024
    docx_tool_max_total_seconds: int = 180
    docx_sandbox_url: str = "http://localhost:8090"
    docx_sandbox_service_token: str = ""
    docx_sandbox_connect_timeout_seconds: float = 5.0
    docx_sandbox_read_timeout_seconds: float = 60.0
    docx_sandbox_max_response_bytes: int = 25 * 1024 * 1024
    docx_sandbox_expected_image_digest: str = ""
    docx_render_command: str = "libreoffice"
    docx_render_expected_version: str = ""
    docx_render_timeout_seconds: int = 60
    docx_render_min_pages: int = 1
    docx_render_max_pages: int = 100
    local_reviewer_id: str = "local-reviewer"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = (
        "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
