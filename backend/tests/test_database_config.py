from backend.config import Settings


def test_postgresql_is_the_runtime_default():
    settings = Settings(_env_file=None)
    assert settings.database_url == (
        "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
    )


def test_sqlite_remains_a_supported_explicit_database():
    settings = Settings(database_url="sqlite:///./test.db", _env_file=None)
    assert settings.database_url.startswith("sqlite")


def test_default_google_model_uses_a_generate_content_identifier():
    settings = Settings(_env_file=None)
    assert settings.llm_model == "gemini-3.5-flash"
