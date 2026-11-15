# FightLens: Make It Deploy-Ready (Vercel + Railway)

**Audience:** Claude (Claude Code) working in Adrian's local `fight-lens` repo, on the machine that has the working `.env`, a local Postgres via Docker Compose, `data/raw/` snapshots, and `data/artifacts/` model bundles.

**Goal:** Ship FightLens publicly:

- **Frontend** (React + Vite in `frontend/`) on **Vercel**
- **Backend** (FastAPI in `backend/`) plus **PostgreSQL** on **Railway**. Adrian already has a Railway Hobby plan.

Work on a branch named `deploy/railway-vercel`. Run the backend tests and ruff before committing. Don't push or deploy anything without asking Adrian first.

---

## 1. Context: why a backend is required

The frontend is only a client. `frontend/src/api.ts` calls relative `/api/...` paths, and locally Vite's dev proxy (`vite.config.ts`) forwards those to `localhost:8000`. Every page depends on FastAPI:

- Fighter search and any-pair matchups: `GET /api/fighters/search`, `GET /api/matchups`
- Live model inference: `POST /api/predictions/matchup` (any pairing)
- Events, stored predictions and the track record all come from Postgres

The backend reads three settings (`backend/app/config.py`, prefix `FIGHTLENS_`):

| Variable | Purpose | Local default |
|---|---|---|
| `FIGHTLENS_DATABASE_URL` | SQLAlchemy URL. **Must use the `postgresql+psycopg://` scheme** (psycopg 3) | `postgresql+psycopg://fightlens:fightlens@localhost:5433/fightlens` |
| `FIGHTLENS_DATA_DIR` | Root for `raw/`, `artifacts/`, `logs/` | repo-root `data/` |
| `FIGHTLENS_CORS_ORIGINS` | JSON list of allowed origins | `["http://localhost:5173"]` |

The API isn't hosted on Vercel because Vercel's Python functions have a size limit, and pandas + numpy + scikit-learn + catboost are far over it.

---

## 2. Known blockers (fix all of these)

1. **No Dockerfile or start command for the API.** `docker-compose.yml` only runs the database.
2. **Model bundles aren't in git.** `.gitignore` excludes `data/artifacts/`, so a deployed API would have no model and every prediction would fail with `NoActiveModel` or a missing-file error.
3. **The stored artifact path doesn't work on another machine.** `app/ml/train.py` saves `artifact_path=str(artifact_dir.resolve())`, an absolute path on the training machine (for example `C:\Users\...\data\artifacts\<version>` on Windows). `app/services/predictions.py::active_bundle` loads `Path(mv.artifact_path)` directly, so a Linux container can't find it.
4. **The frontend has no route to the API in production.** Relative `/api` calls only work through the Vite dev proxy.
5. **SPA deep links return 404 on Vercel.** The app uses `BrowserRouter`, so refreshing `/events/123`, `/compare` or `/track-record` gives a 404 unless every path falls back to `index.html`.
6. **The refresh job only runs on Adrian's Windows PC** (Task Scheduler, `scripts/register-refresh-task.ps1`). This is optional for launch (see section 6).

---

## 3. Code and config changes

All of these were written and checked in a scratch copy of the repo. With them in place, the full backend test suite (110 tests plus the new ones) passed, ruff passed, and the API imported cleanly from a `uv sync --frozen --no-dev` install. **The Docker image itself has NOT been built yet.** Build it locally (section 4) before deploying.

### 3.1 Fix the artifact path: `backend/app/services/predictions.py`

Add the import next to the other `app.` imports:

```python
from app.config import get_settings
```

Add this function directly above `active_bundle`:

```python
def bundle_dir(mv: ModelVersion) -> Path:
    """Where the bundle for `mv` lives on this host.

    `artifact_path` is the absolute path on the machine that trained it. A deployed API
    (or a Linux box reading a path written on Windows) won't have that path, so fall back
    to `<data_dir>/artifacts/<version>`, which is where training always writes bundles.
    """
    stored = Path(mv.artifact_path)
    if stored.is_dir():
        return stored
    return get_settings().data_dir / "artifacts" / mv.version
```

In `active_bundle`, change:

```python
_state.bundle = load_bundle(Path(mv.artifact_path))  # raises on schema mismatch
```

to:

```python
_state.bundle = load_bundle(bundle_dir(mv))  # raises on schema mismatch
```

Before relying on the fallback, check that `train.py` still writes bundles to `data_dir / "artifacts" / version` (around the `save_bundle(...)` call). That's what the fallback assumes.

### 3.2 New test: `backend/tests/test_bundle_dir.py`

```python
from app.config import get_settings
from app.db.models import ModelVersion
from app.services.predictions import bundle_dir


def test_uses_stored_path_when_it_exists(tmp_path):
    mv = ModelVersion(version="v1", artifact_path=str(tmp_path))
    assert bundle_dir(mv) == tmp_path


def test_falls_back_to_data_dir_when_stored_path_is_from_another_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGHTLENS_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        windows_path = r"C:\Users\someone\fight-lens\data\artifacts\v7"
        mv = ModelVersion(version="v7", artifact_path=windows_path)
        assert bundle_dir(mv) == tmp_path / "artifacts" / "v7"
    finally:
        get_settings.cache_clear()
```

Note: if Adrian is on Windows, the "Windows path" case could actually exist on his machine. It won't, because `C:\Users\someone\...` is a made-up path, but keep that in mind if the test behaves oddly.

### 3.3 `backend/Dockerfile` (built from the **repo root**)

```dockerfile
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
```

Notes:
- The working directory is `/app/backend` because `alembic.ini` lives in `backend/`. `migrations/env.py` reads the database URL from `get_settings()`, so `FIGHTLENS_DATABASE_URL` is all alembic needs.
- `/app/data` also matches `config.py`'s default (`parents[2] / "data"` from `/app/backend/app/config.py`), so the setting is correct even without the env var.
- Pin the uv image to a specific version (for example `ghcr.io/astral-sh/uv:0.x.y`) if Adrian wants reproducible builds.
- Use one worker to keep RAM down. Railway bills for RAM, and each worker loads its own copy of pandas, the model and the cached fight history.

### 3.4 `railway.toml` (repo root)

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "backend/Dockerfile"
watchPatterns = ["backend/**", "data/artifacts/**", "railway.toml"]

[deploy]
healthcheckPath = "/api/health"
healthcheckTimeout = 120
restartPolicyType = "ON_FAILURE"
```

`/api/health` already exists in `app/main.py`. In the Railway service settings, leave **Root Directory empty** (the repo root) so the build context includes `data/artifacts/`.

### 3.5 `.dockerignore` (repo root)

```
.git
**/node_modules
**/.venv
**/__pycache__
**/.pytest_cache
**/.ruff_cache
frontend/
docs/
scripts/
data/raw/
data/logs/
**/.env
```

### 3.6 `.gitignore`: allow committing model bundles

Replace the line `data/artifacts/` with:

```
data/artifacts/*
!data/artifacts/.gitkeep
```

Then create an empty `data/artifacts/.gitkeep`. The folder then always exists, so the Dockerfile's `COPY data/artifacts` never fails. Bundles stay ignored by default and get committed on purpose with `git add -f`, one active version at a time.

Check the bundle size first (`du -sh data/artifacts/<version>`). If it's tens of MB or more, consider Git LFS or downloading it from object storage at build time. For a logistic winner model plus a method model it should be small.

### 3.7 `frontend/vercel.json`

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://REPLACE-WITH-RAILWAY-DOMAIN.up.railway.app/api/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

- The first rewrite sends API calls through Vercel, so the browser sees them on the same origin. No changes to `api.ts`, and CORS isn't involved.
- The second rewrite handles deep links. Vercel serves real static files (`/assets/...`) before applying rewrites, so they aren't affected.
- **Replace the placeholder** with the Railway public domain after the first Railway deploy (section 5).

Alternative if Adrian prefers no proxy: add `const BASE = import.meta.env.VITE_API_URL ?? ""` to `api.ts`, prefix every `fetch` path with it, set `VITE_API_URL` in Vercel, and set `FIGHTLENS_CORS_ORIGINS` to the Vercel URL. The rewrite approach is simpler, so use it unless he asks otherwise.

### 3.8 README: add a "Deployment" section

Put it before "Keeping it current". Cover: Railway builds `backend/Dockerfile` through `railway.toml`; the two variables from section 5; how to populate the production database and commit the bundle (section 4); and that Vercel's Root Directory is `frontend` with `vercel.json` handling `/api` and deep links. Add the live URL at the top of the README once it's up.

### 3.9 Repo hygiene (for recruiters)

- Rename `FightLens_Project_Handoff (1).md` in the repo root to `docs/project-handoff.md` (or remove it). The "(1)" looks like a stray download.
- After launch, add the live link and a screenshot near the top of the README.

---

## 4. Verify locally before touching Railway

From the repo root:

```bash
cd backend && uv run pytest && uv run ruff check . && cd ..

docker build -f backend/Dockerfile -t fightlens-api .

# Run against the local compose DB (port 5433 on the host)
docker run --rm -p 8000:8000 \
  -e FIGHTLENS_DATABASE_URL="postgresql+psycopg://fightlens:fightlens@host.docker.internal:5433/fightlens" \
  fightlens-api
```

On Linux, add `--add-host=host.docker.internal:host-gateway`. Then check:

- `curl localhost:8000/api/health` returns `{"status":"ok"}`
- `curl localhost:8000/api/events/upcoming` returns data
- A `POST /api/predictions/matchup` succeeds. This exercises the `bundle_dir` fallback inside the container, since the stored path is a host path. Take the request body from `MatchupPredictionRequest` in `app/schemas/predictions.py`.

If catboost or sklearn fail to import in the slim image (for example a missing `libgomp.so.1`), add this to the Dockerfile before the `uv sync` steps:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
```

---

## 5. Railway setup (Adrian does this in the dashboard; walk him through it)

1. **New service → Deploy from GitHub repo** → `adriangarciao/fight-lens`, with Root Directory empty. `railway.toml` takes care of the rest.
2. **Add PostgreSQL** to the same project (`+ New → Database → PostgreSQL`).
3. **API service → Variables** (raw editor):

   ```
   FIGHTLENS_DATABASE_URL=postgresql+psycopg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
   FIGHTLENS_CORS_ORIGINS=["https://<vercel-app>.vercel.app"]
   ```

   - Don't use `${{Postgres.DATABASE_URL}}` as is. Its `postgresql://` scheme makes SQLAlchemy look for psycopg2, which isn't installed.
   - If the database service has a different name, change `Postgres` to match.
   - `PORT` is provided by Railway. `FIGHTLENS_DATA_DIR` is set in the Dockerfile.
4. **Settings → Networking → Generate Domain.** Put that domain into `frontend/vercel.json`.

---

## 6. Populate the production database (from Adrian's machine)

The container runs migrations at startup, but the data and the active model have to be loaded from the dev machine. Copy the Postgres service's **`DATABASE_PUBLIC_URL`** from Railway and change its scheme to `postgresql+psycopg://`. Then, in `backend/`:

```bash
# PowerShell: $env:FIGHTLENS_DATABASE_URL="postgresql+psycopg://...public-host:port/railway"
# bash:       export FIGHTLENS_DATABASE_URL="postgresql+psycopg://...public-host:port/railway"

uv run alembic upgrade head
uv run fightlens import --report import-report.json   # uses the newest snapshot in data/raw/ (run `fetch` first if needed)
uv run fightlens import-stats
uv run fightlens import-odds        # optional, benchmark only
uv run fightlens train --activate   # writes data/artifacts/<version> and docs/model-report.md
uv run fightlens predict
uv run fightlens score
```

Then commit the bundle that's now active in production:

```bash
git add -f data/artifacts/<version>
git commit -m "Ship active model bundle <version>"
```

Important points:
- **The version marked active in the production `model_versions` table must be the one committed in `data/artifacts/`.** If Adrian later retrains or runs `fightlens activate <other>` against production, he has to commit that bundle too and redeploy.
- `train` runs a backtest (about a minute locally). Running it from the dev machine against the remote database is fine, just slower over the network.
- Alternatively, `pg_dump` the local database and `pg_restore` it into Railway, then commit the matching active bundle. This is faster if the local database is already current.
- **Unset `FIGHTLENS_DATABASE_URL` afterward** (or open a new shell) so local work goes back to the compose database.

### Keeping production current (optional, after launch)

Today `fightlens refresh` runs from Windows Task Scheduler against the local database. Options:
- **Simplest:** keep the scheduled task but point it at the production URL. It only runs while the PC is on and logged in.
- **Better:** add a GitHub Actions workflow (`on: schedule`, with a daily cron) that installs uv, runs `uv sync`, and runs `uv run fightlens refresh` with `FIGHTLENS_DATABASE_URL` stored as a repo secret. `refresh` never retrains, so the committed bundle stays valid. Check that `refresh` works on an empty `data/raw/` (it should fetch first).
- A Railway cron service using the same image is also possible.

---

## 7. Vercel setup

1. Import `adriangarciao/fight-lens` and set **Root Directory → `frontend`**. The framework preset should detect Vite: `npm run build`, output `dist`.
2. No env vars are needed when using the rewrite approach.
3. Deploy. Then add the Vercel URL to Railway's `FIGHTLENS_CORS_ORIGINS` (only needed if you skip the proxy, but harmless to set).

---

## 8. Done when

- [ ] Branch `deploy/railway-vercel` has every change in section 3. Tests and ruff pass.
- [ ] The Docker image builds and runs locally. Health, events and a matchup prediction all work inside the container.
- [ ] Production Postgres is populated, an active model is set, and that bundle is committed.
- [ ] Railway deploy is green, and `https://<railway-domain>/api/health` returns ok.
- [ ] On Vercel: the home page loads events, Compare runs a prediction, Track Record loads, and refreshing `/compare` doesn't 404.
- [ ] README has a Deployment section and the live link. The handoff file is renamed or moved.

## 9. Cost notes

Railway Hobby is a $5/month minimum that counts toward usage, and usage is billed per second (about $10/GB-month for RAM). One uvicorn worker with pandas, sklearn and catboost loaded will probably sit at a few hundred MB, so expect roughly $5–10/month for the API plus a small Postgres. Keep it to one worker, and check Railway's usage page after the first week.
