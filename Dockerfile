FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY backend/requirements.runtime.txt backend/requirements.runtime.txt

RUN pip install --no-cache-dir -r backend/requirements.runtime.txt

COPY alembic.ini alembic.ini
COPY backend backend
COPY docx_sandbox docx_sandbox
COPY docs/actual_prompt_template.md docs/actual_prompt_template.md

CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
