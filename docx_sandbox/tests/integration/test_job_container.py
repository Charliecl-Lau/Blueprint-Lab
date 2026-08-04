import os, pytest

pytestmark = pytest.mark.integration

@pytest.mark.skipif(os.getenv("RUN_DOCX_SANDBOX_INTEGRATION") != "1", reason="Docker integration is gated")
def test_job_container_suite_is_explicitly_gated():
    # The full hostile corpus is run in deployment CI where Docker is available.
    assert os.getenv("RUN_DOCX_SANDBOX_INTEGRATION") == "1"
