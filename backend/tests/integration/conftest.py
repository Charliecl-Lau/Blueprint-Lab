import os
from pathlib import Path

import pytest


def pytest_collection_modifyitems(items):
    """Keep PostgreSQL migration checks out of the routine SQLite suite."""
    integration_dir = Path(__file__).resolve().parent
    for item in items:
        if integration_dir in Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def postgres_url() -> str:
    url = os.getenv("TEST_POSTGRES_DATABASE_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is not set; PostgreSQL migration test skipped")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("TEST_POSTGRES_DATABASE_URL must identify a PostgreSQL database")
    return url
