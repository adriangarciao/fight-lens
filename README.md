# FightLens

UFC matchup analysis: time-correct fight histories, head-to-head meetings and common opponents today, calibrated win/method probabilities next. Outputs are model estimates, not guaranteed results or sportsbook odds.

```
backend/    Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · pytest  (managed with uv)
frontend/   React · TypeScript · Vite
docs/       ADRs and the data audit
data/raw/   timestamped source snapshots (git-ignored; re-fetch with `fightlens fetch`)
```

## Local setup

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
# 1. Database
docker compose up -d db                      # Postgres on host port 5433

# 2. Backend
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run fightlens fetch                       # download a fightr snapshot to ../data/raw/
uv run fightlens import --report import-report.json
uv run fightlens train --activate            # backtest + fit (~1 min); writes docs/model-report.md
uv run fightlens predict                     # store predictions for scheduled bouts
uv run uvicorn app.main:app --reload         # http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                                  # http://localhost:5173 (proxies /api to :8000)
```

Tests run on in-memory SQLite and need no database:

```bash
cd backend && uv run pytest && uv run ruff check .
```

## Data

The bootstrap source is the [fightr](https://github.com/benyamindsmith/fightr) dataset (completed and scheduled UFC bouts derived from UFCStats). Read [docs/adr/0002-bootstrap-data-source.md](docs/adr/0002-bootstrap-data-source.md) and [docs/data-audit.md](docs/data-audit.md) before adding features. In short:

- Bouts store fighters in **source order, which is correlated with the result**. It is not a corner and must never be used as a signal.
- Roster career aggregates are as-of-scrape and **leak future information**. Only static physical attributes are imported.
- There are **no per-bout striking/grappling stats** yet; the UI labels them unavailable.
- Every history query takes an `as_of` date and only sees bouts strictly before it.

Importing is idempotent. Completed results are immutable: a changed result is reported as `result_changed`, not applied.

## API

| Route | Purpose |
|---|---|
| `GET /api/events/upcoming`, `/api/events/recent` | Event lists |
| `GET /api/events/{id}` | Card with as-of-event records |
| `GET /api/fighters/search?q=` | Fighter search |
| `GET /api/fighters/{id}?asOf=` | Summary + full history |
| `GET /api/matchups?fighterA=&fighterB=&asOf=` | Tale of the tape, last five, head to head, common opponents |
| `GET /api/matchups/history?fighterA=&fighterB=` | Head-to-head only |
| `POST /api/predictions/matchup` | Any pairing: win probability, six-outcome distribution, reasons, unknowns, data confidence |
| `GET /api/predictions/{boutId}` | Stored batch prediction for a bout (computed live if missing) |

## Model

See [docs/adr/0003-baseline-model-design.md](docs/adr/0003-baseline-model-design.md) and the latest [evaluation report](docs/model-report.md). On the first run (rolling backtest, 2016–2026, 5,329 bouts), the selected logistic model scored log loss 0.658, Brier 0.233 and 60.3% accuracy. For comparison, Elo scored 0.682 and 55.7%, and a coin flip 0.693 and 50%. Models are versioned bundles under `data/artifacts/`. Use `fightlens activate <version>` to switch between them. The API refuses a bundle whose feature schema doesn't match the code.

## Roadmap

- [x] **Phase 1:** data audit, schema + migrations, idempotent importer, comparison API and page
- [x] **Phase 2:** time-correct features, Elo + logistic baselines, CatBoost challenger, calibration, conditional method model, versioned artifacts, evaluation report
- [ ] **Phase 3:** stat visualizations, richer evidence views, mobile polish (predictions on cards are done)
- [ ] **Phase 4:** sourced injury context, rankings history, prediction-vs-result tracking
