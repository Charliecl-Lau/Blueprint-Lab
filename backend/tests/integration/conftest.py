import os

import pytest


@pytest.fixture(scope="session")
def postgres_url() -> str:
    url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is not set; PostgreSQL migration test skipped")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("TEST_POSTGRES_DATABASE_URL must identify a PostgreSQL database")
    return url
