# FightLens — UFC Fight Night Predictor
## Product and Engineering Handoff | Version 1.1 | October 2026

### 1. Project vision
Build a full-stack UFC matchup prediction application that estimates **who is more likely to win**, **how each fighter could win**, and **why**. Users can open a scheduled fight card or choose two fighters for a hypothetical matchup. The experience should go beyond basic career records: it must account for opponent quality, recent form, past meetings, common opponents, matchup styles, layoffs, and credible pre-fight context.

This is an **evidence-based analytics product**, not a betting tip generator. Predictions must be probabilistic, reproducible, and honest about missing data. Do not manufacture statistics, injury reports, or confidence.

**Architecture decision (v1.1):** Use a **Python-first backend with FastAPI**, not Spring Boot. This product is dominated by data ingestion, historical feature engineering, machine-learning experiments, and probability serving. Keeping those jobs and the HTTP API in one Python ecosystem avoids a separate Java-to-Python model service. Choose technology for project fit, not familiarity.

### 2. Required user experience
**A. Fight card dashboard.** Show upcoming UFC events and each scheduled matchup, with event date, division, number of scheduled rounds, fighter names, model win percentages, likely winning method, and the time predictions were last generated. Separate scheduled fights from completed results. Allow users to open a detailed breakdown.

**B. Head-to-head matchup page.** Let users select Fighter A and Fighter B, including an unscheduled/custom pairing. At the top, display each fighter's predicted win probability and a method-of-victory distribution. For example, the following six **illustrative, non-real** outcomes add to 100%:

| Outcome | Probability |
|---|---:|
| Fighter A by KO/TKO | 28% |
| Fighter A by submission | 9% |
| Fighter A by decision | 20% |
| Fighter B by KO/TKO | 17% |
| Fighter B by submission | 8% |
| Fighter B by decision | 18% |

In this example, Fighter A's overall win probability is **57%** and Fighter B's is **43%**. Make it clear that each method percentage is an **unconditional chance of that exact outcome**, not the percentage of a fighter's wins. Show draws/no-contests separately if the modeling design includes them, and always preserve probability totals.

**C. Explain the prediction.** Below the probabilities, show 3–5 grounded reasons favoring each side, 1–3 major unknowns, a data-confidence indicator, and sources/as-of timestamps. Each explanation must point to actual model inputs or verified context; do not use generic AI-generated sports commentary disguised as analysis.

### 3. Detailed fighter comparison requirements

**Recent form and win/loss quality (high importance).** Display the last five UFC fights as a dated timeline with opponent, opponent quality at the time, result, method, round/time, and days since that fight. Clearly identify whether each fighter is coming off a win or loss, current streak, record over the last 3–5 bouts, and form trajectory. Treat a dominant win over strong opposition differently from an uneventful narrow decision against weaker opposition. Consider knockdowns, strike differential, takedowns, control, finish timing, round scoring where available, and strength of competition. A KO loss or sustained one-sided damage can be a stronger negative signal than a competitive decision loss, but must not automatically imply a lasting medical problem. Do not infer dominance from finish method alone.

**Previous meetings between the two fighters (high relevance, carefully time-adjusted).** Automatically find every prior A-versus-B fight. Show event, date, division, winning fighter, method, round/time, and key bout statistics. Note the time elapsed, whether each fighter has since changed division, how active they have been, and whether their recent performances suggest meaningful change. A rematch from six years ago must receive substantially less model weight than a recent matchup; prior results must never dictate the next outcome by themselves.

**Common opponents (moderate relevance, context-aware).** Identify all opponents both fighters have faced, with side-by-side results, fight dates, methods, and opponent strength at those dates. Include time gaps between the relevant fights and whether the common opponent was in a comparable career stage. Example: A defeated Opponent C by submission in 2024; B lost a decision to C in 2021. Flag that as relevant context, **not proof** A would beat B. Avoid treating wins and losses as transitive. Show a “limited comparison” note when the bouts are old, in different weight classes, or under materially different circumstances.

**Styles and statistics (high importance).** Compare significant strikes landed/absorbed per minute, striking accuracy/defense, knockdowns, strike location and distance/clinch/ground splits where available, takedowns per 15 minutes, takedown accuracy/defense, submission attempts, and control time. Derive opponent-adjusted and recent versions where possible rather than relying only on lifetime averages. Examine striking-versus-grappling compatibility: high takedown volume versus takedown defense, submission offense versus grappling vulnerability, defensive striking versus opponent volume, reach/stance interactions, and three-round versus five-round performance. Label unavailable advanced metrics rather than filling gaps with estimates presented as fact.

**Physical and situational context (moderate importance).** Include age at the fight date, height, reach, stance, division, years of UFC experience, scheduled rounds, debut/return status, weight-class moves, and fight location/travel or altitude only if verifiable and useful. Show days since each fighter's last appearance, long layoffs, short turnarounds, and activity over 12 and 24 months. Account for aging and inactivity statistically; do not assume any one layoff is harmful without evidence.

**Injuries and readiness (conditional, carefully sourced).** Support public injury/surgery reports, announced withdrawals, recovery timelines, and credible return-to-competition updates. Every report needs a source link, publication date, event date, status (`confirmed`, `reported`, `resolved`, `uncertain`), and an evidence-quality flag. Only use information published **before** the prediction cutoff. A lingering issue may be shown as an uncertainty, but should affect probabilities only if evidence and historical validation support it. Never diagnose injuries, invent recovery status, or scrape private health information. Missing injury data means `unknown`, not `healthy`.

**Momentum and hype (display primarily; minimal modeling impact).** Show verified signals such as current ranking trajectory, recent notable wins, title contention, and an optional labeled media/public-interest trend. Hype is distinct from fighting ability. For version 1, **exclude hype from the predictive model**; if later tested as a feature, cap any effect at a very small calibrated amount (for example, at most 1 percentage point), and measure whether it improves out-of-sample predictions. Never substitute social popularity for athletic evidence.

### 4. Prediction engine
Start with a reproducible, tabular machine-learning baseline rather than an LLM predicting fights. Use **Python + pandas (or Polars) + scikit-learn + CatBoost**: begin with logistic regression and an Elo benchmark, then compare CatBoost on the same time-respecting data. Calibrate pre-fight winner probabilities on separate chronological validation data. Train a second model of KO/TKO, submission, or decision **conditional on the winner**, and multiply those conditional probabilities by each fighter's win probability to produce the six joint outcomes. They must sum to 100% in a win-only model. Evaluate a direct six-class model later only if it is better-calibrated on held-out fights.

Create features for age/reach differences, short- and long-run performance, opponent-adjusted striking/grappling metrics, recent opponent strength, layoffs, momentum, rematch history, common opponents, and 3-versus-5-round context. An Elo/Glicko-style **time-indexed fighter strength rating** is a useful baseline and opponent-strength feature. Apply sensible recency weighting and small-sample shrinkage, then let held-out testing determine which features actually help. Historical win/loss quality and common-opponent comparisons should not be double-counted when they depend on the same underlying bouts.

**Critical anti-leakage rule:** Every training example represents the knowledge available immediately *before* that historical fight. Never join current fighter career totals, current rankings, later rematches, later injuries, post-fight statistics, or future opponent outcomes into that example. Store `prediction_as_of`, source snapshot/version, feature-set version, and model version. Scheduled bouts and official results require different states. Normalize red/blue corner ordering so it never creates predictive bias. Persist serialized, versioned model artifacts plus the exact feature schema; refuse inference when the active model and feature schema do not match.

Train and evaluate with **chronological splits and rolling historical backtests**, not a random train/test split. Compare against an always-50/50 baseline, a simple Elo model, and optionally bookmaker implied probabilities **as a benchmark only**, not a training feature. Report accuracy, log loss, Brier score, and calibration by probability bucket; separately evaluate method-of-victory performance. Calibrate probabilities on time-held-out data. Be willing to show 52/48 rather than false certainty. Add a `limited data` indicator for debutants, major division moves, sparse histories, and older data.

### 5. Data sourcing and ingestion
Use **UFCStats** as a candidate primary historical reference for fighters, completed events, bout outcomes, and detailed round/fight statistics. Evaluate the publicly available **TidyTuesday UFC dataset (July 7, 2026)** as a convenient bootstrap dataset, but audit its exact field definitions, provenance, age, duplicates, and whether aggregate records contain future information. Research a legitimate source for upcoming cards separately; a manual scheduled-fight importer is acceptable for the MVP. Confirm permitted data usage, rate limits, and redistribution rights before writing scrapers or shipping data commercially. Do not assume a free official UFC API exists.

Suggested records: `fighters`, `events`, `bouts`, `fighter_bout_stats`, `rankings_history`, `injury_reports`, `scheduled_bouts`, `data_sources`, `model_versions`, and `predictions`. Give fighters stable internal IDs and external-source IDs; handle aliases/name collisions. Each bout stores date, weight class, scheduled rounds, result, method, round/time, and an immutable source reference. Preserve raw ingested data separately from cleaned/derived features. Re-running ingestion must be idempotent and report missing/contradictory fields.

Reference links:
- UFCStats completed events: https://www.ufcstats.com/statistics/events/completed?page=all
- TidyTuesday UFC data and dictionary: https://github.com/rfordatascience/tidytuesday/tree/main/data/2026/2026-07-07

### 6. Recommended architecture (Python-first)
- **Frontend:** React + TypeScript + Vite, with responsive event cards, fighter search, side-by-side comparisons, charts, and expandable evidence. Recharts is a reasonable option for probability and performance visualizations.
- **Backend API:** **Python 3.12+ + FastAPI + Pydantic** for validated request/response schemas, fighter/event search, matchup analysis, model inference, and generated OpenAPI documentation. Start as one modular service rather than separate ML and application microservices.
- **Database:** **PostgreSQL + SQLAlchemy 2 + Alembic** (not Flyway). Use typed ORM models and migrations. Index fight-participant IDs/dates and event/scheduled status; maintain immutable historical results and source provenance. Prefer straightforward synchronous DB access for the MVP.
- **Machine learning:** Python feature-building scripts using pandas or Polars; **scikit-learn** for baseline models, metrics and calibration; **CatBoost** as the primary tree-based challenger. Save versioned model artifacts, feature definitions, evaluation reports, and inference metadata. The API loads approved artifacts rather than retraining per request.
- **Data ingestion and jobs:** Python importer/normalizer modules for supported sources, idempotent upserts, and timestamped raw snapshots. Run scheduled imports, pre-fight feature builds, training, and batch prediction as separate **CLI/worker processes**. Use a simple scheduler or hosting cron later; **do not introduce Celery, Redis, or a second API just for jobs in the MVP**.
- **Development and deployment:** Keep a `frontend/` React app and a `backend/` Python project in one repository. Use `pyproject.toml` and `uv` for reproducible Python dependencies; Docker Compose for local PostgreSQL; pytest and GitHub Actions for tests. Frontend can deploy to Vercel, backend to Railway or another Python-capable host, with managed PostgreSQL when available. **No deployment prerequisite**: the entire project must work locally while Railway is unavailable.

**Suggested backend layout:** `app/api/` (routers), `app/schemas/` (Pydantic), `app/db/` (SQLAlchemy and migrations), `app/services/` (comparisons and prediction orchestration), `app/ingestion/` (source adapters), `app/ml/` (features, training, evaluation, artifacts), and `tests/`. Keep feature transformations reusable between training and inference so their definitions cannot drift.

**Representative API routes:** `GET /api/events/upcoming`, `GET /api/events/{id}`, `GET /api/fighters/search?q=`, `GET /api/fighters/{id}`, `GET /api/matchups?fighterA=&fighterB=&eventDate=`, `GET /api/matchups/history?fighterA=&fighterB=`, `POST /api/predictions/matchup` (fighter IDs + as-of date; returns outcome distribution and evidence), and `GET /api/predictions/{boutId}`. Cache outputs by matchup, scheduled rounds, as-of cutoff, feature-set version, and model version. Do not train or scrape inside a public prediction request. No login is required for version 1.

### 7. MVP build order
**Phase 1 — trustworthy data layer and FastAPI foundation.** Scaffold FastAPI, Pydantic schemas, SQLAlchemy models, Alembic migrations, PostgreSQL, and pytest. Import historical UFC events, bouts, and fighter stats; reconcile fighter identities; expose search and matchup endpoints. Display last-five-fight timelines, head-to-head history, and common opponents before any model exists.

**Phase 2 — Python ML baseline.** Implement time-correct feature creation, Elo and logistic regression baselines, a CatBoost challenger, chronological calibration, conditional method predictions, batch prediction jobs, reproducible model artifacts, and evaluation reports. Add tests for probability arithmetic, artifact/schema compatibility, and post-fight leakage.

**Phase 3 — full fight-night interface.** Add upcoming fight cards, compact predictions, side-by-side stat visualizations, top evidence drivers, inactive/layoff indicators, uncertainty messaging, and mobile-responsive UI.

**Phase 4 — enrichment.** Add sourced injury/readiness context, historical rankings, optional hype indicators, better opponent adjustment, optional round-of-finish probabilities, and prediction-vs-result tracking. Only retain enrichment features if backtests justify them.

### 8. Definition of done for the first release
1. A user can search two fighters and view their most recent fights, current streaks, layoff lengths, direct meetings, and dated common-opponent comparisons.
2. A scheduled card can show every configured bout with win percentages, method outcomes, model version, and `as-of` timestamp.
3. Fighter A/B win probabilities sum to 100% for the modeled win-only case; the six win-method outcomes sum to the same total; no unlabelled made-up values appear.
4. Every historical backtest uses only information available before the bout; automated tests catch post-fight feature leakage, reversed fighter order, duplicate fights, and missing data.
5. A reproducible evaluation report compares the model against Elo and 50/50, with calibration and method-prediction metrics.
6. Missing injury reports, missing advanced statistics, and unknown scheduled bouts degrade gracefully and do not silently become assumed facts.
7. A new developer can clone the repo, start PostgreSQL with Docker Compose, install backend dependencies with `uv`, run Alembic migrations and FastAPI locally, import seed data, run pytest, train/evaluate the baseline, and start the React frontend using documented commands.

### 9. Product guardrails and scope
The initial priority is **prediction quality + transparent matchup analysis**, not social accounts, subscriptions, betting integrations, live round-by-round simulation, or AI-written fight narratives. Avoid hardcoded handicapping weights chosen because they sound intuitive; prefer measurable signals, temporal validation, and calibrated probabilities. The UI should always say the output is a model estimate rather than a guaranteed result or a sportsbook's actual odds.

**Immediate engineering task:** First validate historical data coverage and source permissions, define the PostgreSQL/Alembic schema and importer, and scaffold the FastAPI + React monorepo with local Docker Compose. Deliver the comparison page before model predictions, then implement baseline training, calibration, and versioned inference incrementally. Document the reasons for choosing FastAPI and any later infrastructure changes in short technical decision records.
