"""Prediction orchestration: active model loading, history caching, storage, batch jobs.

Nothing here trains or scrapes. Requests use the approved artifact and cached history.
"""

from collections import OrderedDict
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Bout,
    Event,
    Fighter,
    IngestionRun,
    ModelVersion,
    Prediction,
    PredictionResult,
)
from app.ml import features as F
from app.ml.artifacts import ModelBundle, load_bundle
from app.ml.data import BoutRow, FighterStatic, load_history
from app.ml.features import Context, HistoryEngine
from app.ml.predict import RawPrediction, predict_pair
from app.schemas.common import FighterRef
from app.schemas.predictions import (
    CardPrediction,
    CardResult,
    DataConfidence,
    Outcome,
    PredictionOut,
    Reason,
)
from app.services.history import NON_DIVISIONS

METHOD_WORD = {"KO/TKO": "KO/TKO", "SUB": "submission", "DEC": "decision"}
_ENGINE_CACHE_SIZE = 8
_RESULT_CACHE_SIZE = 256


class NoActiveModel(RuntimeError):
    pass


class _State:
    bundle: ModelBundle | None = None
    history_key: tuple | None = None
    history: tuple[list[BoutRow], dict[int, FighterStatic]] | None = None
    engines: OrderedDict = OrderedDict()
    results: OrderedDict = OrderedDict()


_state = _State()


def reset_caches() -> None:
    _state.bundle = None
    _state.history_key = None
    _state.history = None
    _state.engines.clear()
    _state.results.clear()


def active_bundle(session: Session) -> tuple[ModelVersion, ModelBundle]:
    mv = session.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
    if mv is None:
        raise NoActiveModel("No active model. Run `fightlens train --activate`.")
    if _state.bundle is None or _state.bundle.version != mv.version:
        _state.bundle = load_bundle(Path(mv.artifact_path))  # raises on schema mismatch
        _state.engines.clear()
        _state.results.clear()
    return mv, _state.bundle


def _history(session: Session) -> tuple[list[BoutRow], dict[int, FighterStatic]]:
    # Reload whenever a new import has happened or bout counts change.
    key = (
        session.scalar(select(func.max(IngestionRun.id))),
        session.scalar(select(func.count(Bout.id)).where(Bout.status == "completed")),
    )
    if key != _state.history_key:
        _state.history = load_history(session)
        _state.history_key = key
        _state.engines.clear()
        _state.results.clear()
    return _state.history


def _engine(session: Session, bundle: ModelBundle, as_of: date) -> HistoryEngine:
    bouts, statics = _history(session)
    key = (bundle.version, as_of)
    if key not in _state.engines:
        engine = HistoryEngine(statics, bundle.elo_k)
        engine.replay(bouts, before=as_of)
        _state.engines[key] = engine
        while len(_state.engines) > _ENGINE_CACHE_SIZE:
            _state.engines.popitem(last=False)
    _state.engines.move_to_end(key)
    return _state.engines[key]


def _division_for(session: Session, a: int, b: int, as_of: date) -> str | None:
    """Most recent real division both fighters share; None if they last fought in different ones."""

    def latest(fid: int) -> str | None:
        rows = session.execute(
            select(Bout.division)
            .join(Bout.event)
            .where(
                Bout.status == "completed",
                Event.event_date < as_of,
                (Bout.fighter1_id == fid) | (Bout.fighter2_id == fid),
            )
            .order_by(Event.event_date.desc())
        ).scalars()
        return next((d for d in rows if d not in NON_DIVISIONS), None)

    da, db = latest(a), latest(b)
    return da if da == db else None


def predict_matchup(
    session: Session,
    a: Fighter,
    b: Fighter,
    as_of: date,
    scheduled_rounds: int | None,
    is_title: bool,
    division: str | None = None,
    rounds_source: str | None = "request",
) -> PredictionOut:
    mv, bundle = active_bundle(session)
    _history(session)  # refresh cache keys before consulting the result cache
    division = division or _division_for(session, a.id, b.id, as_of)
    key = (mv.version, _state.history_key, a.id, b.id, as_of, scheduled_rounds, is_title, division)
    if key in _state.results:
        return _state.results[key]
    ctx = Context(scheduled_rounds, is_title, division)
    raw = predict_pair(
        bundle,
        _engine(session, bundle, as_of),
        a.id,
        b.id,
        as_of,
        ctx,
        (a.display_name, b.display_name),
    )
    out = _to_schema(raw, a, b, as_of, scheduled_rounds, rounds_source, mv, stored=False)
    _state.results[key] = out
    while len(_state.results) > _RESULT_CACHE_SIZE:
        _state.results.popitem(last=False)
    return out


def _to_schema(
    raw: RawPrediction,
    a: Fighter,
    b: Fighter,
    as_of,
    rounds,
    rounds_source,
    mv,
    stored,
    generated_at=None,
) -> PredictionOut:
    outcomes = [
        Outcome(fighter_id=(a.id if side == "a" else b.id), method=method, probability=p)
        for key, p in raw.outcomes.items()
        for side, method in [key.split(":")]
    ]
    return PredictionOut(
        fighter_a=FighterRef(id=a.id, name=a.display_name),
        fighter_b=FighterRef(id=b.id, name=b.display_name),
        as_of=as_of,
        scheduled_rounds=rounds,
        scheduled_rounds_source=rounds_source,
        model_version=mv.version,
        feature_set_version=mv.feature_set_version,
        generated_at=generated_at or datetime.now(UTC),
        stored=stored,
        in_sample=as_of <= mv.trained_through,
        win_probability={"a": raw.p_a, "b": 1 - raw.p_a},
        method_given_win={
            "a": dict(zip(F.METHOD_CLASSES, map(float, raw.method_a), strict=True)),
            "b": dict(zip(F.METHOD_CLASSES, map(float, raw.method_b), strict=True)),
        },
        outcomes=outcomes,
        reasons={
            "a": [Reason(**r) for r in raw.reasons_a],
            "b": [Reason(**r) for r in raw.reasons_b],
        },
        unknowns=raw.unknowns,
        data_confidence=DataConfidence(level=raw.confidence[0], reasons=raw.confidence[1]),
    )


def predict_bout(session: Session, bout_id: int) -> PredictionOut | None:
    """Stored prediction for the active model if the batch job made one, else computed live."""
    bout = session.get(
        Bout,
        bout_id,
        options=[joinedload(Bout.event), joinedload(Bout.fighter1), joinedload(Bout.fighter2)],
    )
    if bout is None:
        return None
    mv, _ = active_bundle(session)
    stored = session.scalar(
        select(Prediction).where(
            Prediction.bout_id == bout_id,
            Prediction.model_version_id == mv.id,
            Prediction.as_of == bout.event.event_date,
        )
    )
    if stored is not None:
        return PredictionOut.model_validate(
            {**stored.payload, "stored": True, "in_sample": stored.as_of <= mv.trained_through}
        )
    return predict_matchup(
        session,
        bout.fighter1,
        bout.fighter2,
        bout.event.event_date,
        bout.scheduled_rounds,
        bout.is_title_bout,
        bout.division,
        bout.scheduled_rounds_source,
    )


def batch_predict_scheduled(session: Session) -> dict:
    """Store predictions for every scheduled bout under the active model. Idempotent."""
    mv, _ = active_bundle(session)
    bouts = session.scalars(
        select(Bout)
        .options(joinedload(Bout.event), joinedload(Bout.fighter1), joinedload(Bout.fighter2))
        .where(Bout.status == "scheduled")
    ).all()
    created = skipped = 0
    for bout in bouts:
        as_of = bout.event.event_date
        exists = session.scalar(
            select(Prediction.id).where(
                Prediction.bout_id == bout.id,
                Prediction.model_version_id == mv.id,
                Prediction.as_of == as_of,
            )
        )
        if exists:
            skipped += 1
            continue
        out = predict_matchup(
            session,
            bout.fighter1,
            bout.fighter2,
            as_of,
            bout.scheduled_rounds,
            bout.is_title_bout,
            bout.division,
            bout.scheduled_rounds_source,
        )
        session.add(
            Prediction(
                bout_id=bout.id,
                fighter_a_id=bout.fighter1_id,
                fighter_b_id=bout.fighter2_id,
                model_version_id=mv.id,
                feature_set_version=mv.feature_set_version,
                as_of=as_of,
                scheduled_rounds=bout.scheduled_rounds,
                p_a=out.win_probability["a"],
                outcomes={f"{o.fighter_id}:{o.method}": o.probability for o in out.outcomes},
                payload=out.model_dump(mode="json", exclude={"stored", "in_sample"}),
            )
        )
        created += 1
    session.commit()
    return {"model_version": mv.version, "created": created, "already_stored": skipped}


def card_predictions(session: Session, bout_ids: list[int]) -> dict[int, CardPrediction]:
    """Predictions for a card, keyed by bout id.

    Scheduled bouts get the active model's stored prediction. Completed bouts get the latest
    prediction stored *before fight day* by whichever model was active then, with its result;
    hindsight predictions are never shown as if they were forecasts.
    """
    if not bout_ids:
        return {}
    mv = session.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
    status = dict(session.execute(select(Bout.id, Bout.status).where(Bout.id.in_(bout_ids))).all())
    results = {
        r.prediction_id: r
        for r in session.scalars(
            select(PredictionResult).where(PredictionResult.bout_id.in_(bout_ids))
        )
    }
    rows = session.scalars(
        select(Prediction)
        .options(joinedload(Prediction.model_version))
        .where(Prediction.bout_id.in_(bout_ids))
        .order_by(Prediction.created_at.desc(), Prediction.id.desc())
    ).all()
    out: dict[int, CardPrediction] = {}
    for p in rows:
        if p.bout_id in out:
            continue
        result = results.get(p.id)
        if status[p.bout_id] == "completed":
            if result is None or result.timing != "pre_fight":
                continue
        elif mv is None or p.model_version_id != mv.id:
            continue
        best = max(p.payload["outcomes"], key=lambda o: o["probability"])
        name = (
            p.payload["fighter_a"]["name"]
            if best["fighter_id"] == p.fighter_a_id
            else p.payload["fighter_b"]["name"]
        )
        out[p.bout_id] = CardPrediction(
            p_1=p.p_a,
            p_2=1 - p.p_a,
            likely_outcome=f"{name} by {METHOD_WORD[best['method']]}",
            likely_outcome_probability=best["probability"],
            model_version=p.model_version.version,
            generated_at=p.created_at or datetime.now(UTC),
            result=(
                CardResult(
                    status=result.status,
                    favourite_correct=result.favourite_correct,
                    p_actual_winner=result.p_actual_winner,
                    p_actual_outcome=result.p_actual_outcome,
                )
                if result is not None
                else None
            ),
        )
    return out
