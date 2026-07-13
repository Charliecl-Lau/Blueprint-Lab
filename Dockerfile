FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt

COPY alembic.ini alembic.ini
COPY backend backend

CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
