# ADR 0001: Python + FastAPI backend

- Status: accepted
- Date: 2026-10-20

## Context

Most of FightLens's work is data ingestion, time-indexed feature engineering, model training and calibration, and serving probabilities. Those jobs live in the Python data stack (pandas, scikit-learn, CatBoost).

## Decision

Use one Python 3.12 service: FastAPI + Pydantic for the HTTP API, SQLAlchemy 2 + Alembic for PostgreSQL, and CLI entry points (`fightlens ...`) for ingestion, training and batch prediction. Dependencies are managed with `uv`.

## Consequences

- Feature transforms are imported by both the training jobs and the API, so their definitions can't drift between training and inference.
- There's no Java-to-Python model service and no second API just for jobs. Scheduled work runs as CLI processes (cron or host scheduler); no Celery or Redis.
- Python 3.12 is pinned (`backend/.python-version`) rather than the newest interpreter, because ML wheels such as CatBoost lag new CPython releases.
- Models and queries stay portable SQL so the unit-test suite can run on in-memory SQLite without Docker. PostgreSQL is the runtime and production database.
