"""Live track record: score stored predictions against actual results.

Only predictions stored before the fight's calendar day (UTC) count as forecasts. Backtests
measure the method; this measures what was actually published.
"""

import math
from collections import defaultdict
from datetime import UTC, date, datetime
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Bout, Event, Prediction, PredictionResult
from app.schemas.common import FighterRef
from app.schemas.track_record import (
    CalibrationRow,
    Metrics,
    ModelVersionRecord,
    ScoredPick,
    TrackRecord,
)

EPS = 1e-6
BUCKETS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 1.0001]
RECENT_LIMIT = 50


def timing_of(created_at: datetime, event_date: date) -> str:
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    day = created.astimezone(UTC).date()
    return "pre_fight" if day < event_date else "same_day" if day == event_date else "after"


def score_predictions(session: Session) -> dict:
    """Score every stored prediction whose bout now has a result. Idempotent."""
    scored_ids = set(session.scalars(select(PredictionResult.prediction_id)))
    pending = session.scalars(
        select(Prediction)
        .join(Bout, Prediction.bout_id == Bout.id)
        .options(joinedload(Prediction.model_version))
        .where(Bout.status == "completed")
    ).all()
    counts = defaultdict(int)
    for p in pending:
        if p.id in scored_ids:
            continue
        bout = session.get(Bout, p.bout_id, options=[joinedload(Bout.event)])
        result = PredictionResult(
            prediction_id=p.id,
            bout_id=bout.id,
            timing=timing_of(p.created_at, bout.event.event_date),
            actual_outcome=bout.outcome,
            actual_method=bout.method,
        )
        pair = {p.fighter_a_id, p.fighter_b_id}
        if pair != {bout.fighter1_id, bout.fighter2_id}:
            # Made for a pairing that didn't happen (late replacement): never scored.
            result.status = "void"
            result.actual_outcome = "pairing_changed"
        elif bout.outcome != "win":
            result.status = "void"
        else:
            p_win = p.p_a if bout.winner_id == p.fighter_a_id else 1 - p.p_a
            result.status = "scored"
            result.p_actual_winner = p_win
            # A 50/50 call earns half credit, matching the backtest's accuracy metric.
            result.favourite_correct = None if p.p_a == 0.5 else p_win > 0.5
            result.log_loss = -math.log(max(p_win, EPS))
            result.brier = (1 - p_win) ** 2
            key = f"{bout.winner_id}:{bout.method}"
            result.p_actual_outcome = p.outcomes.get(key)
        session.add(result)
        counts[result.status] += 1
        counts[result.timing] += 1
    session.commit()
    return {
        "scored": counts["scored"],
        "void": counts["void"],
        "pre_fight": counts["pre_fight"],
        "same_day": counts["same_day"],
        "after": counts["after"],
    }


def _metrics(results: list[PredictionResult]) -> Metrics:
    scored = [r for r in results if r.status == "scored"]
    outcome = [r.p_actual_outcome for r in scored if r.p_actual_outcome is not None]
    if not scored:
        return Metrics(
            n=0, accuracy=None, log_loss=None, brier=None, mean_p_actual_outcome=None, n_outcome=0
        )
    hits = [0.5 if r.favourite_correct is None else float(r.favourite_correct) for r in scored]
    return Metrics(
        n=len(scored),
        accuracy=sum(hits) / len(scored),
        log_loss=sum(r.log_loss for r in scored) / len(scored),
        brier=sum(r.brier for r in scored) / len(scored),
        mean_p_actual_outcome=sum(outcome) / len(outcome) if outcome else None,
        n_outcome=len(outcome),
    )


def _calibration(results: list[PredictionResult]) -> list[CalibrationRow]:
    rows = []
    scored = [r for r in results if r.status == "scored"]
    for lo, hi in pairwise(BUCKETS):
        # Favourite's probability = max(p, 1-p); favourite won iff the winner got >= 0.5.
        bucket = [r for r in scored if lo <= max(r.p_actual_winner, 1 - r.p_actual_winner) < hi]
        if bucket:
            fav_p = [max(r.p_actual_winner, 1 - r.p_actual_winner) for r in bucket]
            rows.append(
                CalibrationRow(
                    bucket=f"{lo:.0%}-{min(hi, 1):.0%}",
                    n=len(bucket),
                    mean_predicted=sum(fav_p) / len(bucket),
                    observed=sum(r.p_actual_winner >= 0.5 for r in bucket) / len(bucket),
                )
            )
    return rows


def track_record(session: Session, today: date | None = None) -> TrackRecord:
    today = today or datetime.now(UTC).date()
    results = session.scalars(
        select(PredictionResult).options(
            joinedload(PredictionResult.prediction).joinedload(Prediction.model_version)
        )
    ).all()
    pre_fight = [r for r in results if r.timing == "pre_fight"]

    # Headline: the latest pre-fight prediction per bout (what a user last saw).
    latest: dict[int, PredictionResult] = {}
    for r in pre_fight:
        cur = latest.get(r.bout_id)
        if cur is None or (r.prediction.created_at, r.prediction.id) > (
            cur.prediction.created_at,
            cur.prediction.id,
        ):
            latest[r.bout_id] = r
    headline = list(latest.values())

    by_version: dict[str, list[PredictionResult]] = defaultdict(list)
    for r in pre_fight:
        by_version[r.prediction.model_version.version].append(r)

    pending = session.scalars(
        select(Prediction.bout_id)
        .join(Bout, Prediction.bout_id == Bout.id)
        .where(Bout.status == "scheduled")
        .distinct()
    ).all()
    next_event = session.execute(
        select(Event.name, Event.event_date)
        .join(Bout, Bout.event_id == Event.id)
        .join(Prediction, Prediction.bout_id == Bout.id)
        .where(Bout.status == "scheduled", Event.event_date >= today)
        .order_by(Event.event_date)
        .limit(1)
    ).first()

    return TrackRecord(
        headline=_metrics(headline),
        calibration=_calibration(headline),
        voided=sum(r.status == "void" for r in headline),
        pending=len(pending),
        excluded_not_pre_fight=len(
            {r.bout_id for r in results if r.timing != "pre_fight"} - set(latest)
        ),
        by_model_version=[
            ModelVersionRecord(model_version=v, metrics=_metrics(rs))
            for v, rs in sorted(by_version.items())
        ],
        recent=_recent(session, headline),
        next_event=next_event[0] if next_event else None,
        next_event_date=next_event[1] if next_event else None,
    )


def _recent(session: Session, headline: list[PredictionResult]) -> list[ScoredPick]:
    bouts = {
        b.id: b
        for b in session.scalars(
            select(Bout)
            .options(joinedload(Bout.event), joinedload(Bout.fighter1), joinedload(Bout.fighter2))
            .where(Bout.id.in_([r.bout_id for r in headline]))
        )
    }
    picks = []
    for r in headline:
        b, p = bouts[r.bout_id], r.prediction
        fa = b.fighter1 if b.fighter1_id == p.fighter_a_id else b.fighter2
        fb = b.fighter2 if fa is b.fighter1 else b.fighter1
        winner = None
        if b.winner_id is not None:
            w = b.fighter1 if b.winner_id == b.fighter1_id else b.fighter2
            winner = FighterRef(id=w.id, name=w.display_name)
        picks.append(
            ScoredPick(
                bout_id=b.id,
                event_name=b.event.name,
                event_date=b.event.event_date,
                fighter_a=FighterRef(id=fa.id, name=fa.display_name),
                fighter_b=FighterRef(id=fb.id, name=fb.display_name),
                p_a=p.p_a,
                winner=winner,
                actual_outcome=r.actual_outcome,
                actual_method=r.actual_method,
                p_actual_winner=r.p_actual_winner,
                favourite_correct=r.favourite_correct,
                model_version=p.model_version.version,
                status=r.status,
            )
        )
    picks.sort(key=lambda x: (x.event_date, x.bout_id), reverse=True)
    return picks[:RECENT_LIMIT]
