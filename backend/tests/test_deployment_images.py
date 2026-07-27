from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("dockerfile_name", ("Dockerfile", "Dockerfile.worker"))
def test_backend_images_include_openai_actual_prompt_template(
    dockerfile_name: str,
) -> None:
    dockerfile = (PROJECT_ROOT / dockerfile_name).read_text(encoding="utf-8")

    assert (
        "COPY docs/actual_prompt_template.md docs/actual_prompt_template.md"
        in dockerfile.splitlines()
    )


@pytest.mark.parametrize("dockerfile_name", ("Dockerfile", "Dockerfile.worker"))
def test_backend_images_install_runtime_requirements_only(
    dockerfile_name: str,
) -> None:
    dockerfile = (PROJECT_ROOT / dockerfile_name).read_text(encoding="utf-8")

    assert "COPY backend/requirements.runtime.txt backend/requirements.runtime.txt" in dockerfile
    assert "pip install --no-cache-dir -r backend/requirements.runtime.txt" in dockerfile
    assert "requirements.txt" not in dockerfile
