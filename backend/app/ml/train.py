"""`fightlens train`: tune Elo, backtest, pick models, fit the production bundle, write the report."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import IngestionRun, ModelVersion
from app.ml import features as F
from app.ml.artifacts import ModelBundle, current_schema, save_bundle
from app.ml.data import BoutRow, FighterStatic, load_history
from app.ml.evaluate import (
    TRAIN_START_YEAR,
    BacktestResult,
    backtest,
    fit_winner,
    method_matrix,
    winner_matrix,
    winner_metrics,
)
from app.ml.models import EloModel, LogisticModel, MethodModel

ELO_K_GRID = (16, 32, 48, 64, 96, 128)
K_SELECTION_LAST_YEAR = 2015  # K is tuned only on bouts before the first test year
FIRST_TEST_YEAR = K_SELECTION_LAST_YEAR + 1
CALIBRATION_DAYS = 365


@dataclass
class TrainResult:
    version: str
    artifact_dir: Path
    report_md: str
    activated: bool


def select_elo_k(bouts: list[BoutRow], statics: dict[int, FighterStatic]) -> tuple[float, dict]:
    scores = {}
    for k in ELO_K_GRID:
        rows = [
            r
            for r in F.build_training_rows(bouts, statics, k)
            if TRAIN_START_YEAR <= r.bout.on.year <= K_SELECTION_LAST_YEAR
        ]
        X, y = winner_matrix(rows)
        scores[k] = winner_metrics(EloModel().raw(X), y)["log_loss"]
    return float(min(scores, key=scores.get)), scores


def train(session: Session, data_dir: Path, activate: bool = False) -> TrainResult:
    bouts, statics = load_history(session)
    run = session.scalar(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(1))
    elo_k, k_scores = select_elo_k(bouts, statics)
    rows = F.build_training_rows(bouts, statics, elo_k)
    last = rows[-1].bout.on

    bt = backtest(rows, list(range(FIRST_TEST_YEAR, last.year + 1)))
    winner_kind = min(("elo", "logistic", "catboost"), key=lambda k: bt.pooled[k]["log_loss"])
    method_kind = min(("logistic", "catboost"), key=lambda k: bt.method[k]["log_loss"])

    cal_start = last - timedelta(days=CALIBRATION_DAYS)
    train_rows = [r for r in rows if r.bout.on.year >= TRAIN_START_YEAR and r.bout.on < cal_start]
    calib_rows = [r for r in rows if r.bout.on >= cal_start]
    winner = fit_winner(winner_kind, train_rows, calib_rows)
    method = MethodModel(method_kind).fit(
        *method_matrix([r for r in rows if r.bout.on.year >= TRAIN_START_YEAR])
    )

    version = _unique_version(session, f"{last:%Y%m%d}-{winner_kind}-{F.schema_hash()[:6]}")
    metadata = {
        "version": version,
        **current_schema(),
        "elo_k": elo_k,
        "winner_model": winner_kind,
        "method_model": method_kind,
        "calibration_slope": winner.calibrator.slope,
        "trained_at": datetime.now(UTC).isoformat(),
        "data_snapshot_sha256": run.snapshot_sha256 if run else None,
        "data_through": last.isoformat(),
        "train_range": [train_rows[0].bout.on.isoformat(), train_rows[-1].bout.on.isoformat()],
        "calibration_range": [
            calib_rows[0].bout.on.isoformat(),
            calib_rows[-1].bout.on.isoformat(),
        ],
        "backtest_pooled": bt.pooled,
        "backtest_method": bt.method,
    }
    report = render_report(metadata, bt, k_scores, winner)
    artifact_dir = save_bundle(
        data_dir / "artifacts" / version, ModelBundle(version, winner, method, metadata), report
    )

    if activate:
        session.execute(update(ModelVersion).values(is_active=False))
    session.add(
        ModelVersion(
            version=version,
            feature_set_version=F.FEATURE_SET_VERSION,
            schema_hash=F.schema_hash(),
            winner_model=winner_kind,
            method_model=method_kind,
            artifact_path=str(artifact_dir.resolve()),
            data_snapshot_sha256=metadata["data_snapshot_sha256"],
            trained_through=last,
            metrics={"backtest": bt.pooled, "method": bt.method},
            is_active=activate,
        )
    )
    session.commit()
    return TrainResult(version, artifact_dir, report, activate)


def activate_version(session: Session, version: str) -> None:
    mv = session.scalar(select(ModelVersion).where(ModelVersion.version == version))
    if mv is None:
        raise ValueError(f"Unknown model version {version!r}")
    session.execute(update(ModelVersion).values(is_active=False))
    mv.is_active = True
    session.commit()


def _unique_version(session: Session, base: str) -> str:
    version, n = base, 1
    while session.scalar(select(ModelVersion.id).where(ModelVersion.version == version)):
        n += 1
        version = f"{base}-r{n}"
    return version


def _pct(x: float) -> str:
    return f"{x:.1%}"


def render_report(meta: dict, bt: BacktestResult, k_scores: dict, winner) -> str:
    lines = [
        f"# Model evaluation: {meta['version']}",
        "",
        f"Generated {meta['trained_at'][:19]}Z. Data through {meta['data_through']} "
        f"(snapshot `{(meta['data_snapshot_sha256'] or 'n/a')[:12]}`). Feature set "
        f"`{meta['feature_set_version']}` (schema `{meta['schema_hash']}`).",
        "",
        "## Method",
        "",
        f"- Rolling backtest: for each test year Y in {bt.years[0]}–{bt.years[-1]}, models are fit on "
        f"bouts from {TRAIN_START_YEAR} to Y-2, calibrated on Y-1, and scored on Y. No random splits.",
        "- Every feature is computed from bouts strictly before the fight date (see `app/ml/features.py`).",
        "- Models are symmetric in fighter order, so metrics don't depend on how the source lists fighters.",
        "- Win-only model: draws and no-contests are excluded from targets (they're about 2% of bouts).",
        "- Bookmaker odds aren't used, either as features or (yet) as a benchmark.",
        "",
        "## Elo K selection (log loss, bouts 2005–2015)",
        "",
        "| K | log loss |",
        "|---:|---:|",
        *[f"| {k:g} | {v:.4f} |" for k, v in k_scores.items()],
        "",
        f"Selected K = {meta['elo_k']:g}.",
        "",
        "## Winner model, pooled over all test years",
        "",
        "| Model | Bouts | Log loss | Brier | Accuracy |",
        "|---|---:|---:|---:|---:|",
    ]
    for kind, m in bt.pooled.items():
        mark = " **(selected)**" if kind == meta["winner_model"] else ""
        lines.append(
            f"| {kind}{mark} | {m['n']} | {m['log_loss']:.4f} | {m['brier']:.4f} | {_pct(m['accuracy'])} |"
        )
    lines += ["", "### Log loss by test year", ""]
    kinds = list(bt.per_year)
    lines += ["| Year | " + " | ".join(kinds) + " |", "|---:|" + "---:|" * len(kinds)]
    for i, year in enumerate(bt.years):
        cells = [f"{bt.per_year[k][i]['log_loss']:.4f}" for k in kinds if i < len(bt.per_year[k])]
        lines.append(f"| {year} | " + " | ".join(cells) + " |")

    lines += [
        "",
        f"### Calibration: {meta['winner_model']} (favourite's probability vs. how often the favourite won)",
        "",
        "| Bucket | Bouts | Mean predicted | Observed |",
        "|---|---:|---:|---:|",
        *[
            f"| {c['bucket']} | {c['n']} | {_pct(c['mean_predicted'])} | {_pct(c['observed'])} |"
            for c in bt.calibration[meta["winner_model"]]
        ],
        "",
        "## Method of victory (conditional on the actual winner)",
        "",
        "| Model | Bouts | Log loss | Accuracy | Joint 6-outcome log loss |",
        "|---|---:|---:|---:|---:|",
    ]
    for kind, m in bt.method.items():
        mark = " **(selected)**" if kind == meta["method_model"] else ""
        lines.append(
            f"| {kind}{mark} | {m['n']} | {m['log_loss']:.4f} | {_pct(m['accuracy'])} | {m['joint_log_loss']:.4f} |"
        )
    lines += [
        "",
        "`prior` predicts training-set class frequencies. Joint log loss scores "
        "P(actual winner) × P(actual method | winner) using the best winner model.",
    ]
    if isinstance(winner, LogisticModel):
        coefs = sorted(
            zip(F.WINNER_FEATURES, winner.lr.coef_[0], strict=True),
            key=lambda t: abs(t[1]),
            reverse=True,
        )
        lines += [
            "",
            "## Logistic coefficients (standardized, before calibration)",
            "",
            "| Feature | Coefficient |",
            "|---|---:|",
            *[f"| `{f}` | {c:+.3f} |" for f, c in coefs],
        ]
    lines += [
        "",
        "## Known limitations",
        "",
        "- No per-bout striking/grappling statistics in the source, so there are no opponent-adjusted style features yet.",
        "- Common-opponent results aren't a feature: Elo already uses those same bouts, and adding both would count them twice.",
        "- Hype and popularity are excluded from the model, as the handoff requires.",
        "- Ages and reach come from current roster files. Static attributes are safe, but 104 fighters lack a DOB and 660 lack reach.",
        "",
    ]
    return "\n".join(lines)
