"""Metrics and rolling chronological backtests.

Metrics are computed from P(fighter 1 wins) against the outcome. Because every model is
symmetric, log loss, Brier and accuracy are independent of which fighter is listed first.
"""

from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np

from app.ml.features import METHOD_CLASSES, METHOD_FEATURES, WINNER_FEATURES, TrainingRow
from app.ml.models import EPS, WINNER_MODELS, MethodModel

TRAIN_START_YEAR = 2005  # pre-2005 bouts feed fighter histories but aren't training targets
CALIBRATION_BUCKETS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 1.0001]


def winner_matrix(rows: list[TrainingRow]) -> tuple[np.ndarray, np.ndarray]:
    X = np.array([[r.winner_x[f] for f in WINNER_FEATURES] for r in rows], dtype=float)
    y = np.array([1.0 if r.f1_won else 0.0 for r in rows])
    return X, y


def method_matrix(rows: list[TrainingRow]) -> tuple[np.ndarray, list[str]]:
    usable = [r for r in rows if r.method_y is not None]
    X = np.array([[r.method_x[f] for f in METHOD_FEATURES] for r in usable], dtype=float)
    return X.reshape(-1, len(METHOD_FEATURES)), [r.method_y for r in usable]


def winner_metrics(p: np.ndarray, y: np.ndarray) -> dict:
    pc = np.clip(p, EPS, 1 - EPS)
    correct = np.where(p == 0.5, 0.5, ((p > 0.5) == (y == 1)).astype(float))
    return {
        "n": int(len(y)),
        "log_loss": float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc))),
        "brier": float(np.mean((p - y) ** 2)),
        "accuracy": float(np.mean(correct)),
    }


def calibration_table(p: np.ndarray, y: np.ndarray) -> list[dict]:
    """Reliability by bucket of the favourite's probability (both orientations pooled)."""
    fav_p = np.maximum(p, 1 - p)
    fav_won = np.where(p >= 0.5, y, 1 - y)
    table = []
    for lo, hi in pairwise(CALIBRATION_BUCKETS):
        mask = (fav_p >= lo) & (fav_p < hi)
        if mask.any():
            table.append(
                {
                    "bucket": f"{lo:.0%}-{min(hi, 1):.0%}",
                    "n": int(mask.sum()),
                    "mean_predicted": float(fav_p[mask].mean()),
                    "observed": float(fav_won[mask].mean()),
                }
            )
    return table


def method_metrics(proba: np.ndarray, y: list[str], p_winner: np.ndarray | None = None) -> dict:
    idx = np.array([METHOD_CLASSES.index(m) for m in y])
    p_true = np.clip(proba[np.arange(len(idx)), idx], EPS, 1)
    out = {
        "n": int(len(idx)),
        "log_loss": float(-np.mean(np.log(p_true))),
        "accuracy": float(np.mean(proba.argmax(axis=1) == idx)),
    }
    if p_winner is not None:
        # Joint six-outcome log loss: P(actual winner) * P(actual method | that winner).
        out["joint_log_loss"] = float(-np.mean(np.log(np.clip(p_winner * p_true, EPS, 1))))
    return out


@dataclass
class BacktestResult:
    years: list[int]
    per_year: dict[str, list[dict]] = field(default_factory=dict)
    pooled: dict[str, dict] = field(default_factory=dict)
    calibration: dict[str, list[dict]] = field(default_factory=dict)
    method: dict[str, dict] = field(default_factory=dict)


def fit_winner(kind: str, train: list[TrainingRow], calib: list[TrainingRow]):
    Xt, yt = winner_matrix(train)
    Xc, yc = winner_matrix(calib)
    model = WINNER_MODELS[kind]().fit(Xt, yt)
    model.calibrator.fit(model.raw(Xc), yc)
    return model


def backtest(
    rows: list[TrainingRow],
    test_years: list[int],
    winner_kinds: tuple[str, ...] = ("elo", "logistic", "catboost"),
    method_kinds: tuple[str, ...] = ("logistic", "catboost"),
) -> BacktestResult:
    """For each test year Y: fit on [2005, Y-1), calibrate on Y-1, evaluate on Y."""
    result = BacktestResult(years=test_years)
    preds: dict[str, list[np.ndarray]] = {k: [] for k in ("coin_flip", *winner_kinds)}
    ys: list[np.ndarray] = []
    method_preds: dict[str, list[np.ndarray]] = {k: [] for k in ("prior", *method_kinds)}
    method_ys: list[str] = []
    method_pw: dict[str, list[np.ndarray]] = {k: [] for k in winner_kinds}

    for year in test_years:
        train = [r for r in rows if TRAIN_START_YEAR <= r.bout.on.year < year - 1]
        calib = [r for r in rows if r.bout.on.year == year - 1]
        test = [r for r in rows if r.bout.on.year == year]
        if not (train and calib and test):
            continue
        Xs, ys_year = winner_matrix(test)
        ys.append(ys_year)
        preds["coin_flip"].append(np.full(len(ys_year), 0.5))
        _record(result, "coin_flip", year, preds["coin_flip"][-1], ys_year)
        fitted = {}
        for kind in winner_kinds:
            fitted[kind] = fit_winner(kind, train, calib)
            p = fitted[kind].predict(Xs)
            preds[kind].append(p)
            _record(result, kind, year, p, ys_year)

        # Method model, conditional on the actual winner.
        Xm_train, ym_train = method_matrix(train + calib)
        test_m = [r for r in test if r.method_y is not None]
        Xm_test, ym_test = method_matrix(test_m)
        method_ys.extend(ym_test)
        for kind in method_kinds:
            method_preds[kind].append(MethodModel(kind).fit(Xm_train, ym_train).predict(Xm_test))
        counts = np.bincount(
            [METHOD_CLASSES.index(m) for m in ym_train], minlength=len(METHOD_CLASSES)
        )
        method_preds["prior"].append(np.tile(counts / counts.sum(), (len(ym_test), 1)))
        Xw, _ = winner_matrix(test_m)
        for kind in winner_kinds:
            p1 = fitted[kind].predict(Xw)
            method_pw[kind].append(
                np.array([p if r.f1_won else 1 - p for p, r in zip(p1, test_m, strict=True)])
            )

    y_all = np.concatenate(ys)
    for kind, chunks in preds.items():
        p_all = np.concatenate(chunks)
        result.pooled[kind] = winner_metrics(p_all, y_all)
        result.calibration[kind] = calibration_table(p_all, y_all)
    best = min(winner_kinds, key=lambda k: result.pooled[k]["log_loss"])
    pw_best = np.concatenate(method_pw[best])
    for kind, chunks in method_preds.items():
        result.method[kind] = method_metrics(np.concatenate(chunks), method_ys, pw_best)
    return result


def _record(result: BacktestResult, kind: str, year: int, p: np.ndarray, y: np.ndarray) -> None:
    result.per_year.setdefault(kind, []).append({"year": year, **winner_metrics(p, y)})
