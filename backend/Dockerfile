# FightLens API. Build from the REPO ROOT so data/artifacts/ is in the build context:
#   docker build -f backend/Dockerfile -t fightlens-api .
# railway.toml at the repo root already points Railway here.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FIGHTLENS_DATA_DIR=/app/data

WORKDIR /app/backend

# Dependencies first so code changes don't reinstall pandas/catboost.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

# Trained model bundles (commit the active one with `git add -f data/artifacts/<version>`).
COPY data/artifacts /app/data/artifacts

EXPOSE 8000
# Single worker: each worker loads its own copy of the model and fight history.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
