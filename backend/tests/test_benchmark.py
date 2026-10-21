"""Bookmaker odds: conversion math, matching, and the guarantee that they never reach the model."""

import ast
import csv
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.benchmarks.market import MarketLine, compare_to_market, implied, market_p_f1, market_six
from app.benchmarks.odds import import_odds
from app.db.models import BenchmarkOdds, Bout
from app.ml import features as F
from app.ml.data import load_history
from app.ml.evaluate import BacktestResult
from tests.conftest import fighter_id

APP = Path(__file__).resolve().parents[1] / "app"
# Everything that produces features, fits models or serves predictions.
MODEL_PATH_MODULES = [
    "ml/data.py",
    "ml/features.py",
    "ml/models.py",
    "ml/predict.py",
    "ml/artifacts.py",
    "ml/evaluate.py",
    "services/predictions.py",
    "services/history.py",
]


def test_implied_probability_and_margin_removal():
    assert implied(-150) == pytest.approx(0.6)
    assert implied(150) == pytest.approx(0.4)
    p, overround = market_p_f1(MarketLine(-200, 170, (None,) * 6))
    assert p == pytest.approx((2 / 3) / (2 / 3 + 100 / 270))
    assert overround == pytest.approx(2 / 3 + 100 / 270 - 1)


def test_market_six_normalizes_and_requires_all_props():
    six = market_six(MarketLine(-150, 130, (200, 400, 150, 500, 900, 300)))
    assert six.sum() == pytest.approx(1.0)
    assert market_six(MarketLine(-150, 130, (200, None, 150, 500, 900, 300))) is None


@pytest.mark.parametrize("module", MODEL_PATH_MODULES)
def test_model_path_never_touches_odds(module):
    """Static guard: no import of the benchmark package or odds table on the model path."""
    tree = ast.parse((APP / module).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("app.benchmarks"), module
            assert "BenchmarkOdds" not in [a.name for a in node.names], module
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("app.benchmarks") for a in node.names), module
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            assert "odds" not in name.lower(), f"{module} references {name}"


ODDS_COLUMNS = [
    "R_fighter",
    "B_fighter",
    "R_odds",
    "B_odds",
    "date",
    "Winner",
    "r_ko_odds",
    "b_ko_odds",
    "r_sub_odds",
    "b_sub_odds",
    "r_dec_odds",
    "b_dec_odds",
]


def _odds_csv(path: Path, rows: list[dict]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ODDS_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in ODDS_COLUMNS})
    return path


def _row(red, blue, date, winner, r_odds=-150, b_odds=130, **props):
    return {
        "R_fighter": red,
        "B_fighter": blue,
        "date": date,
        "Winner": winner,
        "R_odds": r_odds,
        "B_odds": b_odds,
        **props,
    }


def test_import_maps_corners_onto_bout_order(loaded, tmp_path):
    rows = [
        # Bravo listed red, but the bout stores Alpha as fighter1: moneylines must swap.
        _row(
            "Bravo Bell", "Alpha Ace", "2024-08-17", "Blue", -200, 170, r_ko_odds=300, b_ko_odds=250
        ),
        _row("Cole Charlie", "Alpha Ace", "2019-03-02", "Blue"),  # reordered name -> fuzzy
        _row("Bravo Bel", "Charlie Cole", "2020-05-09", "Red"),  # misspelling -> fuzzy
        _row("Nobody Known", "Alpha Ace", "2019-03-02", "Red"),  # unmatched
        _row("Bravo Bell", "Alpha Ace", "2021-01-16", "Blue"),  # Bravo actually won
        _row("Alpha Ace", "Delta Dunn", "2022-06-04", "Red", r_odds=""),  # no moneyline
    ]
    report = import_odds(loaded, _odds_csv(tmp_path / "odds.csv", rows))
    assert report.inserted == 3 and report.fuzzy_matches == 2
    assert len(report.issues["unmatched"]) == 1
    assert len(report.issues["winner_mismatch"]) == 1
    assert len(report.issues["no_moneyline"]) == 1

    b07 = loaded.scalar(select(Bout).where(Bout.external_key == "b07"))
    assert b07.fighter1_id == fighter_id(loaded, "Alpha Ace")
    odds = loaded.scalar(select(BenchmarkOdds).where(BenchmarkOdds.bout_id == b07.id))
    assert (odds.f1_moneyline, odds.f2_moneyline, odds.f1_ko, odds.f2_ko) == (170, -200, 250, 300)

    again = import_odds(loaded, _odds_csv(tmp_path / "odds.csv", rows))
    assert (again.inserted, again.unchanged, again.removed) == (0, 3, 0)
    pruned = import_odds(loaded, _odds_csv(tmp_path / "odds2.csv", rows[:1]))
    assert pruned.removed == 2


def test_training_rows_identical_with_and_without_odds(loaded, tmp_path):
    before = F.build_training_rows(*load_history(loaded))
    import_odds(
        loaded,
        _odds_csv(tmp_path / "o.csv", [_row("Bravo Bell", "Alpha Ace", "2024-08-17", "Blue")]),
    )
    after = F.build_training_rows(*load_history(loaded))
    # repr() makes NaN compare equal to NaN, so this checks every value exactly.
    assert repr(
        [(r.bout.bout_id, r.winner_x, r.method_x_f1, r.method_x_f2) for r in before]
    ) == repr([(r.bout.bout_id, r.winner_x, r.method_x_f1, r.method_x_f2) for r in after])


def test_compare_to_market_uses_only_shared_bouts():
    bt = BacktestResult(years=[2024])
    bt.bout_p_f1 = {"logistic": {1: 0.7, 2: 0.4, 3: 0.55}}
    d = np.array([0.3, 0.2, 0.5])
    bt.bout_methods = {"logistic": {1: (d, d), 2: (d, d), 3: (d, d)}}
    lines = {
        1: MarketLine(-300, 250, (200, 400, 150, 500, 900, 300)),
        2: MarketLine(150, -170, (None,) * 6),
        99: MarketLine(-110, -110, (None,) * 6),  # no model prediction: excluded
    }
    truth = {1: (True, "DEC", 2024), 2: (False, "KO/TKO", 2024), 3: (True, "SUB", 2024)}
    out = compare_to_market(bt, lines, truth, "logistic", "logistic")
    assert out["n"] == 2 and out["years"] == [2024]
    assert out["winner"]["market"]["n"] == out["winner"]["logistic"]["n"] == 2
    assert out["favourite_agreement"] == 1.0
    assert out["six_outcome"]["n"] == 1
