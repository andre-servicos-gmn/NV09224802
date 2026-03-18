FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app

RUN pip install --no-cache-dir -r backend/requirements.txt && \
    pip install --no-cache-dir -e backend/

CMD cd backend && uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
