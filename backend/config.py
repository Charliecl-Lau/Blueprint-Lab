from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    google_api_key: str = ""
    llm_provider: str = "google"
    llm_model: str = "gemini-3.5-flash"
    llm_temperature: float = 0.2
    llm_top_p: float = 0.95
    llm_seed: Optional[int] = None
    llm_max_output_tokens: int = 8192
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = (
        "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
