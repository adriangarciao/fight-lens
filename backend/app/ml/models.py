"""Winner and method models.

Every winner model exposes `predict(X) -> P(row's fighter A wins)` and is symmetric by
construction: predict(-X) == 1 - predict(X). Calibration is a slope-only Platt fit on the logit,
which preserves that symmetry.
"""

import math

import numpy as np
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.ml.features import METHOD_CLASSES, METHOD_FEATURES, WINNER_FEATURES

EPS = 1e-6


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-z))


def symmetrize(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each bout in both orientations, so no model can learn from source order."""
    return np.vstack([X, -X]), np.concatenate([y, 1 - y])


class SlopeCalibrator:
    """p' = sigmoid(a * logit(p)). One parameter, no intercept: keeps P(A)+P(B)=1."""

    def __init__(self, slope: float = 1.0):
        self.slope = slope

    def fit(self, p: np.ndarray, y: np.ndarray) -> "SlopeCalibrator":
        z = logit(np.concatenate([p, 1 - p])).reshape(-1, 1)
        t = np.concatenate([y, 1 - y])
        lr = LogisticRegression(fit_intercept=False, C=1e6).fit(z, t)
        self.slope = float(lr.coef_[0, 0])
        return self

    def __call__(self, p: np.ndarray) -> np.ndarray:
        return sigmoid(self.slope * logit(p))


class EloModel:
    name = "elo"

    def __init__(self) -> None:
        self.calibrator = SlopeCalibrator()
        self._idx = WINNER_FEATURES.index("elo_diff")

    def fit(self, X: np.ndarray, y: np.ndarray) -> "EloModel":
        return self

    def raw(self, X: np.ndarray) -> np.ndarray:
        return 1 / (1 + 10 ** (-X[:, self._idx] / 400))

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.calibrator(self.raw(X))


class LogisticModel:
    """No intercept, scaling without centering, missing diffs imputed as 0 (no difference)."""

    name = "logistic"

    def __init__(self, C: float = 0.5):
        self.scaler = StandardScaler(with_mean=False)
        self.lr = LogisticRegression(fit_intercept=False, C=C, max_iter=2000)
        self.calibrator = SlopeCalibrator()

    @staticmethod
    def _prep(X: np.ndarray) -> np.ndarray:
        return np.nan_to_num(X, nan=0.0)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticModel":
        Xs, ys = symmetrize(self._prep(X), y)
        self.lr.fit(self.scaler.fit_transform(Xs), ys)
        return self

    def raw(self, X: np.ndarray) -> np.ndarray:
        return self.lr.predict_proba(self.scaler.transform(self._prep(X)))[:, 1]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.calibrator(self.raw(X))

    def contributions(self, X: np.ndarray) -> np.ndarray:
        """Per-feature logit contributions (exact for a linear model)."""
        return self.scaler.transform(self._prep(X)) * self.lr.coef_[0]


class CatBoostModel:
    """Trained on both orientations; predictions averaged over both to be exactly symmetric."""

    name = "catboost"

    def __init__(
        self, iterations: int = 600, depth: int = 4, learning_rate: float = 0.03, seed: int = 7
    ):
        self.clf = CatBoostClassifier(
            iterations=iterations,
            depth=depth,
            learning_rate=learning_rate,
            l2_leaf_reg=5,
            loss_function="Logloss",
            random_seed=seed,
            verbose=False,
            allow_writing_files=False,
            thread_count=-1,
        )
        self.calibrator = SlopeCalibrator()

    def fit(self, X: np.ndarray, y: np.ndarray) -> "CatBoostModel":
        Xs, ys = symmetrize(X, y)
        self.clf.fit(Xs, ys)
        return self

    def raw(self, X: np.ndarray) -> np.ndarray:
        return (self.clf.predict_proba(X)[:, 1] + 1 - self.clf.predict_proba(-X)[:, 1]) / 2

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.calibrator(self.raw(X))

    def contributions(self, X: np.ndarray) -> np.ndarray:
        """Symmetrized SHAP values in logit space."""
        shap_pos = self.clf.get_feature_importance(data=_pool(X), type="ShapValues")[:, :-1]
        shap_neg = self.clf.get_feature_importance(data=_pool(-X), type="ShapValues")[:, :-1]
        return (shap_pos - shap_neg) / 2 * self.calibrator.slope


def _pool(X: np.ndarray):
    from catboost import Pool

    return Pool(X, feature_names=WINNER_FEATURES)


WINNER_MODELS = {"elo": EloModel, "logistic": LogisticModel, "catboost": CatBoostModel}


class MethodModel:
    """P(KO/TKO, SUB, DEC | fighter wins). Multinomial logistic or CatBoost multiclass."""

    def __init__(self, kind: str = "logistic"):
        self.kind = kind
        self.priors = np.full(len(METHOD_CLASSES), 1 / len(METHOD_CLASSES))
        self.medians = np.zeros(len(METHOD_FEATURES))
        if kind == "logistic":
            self.scaler = StandardScaler()
            self.clf = LogisticRegression(C=0.5, max_iter=2000)
        else:
            self.clf = CatBoostClassifier(
                iterations=500,
                depth=4,
                learning_rate=0.03,
                loss_function="MultiClass",
                random_seed=7,
                verbose=False,
                allow_writing_files=False,
            )

    def fit(self, X: np.ndarray, y: list[str]) -> "MethodModel":
        labels = np.array([METHOD_CLASSES.index(m) for m in y])
        self.priors = np.bincount(labels, minlength=len(METHOD_CLASSES)) / len(labels)
        if self.kind == "logistic":
            self.medians = np.nanmedian(X, axis=0)
            self.clf.fit(self.scaler.fit_transform(self._impute(X)), labels)
        else:
            self.clf.fit(X, labels)
        return self

    def _impute(self, X: np.ndarray) -> np.ndarray:
        return np.where(np.isnan(X), self.medians, X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Rows sum to 1, columns ordered as METHOD_CLASSES."""
        if self.kind == "logistic":
            proba = self.clf.predict_proba(self.scaler.transform(self._impute(X)))
        else:
            proba = self.clf.predict_proba(X)
        out = np.zeros((len(X), len(METHOD_CLASSES)))
        out[:, self.clf.classes_.astype(int)] = proba
        return out / out.sum(axis=1, keepdims=True)


def outcome_distribution(
    p_a: float, method_a: np.ndarray, method_b: np.ndarray
) -> dict[str, float]:
    """Six joint outcomes. Sums to exactly 1 in the win-only model."""
    if not (
        math.isclose(method_a.sum(), 1, abs_tol=1e-9)
        and math.isclose(method_b.sum(), 1, abs_tol=1e-9)
    ):
        raise ValueError("method distributions must each sum to 1")
    out = {}
    for side, p, dist in (("a", p_a, method_a), ("b", 1 - p_a, method_b)):
        for cls, q in zip(METHOD_CLASSES, dist, strict=True):
            out[f"{side}:{cls}"] = float(p * q)
    return out
