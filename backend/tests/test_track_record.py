import math
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.db.models import Bout, ModelVersion, Prediction, PredictionResult
from app.ingestion.fightr import import_snapshot
from app.ml import features as F
from app.ml.artifacts import save_bundle
from app.services import predictions
from app.services.track_record import score_predictions, timing_of, track_record
from tests.conftest import bout, default_bouts, fighter_id, write_snapshot
from tests.test_ml import _activate, _bundle, synthetic_league


@pytest.fixture(autouse=True)
def _fresh_caches():
    predictions.reset_caches()
    yield
    predictions.reset_caches()


def _mv(session, version="manual") -> ModelVersion:
    mv = ModelVersion(
        version=version,
        feature_set_version=F.FEATURE_SET_VERSION,
        schema_hash=F.schema_hash(),
        winner_model="logistic",
        method_model="logistic",
        artifact_path="-",
        trained_through=date(2020, 1, 1),
        metrics={},
        is_active=False,
    )
    session.add(mv)
    session.flush()
    return mv


def _predict(session, b: Bout, mv: ModelVersion, p_a: float, created: datetime) -> Prediction:
    outcomes = {
        f"{b.fighter1_id}:KO/TKO": p_a * 0.3,
        f"{b.fighter1_id}:SUB": p_a * 0.2,
        f"{b.fighter1_id}:DEC": p_a * 0.5,
        f"{b.fighter2_id}:KO/TKO": (1 - p_a) * 0.3,
        f"{b.fighter2_id}:SUB": (1 - p_a) * 0.2,
        f"{b.fighter2_id}:DEC": (1 - p_a) * 0.5,
    }
    pred = Prediction(
        bout_id=b.id,
        fighter_a_id=b.fighter1_id,
        fighter_b_id=b.fighter2_id,
        model_version_id=mv.id,
        feature_set_version=mv.feature_set_version,
        as_of=b.event.event_date,
        scheduled_rounds=3,
        p_a=p_a,
        outcomes=outcomes,
        created_at=created,
        payload={
            "outcomes": [
                {"fighter_id": int(k.split(":")[0]), "method": k.split(":")[1], "probability": v}
                for k, v in outcomes.items()
            ],
            "fighter_a": {"id": b.fighter1_id, "name": b.fighter1.display_name},
            "fighter_b": {"id": b.fighter2_id, "name": b.fighter2.display_name},
        },
    )
    session.add(pred)
    session.commit()
    return pred


def _bout(session, key: str) -> Bout:
    return session.scalar(select(Bout).where(Bout.external_key == key))


def test_timing_classification():
    event = date(2026, 10, 24)
    assert timing_of(datetime(2026, 10, 23, 23, 59, tzinfo=UTC), event) == "pre_fight"
    assert timing_of(datetime(2026, 10, 24, 1, 0), event) == "same_day"  # naive = UTC
    assert timing_of(datetime(2026, 10, 25, tzinfo=UTC), event) == "after"


def test_full_lifecycle_scheduled_to_scored(client, loaded, tmp_path):
    _activate(loaded, save_bundle(tmp_path / "m", _bundle(synthetic_league()), "# r"))
    assert predictions.batch_predict_scheduled(loaded)["created"] == 1
    assert score_predictions(loaded)["scored"] == 0  # bout not fought yet
    assert track_record(loaded).pending == 1

    rows = default_bouts()
    rows[-1] = bout(
        "b10",
        "UFC 999",
        "January 01, 2099",
        "Alpha Ace",
        "W",
        "Charlie Cole",
        "L",
        "UFC Welterweight Title Bout",
        "Submission",
        "4",
        "1:00",
        fmt="5 Rnd (5-5-5-5-5)",
    )
    import_snapshot(loaded, write_snapshot(tmp_path / "next", rows))
    summary = score_predictions(loaded)
    assert summary == {"scored": 1, "void": 0, "pre_fight": 1, "same_day": 0, "after": 0}
    assert score_predictions(loaded)["scored"] == 0  # idempotent

    pred = loaded.scalar(select(Prediction))
    alpha = fighter_id(loaded, "Alpha Ace")
    p_win = pred.p_a if pred.fighter_a_id == alpha else 1 - pred.p_a
    res = loaded.scalar(select(PredictionResult))
    assert res.p_actual_winner == pytest.approx(p_win)
    assert res.log_loss == pytest.approx(-math.log(p_win))
    assert res.favourite_correct == (p_win > 0.5)
    assert res.p_actual_outcome == pytest.approx(pred.outcomes[f"{alpha}:SUB"])

    tr = client.get("/api/track-record").json()
    assert tr["headline"]["n"] == 1 and tr["pending"] == 0
    assert tr["recent"][0]["winner"]["name"] == "Alpha Ace"

    # The finished card shows the pre-fight pick with its result.
    card = client.get(f"/api/events/{_bout(loaded, 'b10').event_id}").json()
    assert card["bouts"][0]["prediction"]["result"]["favourite_correct"] == (p_win > 0.5)


def test_hindsight_and_void_predictions(loaded):
    mv = _mv(loaded)
    _predict(
        loaded, _bout(loaded, "b07"), mv, 0.6, datetime(2026, 1, 1, tzinfo=UTC)
    )  # after the 2024 bout
    _predict(
        loaded, _bout(loaded, "b06"), mv, 0.5, datetime(2023, 1, 1, tzinfo=UTC)
    )  # draw, pre-fight
    summary = score_predictions(loaded)
    assert summary["after"] == 1 and summary["void"] == 1
    tr = track_record(loaded)
    assert tr.headline.n == 0  # neither counts as a scored forecast
    assert tr.voided == 1
    assert tr.excluded_not_pre_fight == 1


def test_headline_uses_latest_pre_fight_prediction_per_bout(loaded):
    old, new = _mv(loaded, "v-old"), _mv(loaded, "v-new")
    b = _bout(loaded, "b07")  # Alpha (fighter1) beat Bravo
    _predict(loaded, b, old, 0.30, datetime(2024, 8, 1, tzinfo=UTC))
    _predict(loaded, b, new, 0.70, datetime(2024, 8, 10, tzinfo=UTC))
    score_predictions(loaded)
    tr = track_record(loaded)
    assert tr.headline.n == 1
    assert tr.headline.accuracy == 1.0 and tr.headline.log_loss == pytest.approx(-math.log(0.7))
    assert {r.model_version: r.metrics.n for r in tr.by_model_version} == {"v-old": 1, "v-new": 1}
    assert tr.calibration[0].bucket == "70%-75%" and tr.calibration[0].observed == 1.0
