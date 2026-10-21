"""Phase 2 guards: leakage, order symmetry, probability arithmetic, artifact compatibility."""

import json
import math
import random
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from app.db.models import ModelVersion
from app.ml import features as F
from app.ml.artifacts import IncompatibleArtifact, ModelBundle, load_bundle, save_bundle
from app.ml.data import BoutRow, FighterStatic, StatLine
from app.ml.evaluate import backtest, method_matrix, winner_matrix
from app.ml.models import CatBoostModel, LogisticModel, MethodModel, outcome_distribution
from app.services import predictions
from tests.conftest import fighter_id


def _line(rng, skill, me, opp, seconds) -> StatLine:
    """Plausible per-fight stats where higher hidden skill lands more and wrestles more."""
    mins = seconds / 60
    landed = max(0, int(mins * (3.5 + skill[me] - 0.5 * skill[opp]) + rng.gauss(0, 3)))
    td = max(0, int(mins / 15 * (1 + skill[me]) + rng.random()))
    return StatLine(
        int(rng.random() < 0.1),
        landed,
        landed * 2 + 5,
        td,
        td + 2,
        0,
        int(mins * 20),
        landed // 2,
        landed // 4,
        landed - landed // 2 - landed // 4,
    )


def synthetic_league(seed: int = 1, n_fighters: int = 80, start=2005, end=2012):
    """Fighters with a hidden skill; better fighters win more and finish more."""
    rng = random.Random(seed)
    skill = {i: rng.gauss(0, 1) for i in range(1, n_fighters + 1)}
    statics = {
        i: FighterStatic(
            date(1985, 1, 1) + timedelta(days=rng.randint(0, 3000)),
            70 + rng.random() * 6,
            70 + rng.random() * 8,
            rng.choice(["Orthodox", "Southpaw"]),
        )
        for i in skill
    }
    bouts, bid, day = [], 1, date(start, 1, 1)
    while day.year <= end:
        for _ in range(6):
            a, b = rng.sample(list(skill), 2)
            p = 1 / (1 + math.exp(-(skill[a] - skill[b]) * 1.2))
            outcome = "draw" if rng.random() < 0.01 else "win"
            winner = (a if rng.random() < p else b) if outcome == "win" else None
            method = rng.choices(["KO/TKO", "SUB", "DEC"], [0.3, 0.2, 0.5])[0] if winner else "DEC"
            seconds = rng.randint(60, 900)
            stats = (
                (_line(rng, skill, a, b, seconds), _line(rng, skill, b, a, seconds))
                if rng.random() < 0.95
                else None
            )
            bouts.append(
                BoutRow(
                    bid,
                    day,
                    a,
                    b,
                    outcome,
                    winner,
                    method,
                    3,
                    rng.choice([3, 3, 3, 5]),
                    False,
                    "Lightweight",
                    seconds,
                    stats,
                )
            )
            bid += 1
        day += timedelta(days=14)
    return bouts, statics


@pytest.fixture(scope="module")
def league():
    return synthetic_league()


@pytest.fixture(autouse=True)
def _fresh_prediction_caches():
    predictions.reset_caches()
    yield
    predictions.reset_caches()


def _same(x: dict, y: dict) -> bool:
    return all((math.isnan(x[k]) and math.isnan(y[k])) or x[k] == y[k] for k in x)


def test_training_rows_never_see_later_bouts(league):
    bouts, statics = league
    full = F.build_training_rows(bouts, statics)
    cutoff = date(2009, 6, 1)
    truncated = F.build_training_rows([b for b in bouts if b.on < cutoff], statics)
    early_full = [r for r in full if r.bout.on < cutoff]
    assert len(early_full) == len(truncated)
    assert all(_same(x.winner_x, y.winner_x) for x, y in zip(early_full, truncated, strict=True))

    # Flipping every later result must not change a single earlier feature.
    flipped = [
        replace(b, winner=(b.f2 if b.winner == b.f1 else b.f1))
        if b.on >= cutoff and b.winner
        else b
        for b in bouts
    ]
    early_flipped = [r for r in F.build_training_rows(flipped, statics) if r.bout.on < cutoff]
    assert all(
        _same(x.winner_x, y.winner_x) for x, y in zip(early_full, early_flipped, strict=True)
    )


def test_same_day_bouts_do_not_see_each_other():
    statics = {i: FighterStatic(None, None, None, None) for i in (1, 2, 3)}
    d = date(2020, 1, 1)
    bouts = [
        BoutRow(1, d, 1, 2, "win", 1, "DEC", 3, 3, False, "Lightweight"),
        BoutRow(2, d, 1, 3, "win", 1, "DEC", 3, 3, False, "Lightweight"),  # tournament night
    ]
    rows = F.build_training_rows(bouts, statics)
    assert rows[1].winner_x["experience_diff"] == 0  # fighter 1's first bout that night unseen
    assert rows[1].winner_x["elo_diff"] == 0


def test_winner_features_are_antisymmetric(league):
    bouts, statics = league
    engine = F.HistoryEngine(statics)
    engine.replay(bouts, before=date(2011, 1, 1))
    on, ctx = date(2011, 1, 1), F.Context(5, True, "Lightweight")
    for a, b in [(1, 2), (5, 9), (10, 40)]:
        ab, ba = engine.winner_features(a, b, on, ctx), engine.winner_features(b, a, on, ctx)
        for k in F.WINNER_FEATURES:
            assert (math.isnan(ab[k]) and math.isnan(ba[k])) or ab[k] == pytest.approx(-ba[k]), k


def test_h2h_decays_with_time():
    statics = {1: FighterStatic(None, None, None, None), 2: FighterStatic(None, None, None, None)}
    engine = F.HistoryEngine(statics)
    engine.replay([BoutRow(1, date(2018, 1, 1), 1, 2, "win", 1, "DEC", 3, 3, False, None)])
    fresh = engine.h2h_score(1, 2, date(2018, 6, 1))
    old = engine.h2h_score(1, 2, date(2024, 1, 1))
    assert fresh > 0.8 and old < 0.1 and engine.h2h_score(2, 1, date(2018, 6, 1)) == -fresh


@pytest.mark.parametrize("model_cls", [LogisticModel, lambda: CatBoostModel(iterations=60)])
def test_models_are_order_symmetric(league, model_cls):
    rows = F.build_training_rows(*league)
    X, y = winner_matrix(rows)
    model = model_cls().fit(X, y)
    model.calibrator.fit(model.raw(X[:300]), y[:300])
    p, p_rev = model.predict(X[:200]), model.predict(-X[:200])
    np.testing.assert_allclose(p + p_rev, 1.0, atol=1e-9)


def test_outcome_distribution_sums_to_one():
    out = outcome_distribution(
        0.57, np.array([0.28, 0.09, 0.20]) / 0.57, np.array([0.17, 0.08, 0.18]) / 0.43
    )
    assert sum(out.values()) == pytest.approx(1.0, abs=1e-12)
    assert out["a:KO/TKO"] == pytest.approx(0.28)
    with pytest.raises(ValueError):
        outcome_distribution(0.5, np.array([0.5, 0.5, 0.5]), np.array([1, 0, 0]))


def test_method_model_rows_sum_to_one(league):
    rows = F.build_training_rows(*league)
    Xm, ym = method_matrix(rows)
    proba = MethodModel("logistic").fit(Xm, ym).predict(Xm[:50])
    np.testing.assert_allclose(proba.sum(axis=1), 1.0)
    assert proba.shape == (50, len(F.METHOD_CLASSES))


def test_backtest_learns_hidden_skill(league):
    rows = F.build_training_rows(*league)
    result = backtest(
        rows, [2010, 2011, 2012], winner_kinds=("elo", "logistic"), method_kinds=("logistic",)
    )
    assert result.pooled["logistic"]["log_loss"] < result.pooled["coin_flip"]["log_loss"] - 0.02
    assert result.pooled["elo"]["accuracy"] > 0.55
    assert {c["bucket"] for c in result.calibration["logistic"]} <= {
        "50%-55%",
        "55%-60%",
        "60%-65%",
        "65%-70%",
        "70%-75%",
        "75%-80%",
        "80%-100%",
    }


# --- artifacts and API --------------------------------------------------------------------


def _bundle(league, version="test-logistic") -> ModelBundle:
    rows = F.build_training_rows(*league)
    X, y = winner_matrix(rows)
    winner = LogisticModel().fit(X, y)
    winner.calibrator.fit(winner.raw(X), y)
    method = MethodModel("logistic").fit(*method_matrix(rows))
    from app.ml.artifacts import current_schema

    return ModelBundle(
        version, winner, method, {"version": version, "elo_k": 96, **current_schema()}
    )


def test_bundle_roundtrip_and_schema_refusal(league, tmp_path):
    path = save_bundle(tmp_path / "m1", _bundle(league), "# report")
    loaded = load_bundle(path)
    assert loaded.version == "test-logistic"

    meta = json.loads((path / "metadata.json").read_text())
    meta["winner_features"] = meta["winner_features"][:-1]
    (path / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(IncompatibleArtifact):
        load_bundle(path)


def _activate(session, path, version="test-logistic", trained_through=date(2020, 1, 1)):
    session.add(
        ModelVersion(
            version=version,
            feature_set_version=F.FEATURE_SET_VERSION,
            schema_hash=F.schema_hash(),
            winner_model="logistic",
            method_model="logistic",
            artifact_path=str(path),
            trained_through=trained_through,
            metrics={},
            is_active=True,
        )
    )
    session.commit()


def test_prediction_api_without_model_is_503(client, loaded):
    a, b = fighter_id(loaded, "Alpha Ace"), fighter_id(loaded, "Bravo Bell")
    res = client.post("/api/predictions/matchup", json={"fighterA": a, "fighterB": b})
    assert res.status_code == 503


def test_prediction_api_end_to_end(client, loaded, league, tmp_path):
    _activate(loaded, save_bundle(tmp_path / "m", _bundle(league), "# r"))
    a, b = fighter_id(loaded, "Alpha Ace"), fighter_id(loaded, "Bravo Bell")

    body = client.post(
        "/api/predictions/matchup",
        json={"fighterA": a, "fighterB": b, "asOf": "2026-10-20", "scheduledRounds": 5},
    ).json()
    assert body["win_probability"]["a"] + body["win_probability"]["b"] == pytest.approx(1.0)
    assert sum(o["probability"] for o in body["outcomes"]) == pytest.approx(1.0)
    assert len(body["outcomes"]) == 6 and body["model_version"] == "test-logistic"
    assert body["in_sample"] is False and body["stored"] is False
    assert 1 <= len(body["unknowns"]) <= 3

    # Swapping the fighters mirrors the probabilities exactly.
    rev = client.post(
        "/api/predictions/matchup",
        json={"fighterA": b, "fighterB": a, "asOf": "2026-10-20", "scheduledRounds": 5},
    ).json()
    assert rev["win_probability"]["a"] == pytest.approx(body["win_probability"]["b"], abs=1e-12)

    # Batch job stores the scheduled bout; the card and the bout endpoint then serve it.
    summary = predictions.batch_predict_scheduled(loaded)
    assert summary["created"] == 1 and predictions.batch_predict_scheduled(loaded)["created"] == 0
    event = client.get("/api/events/upcoming").json()[0]
    card = client.get(f"/api/events/{event['id']}").json()
    pred = card["bouts"][0]["prediction"]
    assert pred["p_1"] + pred["p_2"] == pytest.approx(1.0)
    assert card["bouts"][0]["scheduled_rounds_source"] == "source"
    stored = client.get(f"/api/predictions/{card['bouts'][0]['bout_id']}").json()
    assert stored["stored"] is True


def test_completed_bout_prediction_is_flagged_in_sample(client, loaded, league, tmp_path):
    _activate(
        loaded,
        save_bundle(tmp_path / "m", _bundle(league), "# r"),
        trained_through=date(2025, 1, 1),
    )
    from sqlalchemy import select

    from app.db.models import Bout

    bout_id = loaded.scalar(select(Bout.id).where(Bout.external_key == "b07"))
    body = client.get(f"/api/predictions/{bout_id}").json()
    assert body["in_sample"] is True


def test_incompatible_active_artifact_refuses_inference(client, loaded, league, tmp_path):
    path = save_bundle(tmp_path / "m", _bundle(league), "# r")
    meta = json.loads((path / "metadata.json").read_text())
    meta["feature_set_version"] = "fs-0"
    (path / "metadata.json").write_text(json.dumps(meta))
    _activate(loaded, path)
    a, b = fighter_id(loaded, "Alpha Ace"), fighter_id(loaded, "Bravo Bell")
    res = client.post("/api/predictions/matchup", json={"fighterA": a, "fighterB": b})
    assert res.status_code == 503 and "different feature schema" in res.json()["detail"]


def test_every_winner_feature_is_explained_exactly_once():
    from app.ml.predict import REASON_GROUPS

    grouped = [f for members in REASON_GROUPS.values() for f in members]
    assert sorted(grouped) == sorted(F.WINNER_FEATURES)


def test_later_stats_never_change_earlier_features(league):
    bouts, statics = league
    cutoff = date(2009, 6, 1)
    full = [r for r in F.build_training_rows(bouts, statics) if r.bout.on < cutoff]
    tampered = [
        replace(b, stats=(b.stats[1], b.stats[0]), seconds=b.seconds + 300)
        if b.on >= cutoff and b.stats
        else b
        for b in bouts
    ]
    early = [r for r in F.build_training_rows(tampered, statics) if r.bout.on < cutoff]
    assert all(_same(x.winner_x, y.winner_x) for x, y in zip(full, early, strict=True))
    assert repr([r.method_x_f1 for r in full]) == repr([r.method_x_f1 for r in early])


def test_style_starts_from_fallback_priors_and_learns(league):
    from app.ml.style import FALLBACK

    bouts, statics = league
    first = F.build_training_rows(bouts, statics)[0]
    assert first.winner_x["slpm_diff"] == 0 and first.winner_x["stats_minutes_diff"] == 0
    assert first.method_x_f1["w_slpm"] == pytest.approx(FALLBACK["slpm"])

    # By the end, opponent-adjusted striking ranks fighters roughly by hidden skill.
    engine = F.HistoryEngine(statics)
    engine.replay(bouts)
    end = bouts[-1].on
    rng = random.Random(1)
    skill = {i: rng.gauss(0, 1) for i in range(1, 81)}  # same draw as synthetic_league(seed=1)
    top = sorted(skill, key=skill.get)[-10:]
    bottom = sorted(skill, key=skill.get)[:10]
    adj = lambda f: engine.snapshot(f, end).style.adj_str_off  # noqa: E731
    assert sum(map(adj, top)) / 10 > sum(map(adj, bottom)) / 10
