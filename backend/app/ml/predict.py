"""Inference: a model bundle + history replayed to the as-of date -> outcome distribution and
explanations grounded in the actual feature values."""

import math
from dataclasses import dataclass
from datetime import date

import numpy as np

from app.ml.artifacts import ModelBundle
from app.ml.data import BoutRow, FighterStatic
from app.ml.features import (
    METHOD_FEATURES,
    WINNER_FEATURES,
    Context,
    HistoryEngine,
    Snapshot,
    method_features,
    winner_features,
)
from app.ml.models import LogisticModel, outcome_distribution

REASON_MIN_LOGIT = 0.02  # contributions smaller than this aren't worth listing
MAX_REASONS = 5
MAX_UNKNOWNS = 3


@dataclass
class RawPrediction:
    p_a: float
    method_a: np.ndarray
    method_b: np.ndarray
    outcomes: dict[str, float]
    reasons_a: list[dict]
    reasons_b: list[dict]
    unknowns: list[str]
    confidence: tuple[str, list[str]]


def replay_engine(
    bouts: list[BoutRow], statics: dict[int, FighterStatic], elo_k: float, as_of: date
) -> HistoryEngine:
    engine = HistoryEngine(statics, elo_k)
    engine.replay(bouts, before=as_of)
    return engine


def predict_pair(
    bundle: ModelBundle,
    engine: HistoryEngine,
    a: int,
    b: int,
    as_of: date,
    ctx: Context,
    names: tuple[str, str],
) -> RawPrediction:
    sa, sb = engine.snapshot(a, as_of), engine.snapshot(b, as_of)
    feats = winner_features(sa, sb, engine.h2h_score(a, b, as_of), ctx)
    X = np.array([[feats[f] for f in WINNER_FEATURES]])
    p_a = float(bundle.winner.predict(X)[0])

    Xm = np.array(
        [
            [method_features(sa, sb, ctx)[f] for f in METHOD_FEATURES],
            [method_features(sb, sa, ctx)[f] for f in METHOD_FEATURES],
        ]
    )
    method = bundle.method.predict(Xm)
    outcomes = outcome_distribution(p_a, method[0], method[1])

    contrib = _contributions(bundle.winner, X, feats)
    reasons_a, reasons_b = _reasons(contrib, feats, sa, sb, engine, a, b, as_of, names)
    return RawPrediction(
        p_a=p_a,
        method_a=method[0],
        method_b=method[1],
        outcomes=outcomes,
        reasons_a=reasons_a,
        reasons_b=reasons_b,
        unknowns=_unknowns(sa, sb, names),
        confidence=_confidence(sa, sb),
    )


def _contributions(model, X: np.ndarray, feats: dict[str, float]) -> dict[str, float]:
    if hasattr(model, "contributions"):
        values = model.contributions(X)[0]
        if isinstance(model, LogisticModel):
            values = values * model.calibrator.slope
        return dict(zip(WINNER_FEATURES, map(float, values), strict=True))
    # Elo-only model: the rating gap is the whole story.
    return {f: 0.0 for f in WINNER_FEATURES} | {"elo_diff": feats["elo_diff"] / 400 * math.log(10)}


def _fmt_pct(x: float) -> str:
    return f"{x:.0%}"


def _last_results(engine: HistoryEngine, fid: int, n: int = 3) -> str:
    res = [x.result for x in engine.state[fid].bouts[-n:]]
    return "-".join(reversed(res)) if res else "no UFC bouts"


def _streak(s: Snapshot) -> str:
    return f"W{s.streak}" if s.streak > 0 else f"L{-s.streak}" if s.streak < 0 else "none"


# Correlated features are explained together: individually, collinear coefficients can point the
# "wrong" way (e.g. last-3 form vs. recency-weighted form) even though their sum is sensible.
REASON_GROUPS = {
    "rating": ["elo_diff", "elo_diff_x_5rd"],
    "form": [
        "win_rate_diff",
        "recent_win_rate_diff",
        "last3_diff",
        "streak_diff",
        "elo_trend_diff",
    ],
    "opposition": ["opp_elo_last5_diff"],
    "experience": ["experience_diff", "debut_diff"],
    "age": ["age_diff"],
    "reach": ["reach_diff"],
    "height": ["height_diff"],
    "finishing": ["ko_win_rate_diff", "sub_win_rate_diff"],
    "durability": ["ko_loss_rate_diff", "sub_loss_rate_diff"],
    "pace": ["decision_rate_diff", "decision_rate_diff_x_5rd"],
    "activity": ["log_layoff_diff"],
    "h2h": ["h2h_score"],
    "stance": ["southpaw_edge"],
}


def _reasons(contrib, feats, sa: Snapshot, sb: Snapshot, engine, a, b, as_of, names):
    na, nb = names

    def vs(x: str, y: str) -> str:
        return f"{na}: {x} · {nb}: {y}"

    def opt(v, fmt):
        return fmt(v) if v is not None else "unknown"

    def inches(v):
        return f'{v:g}"'

    def pct_pair(s: Snapshot, first: str, second: str) -> str:
        return f"{_fmt_pct(getattr(s, first))} / {_fmt_pct(getattr(s, second))}"

    meetings = engine.meetings.get(frozenset((a, b)), [])
    describe = {
        "rating": (
            "Strength rating (Elo, adjusts for opponent quality)",
            vs(f"{sa.elo:.0f}", f"{sb.elo:.0f}"),
        ),
        "form": (
            "Record and recent form",
            vs(
                f"{sa.wins}-{sa.losses}, last 3 {_last_results(engine, a)}, streak {_streak(sa)}",
                f"{sb.wins}-{sb.losses}, last 3 {_last_results(engine, b)}, streak {_streak(sb)}",
            ),
        ),
        "opposition": (
            "Average Elo of last five opponents",
            vs(f"{sa.opp_elo_last5:.0f}", f"{sb.opp_elo_last5:.0f}"),
        ),
        "experience": ("UFC experience", vs(f"{sa.n_bouts} bouts", f"{sb.n_bouts} bouts")),
        "age": (
            "Age at fight date",
            vs(opt(sa.age, lambda v: f"{v:.1f}"), opt(sb.age, lambda v: f"{v:.1f}")),
        ),
        "reach": ("Reach", vs(opt(sa.reach_in, inches), opt(sb.reach_in, inches))),
        "height": ("Height", vs(opt(sa.height_in, inches), opt(sb.height_in, inches))),
        "finishing": (
            "Finishing rate (KO / submission wins per bout, small-sample shrunk)",
            vs(
                pct_pair(sa, "ko_win_rate", "sub_win_rate"),
                pct_pair(sb, "ko_win_rate", "sub_win_rate"),
            ),
        ),
        "durability": (
            "Times finished (KO / submission losses per bout, shrunk)",
            vs(
                pct_pair(sa, "ko_loss_rate", "sub_loss_rate"),
                pct_pair(sb, "ko_loss_rate", "sub_loss_rate"),
            ),
        ),
        "pace": (
            "Share of bouts going to decision",
            vs(_fmt_pct(sa.decision_rate), _fmt_pct(sb.decision_rate)),
        ),
        "activity": (
            "Days since last UFC bout",
            vs(opt(sa.days_since_last, str), opt(sb.days_since_last, str)),
        ),
        "h2h": (
            "Previous meetings (older ones count much less)",
            "; ".join(
                f"{when:%b %Y}: {na if w == a else nb} won ({(as_of - when).days / 365.25:.1f}y ago)"
                for when, w in meetings
                if w is not None
            )
            or "none",
        ),
        "stance": ("Stance matchup", vs(sa.stance or "unknown", sb.stance or "unknown")),
    }
    totals = {
        group: sum(contrib[f] for f in members if not math.isnan(feats[f]))
        for group, members in REASON_GROUPS.items()
    }
    ranked = sorted(
        ((g, c) for g, c in totals.items() if abs(c) >= REASON_MIN_LOGIT),
        key=lambda t: abs(t[1]),
        reverse=True,
    )

    def build(sign: int) -> list[dict]:
        return [
            {
                "feature": g,
                "label": describe[g][0],
                "detail": describe[g][1],
                "contribution": abs(c),
            }
            for g, c in ranked
            if c * sign > 0
        ][:MAX_REASONS]

    return build(1), build(-1)


def _unknowns(sa: Snapshot, sb: Snapshot, names: tuple[str, str]) -> list[str]:
    items: list[tuple[int, str]] = []
    for s, name in ((sa, names[0]), (sb, names[1])):
        if s.n_bouts == 0:
            items.append(
                (
                    0,
                    f"{name} has no UFC bouts in the data; the estimate leans on population averages.",
                )
            )
        elif s.n_bouts < 3:
            items.append(
                (
                    1,
                    f"{name} has only {s.n_bouts} UFC bout(s); form and finish rates are mostly prior.",
                )
            )
        if s.days_since_last is not None and s.days_since_last > 365:
            items.append(
                (
                    2,
                    f"{name} hasn't fought in {s.days_since_last / 30.44:.0f} months; the effect of this layoff is uncertain.",
                )
            )
        if s.age is None:
            items.append((3, f"{name}'s date of birth is unavailable."))
        if s.reach_in is None:
            items.append((4, f"{name}'s reach is unavailable."))
    items.append((5, "No per-bout striking/grappling statistics or injury reports are included."))
    return [text for _, text in sorted(items)[:MAX_UNKNOWNS]]


def _confidence(sa: Snapshot, sb: Snapshot) -> tuple[str, list[str]]:
    reasons = []
    low_n = min(sa.n_bouts, sb.n_bouts)
    if low_n < 2:
        reasons.append("At least one fighter has fewer than two UFC bouts.")
    elif low_n < 5:
        reasons.append("At least one fighter has fewer than five UFC bouts.")
    if any(s.days_since_last is not None and s.days_since_last > 730 for s in (sa, sb)):
        reasons.append("At least one fighter has been out for over two years.")
    if any(s.age is None or s.reach_in is None for s in (sa, sb)):
        reasons.append("Some physical attributes are missing.")
    if low_n < 2:
        return "low", reasons
    return ("medium" if reasons else "high"), reasons or [
        "Both fighters have substantial, recent UFC histories."
    ]
