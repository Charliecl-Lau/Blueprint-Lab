from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    google_api_key: str = ""
    llm_model: str = "gemma-4-31b"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///./assessment_generator.db"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
