"""Time-correct pre-fight features, shared by training and inference.

`HistoryEngine` replays completed bouts in date order. Features for a bout are always computed
from the engine state *before* any bout on that date is applied, so a training row only sees
what was knowable immediately before the fight, the same view inference gets for a future bout.

Winner features are antisymmetric: features(B, A) == -features(A, B). Combined with models that
respect that (no intercept, or averaged over both orders), listing order cannot leak into a
prediction and P(A wins) + P(B wins) == 1.
"""

import hashlib
import math
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date

from app.ingestion.normalize import DIVISION_LIMITS
from app.ml.data import BoutRow, FighterStatic
from app.ml.style import League, Style, StyleEntry, compute_style

FEATURE_SET_VERSION = "fs-2"

ELO_START = 1500.0
DEFAULT_ELO_K = 32.0
RECENCY_HALF_LIFE_DAYS = 730
H2H_DECAY_DAYS = 730  # a six-year-old meeting keeps ~5% of a fresh one's weight

# fs-1: results-only features. Kept as a named subset for the with/without-stats ablation.
FS1_WINNER_FEATURES = [
    "elo_diff",
    "experience_diff",
    "age_diff",
    "height_diff",
    "reach_diff",
    "win_rate_diff",
    "recent_win_rate_diff",
    "last3_diff",
    "ko_win_rate_diff",
    "sub_win_rate_diff",
    "ko_loss_rate_diff",
    "sub_loss_rate_diff",
    "decision_rate_diff",
    "opp_elo_last5_diff",
    "elo_trend_diff",
    "log_layoff_diff",
    "debut_diff",
    "streak_diff",
    "h2h_score",
    "southpaw_edge",
    "elo_diff_x_5rd",
    "decision_rate_diff_x_5rd",
]

# fs-2 adds per-fight striking and grappling style (see app/ml/style.py).
STYLE_WINNER_FEATURES = [
    "slpm_diff",
    "sapm_diff",
    "str_acc_diff",
    "str_def_diff",
    "td15_diff",
    "td_acc_diff",
    "td_def_diff",
    "kd15_diff",
    "kd_absorbed15_diff",
    "sub15_diff",
    "ctrl_share_diff",
    "adj_str_off_diff",
    "adj_str_def_diff",
    "adj_td_off_diff",
    "striking_matchup",
    "wrestling_matchup",
    "stats_minutes_diff",
]
WINNER_FEATURES = FS1_WINNER_FEATURES + STYLE_WINNER_FEATURES

METHOD_CLASSES = ["KO/TKO", "SUB", "DEC"]
METHOD_FEATURES = [
    "elo_diff",
    "w_ko_win_rate",
    "w_sub_win_rate",
    "w_decision_rate",
    "l_ko_loss_rate",
    "l_sub_loss_rate",
    "l_decision_rate",
    "w_age",
    "l_age",
    "division_lbs",
    "is_womens",
    "five_rounds",
    "w_kd15",
    "w_sub15",
    "w_td15",
    "w_ctrl_share",
    "w_slpm",
    "l_kd_absorbed15",
    "l_sapm",
    "l_td_def",
    "l_str_def",
]


def schema_hash() -> str:
    payload = "|".join(
        [FEATURE_SET_VERSION, *WINNER_FEATURES, "#", *METHOD_FEATURES, "#", *METHOD_CLASSES]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class PastBout:
    on: date
    opponent: int
    opponent_elo_before: float
    result: str  # W / L / D / NC
    method: str | None


@dataclass
class FighterState:
    elo: float = ELO_START
    bouts: list[PastBout] = field(default_factory=list)
    elo_history: list[float] = field(default_factory=list)  # Elo before each bout
    style: list[StyleEntry] = field(default_factory=list)


@dataclass(frozen=True)
class Snapshot:
    """One fighter's pre-fight view. None means unknown, never assumed."""

    elo: float
    n_bouts: int
    wins: int
    losses: int
    recent_win_rate: float
    last3: float
    ko_win_rate: float
    sub_win_rate: float
    decision_rate: float
    ko_loss_rate: float
    sub_loss_rate: float
    opp_elo_last5: float
    elo_trend: float
    days_since_last: int | None
    streak: int  # +n win streak, -n losing streak
    age: float | None
    height_in: float | None
    reach_in: float | None
    stance: str | None
    style: Style


@dataclass(frozen=True)
class Context:
    scheduled_rounds: int | None
    is_title: bool
    division: str | None


class HistoryEngine:
    def __init__(self, statics: dict[int, FighterStatic], elo_k: float = DEFAULT_ELO_K):
        self.statics = statics
        self.elo_k = elo_k
        self.state: dict[int, FighterState] = defaultdict(FighterState)
        self.meetings: dict[frozenset, list[tuple[date, int | None]]] = defaultdict(list)
        self.league = League()
        self.last_date: date | None = None

    # -- replay ---------------------------------------------------------------------------
    def replay(self, bouts: Iterable[BoutRow], before: date | None = None) -> None:
        for _, group in self.iter_dates(bouts, before):
            self.apply_all(group)

    def iter_dates(
        self, bouts: Iterable[BoutRow], before: date | None = None
    ) -> Iterator[tuple[date, list[BoutRow]]]:
        """Yields (date, bouts) groups so callers can featurize a date before applying it."""
        group: list[BoutRow] = []
        for b in bouts:
            if b.outcome is None or (before is not None and b.on >= before):
                continue
            if group and b.on != group[0].on:
                yield group[0].on, group
                group = []
            group.append(b)
        if group:
            yield group[0].on, group

    def apply_all(self, group: list[BoutRow]) -> None:
        # Featurize-then-apply happens per date, so Elo updates within a date use pre-date
        # ratings for every bout (handles one-night tournaments without ordering effects).
        pre = {fid: self.state[fid].elo for b in group for fid in (b.f1, b.f2)}
        on = group[0].on
        with_stats = [b for b in group if b.stats is not None and b.seconds]
        pre_style = {
            fid: compute_style(self.state[fid].style, on, self.league)
            for b in with_stats
            for fid in (b.f1, b.f2)
        }
        for b in group:
            self._apply(b, pre)
        for b in with_stats:
            minutes = b.seconds / 60
            for fid, opp, mine, theirs in (
                (b.f1, b.f2, *b.stats),
                (b.f2, b.f1, *reversed(b.stats)),
            ):
                o = pre_style[opp]
                self.state[fid].style.append(
                    StyleEntry(on, minutes, mine, theirs, o.sapm, o.slpm, o.td_allowed15)
                )
        for b in with_stats:  # league priors only ever include already-applied bouts
            for line in b.stats:
                self.league.add(b.seconds / 60, line)
        self.last_date = on

    def _apply(self, b: BoutRow, pre: dict[int, float]) -> None:
        if b.outcome == "no_contest":
            results = {b.f1: "NC", b.f2: "NC"}
        elif b.outcome == "draw":
            results = {b.f1: "D", b.f2: "D"}
        else:
            loser = b.f2 if b.winner == b.f1 else b.f1
            results = {b.winner: "W", loser: "L"}
        for fid, opp in ((b.f1, b.f2), (b.f2, b.f1)):
            st = self.state[fid]
            st.elo_history.append(st.elo)
            st.bouts.append(PastBout(b.on, opp, pre[opp], results[fid], b.method))
            if results[fid] != "NC":
                score = {"W": 1.0, "L": 0.0, "D": 0.5}[results[fid]]
                expected = elo_expected(pre[fid], pre[opp])
                st.elo += self.elo_k * (score - expected)
        if b.outcome != "no_contest":
            self.meetings[frozenset((b.f1, b.f2))].append((b.on, b.winner))

    # -- snapshots and features -----------------------------------------------------------
    def snapshot(self, fid: int, on: date) -> Snapshot:
        st = self.state[fid]
        static = self.statics.get(fid) or FighterStatic(None, None, None, None)
        decisive = [x for x in st.bouts if x.result in ("W", "L")]
        counted = [x for x in st.bouts if x.result != "NC"]
        n = len(counted)
        wins = sum(x.result == "W" for x in decisive)

        weights = [0.5 ** ((on - x.on).days / RECENCY_HALF_LIFE_DAYS) for x in decisive]
        recent = (
            sum(w for w, x in zip(weights, decisive, strict=True) if x.result == "W") + 0.5
        ) / (sum(weights) + 1.0)
        last3_scores = [{"W": 1.0, "L": 0.0, "D": 0.5}[x.result] for x in counted[-3:]]
        last3 = (sum(last3_scores) + 0.5 * (3 - len(last3_scores))) / 3

        streak = 0
        for x in reversed(st.bouts):
            if x.result == "NC":
                continue
            if (
                x.result == "D"
                or (streak > 0 and x.result == "L")
                or (streak < 0 and x.result == "W")
            ):
                break
            streak += 1 if x.result == "W" else -1

        last5 = counted[-5:]
        return Snapshot(
            elo=st.elo,
            n_bouts=n,
            wins=wins,
            losses=len(decisive) - wins,
            recent_win_rate=recent,
            last3=last3,
            ko_win_rate=_rate(counted, lambda x: x.result == "W" and x.method == "KO/TKO", 0.15),
            sub_win_rate=_rate(counted, lambda x: x.result == "W" and x.method == "SUB", 0.08),
            decision_rate=_rate(counted, lambda x: x.method == "DEC", 0.45),
            ko_loss_rate=_rate(counted, lambda x: x.result == "L" and x.method == "KO/TKO", 0.15),
            sub_loss_rate=_rate(counted, lambda x: x.result == "L" and x.method == "SUB", 0.08),
            opp_elo_last5=(
                sum(x.opponent_elo_before for x in last5) / len(last5) if last5 else ELO_START
            ),
            elo_trend=st.elo - st.elo_history[-3] if len(st.elo_history) >= 3 else 0.0,
            days_since_last=(on - st.bouts[-1].on).days if st.bouts else None,
            streak=streak,
            age=(on - static.dob).days / 365.25 if static.dob else None,
            height_in=static.height_in,
            reach_in=static.reach_in,
            stance=static.stance,
            style=compute_style(st.style, on, self.league),
        )

    def h2h_score(self, a: int, b: int, on: date) -> float:
        """Time-decayed head-to-head balance from A's side: +1 for a fresh A win."""
        score = 0.0
        for when, winner in self.meetings.get(frozenset((a, b)), []):
            if winner is None:
                continue
            score += (1 if winner == a else -1) * math.exp(-(on - when).days / H2H_DECAY_DAYS)
        return score

    def winner_features(self, a: int, b: int, on: date, ctx: Context) -> dict[str, float]:
        return winner_features(
            self.snapshot(a, on), self.snapshot(b, on), self.h2h_score(a, b, on), ctx
        )


def elo_expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def _rate(bouts: list[PastBout], pred, prior: float, strength: float = 3.0) -> float:
    """Share of bouts matching `pred`, shrunk toward a population prior for small samples."""
    return (sum(1 for x in bouts if pred(x)) + prior * strength) / (len(bouts) + strength)


def _diff(x: float | None, y: float | None) -> float:
    return x - y if x is not None and y is not None else float("nan")


def _southpaw(stance: str | None) -> bool:
    return stance in ("Southpaw", "Switch")


def winner_features(sa: Snapshot, sb: Snapshot, h2h: float, ctx: Context) -> dict[str, float]:
    five = 1.0 if ctx.scheduled_rounds == 5 else 0.0
    log_layoff = lambda s: math.log1p(s.days_since_last) if s.days_since_last is not None else 0.0  # noqa: E731
    edge = 0.0
    if sa.stance and sb.stance:
        edge = float(_southpaw(sa.stance) and not _southpaw(sb.stance)) - float(
            _southpaw(sb.stance) and not _southpaw(sa.stance)
        )
    elo_diff = sa.elo - sb.elo
    dec_diff = sa.decision_rate - sb.decision_rate
    ya, yb = sa.style, sb.style
    return {
        "elo_diff": elo_diff,
        "experience_diff": math.log1p(sa.n_bouts) - math.log1p(sb.n_bouts),
        "age_diff": _diff(sa.age, sb.age),
        "height_diff": _diff(sa.height_in, sb.height_in),
        "reach_diff": _diff(sa.reach_in, sb.reach_in),
        "win_rate_diff": (sa.wins + 2) / (sa.wins + sa.losses + 4)
        - (sb.wins + 2) / (sb.wins + sb.losses + 4),
        "recent_win_rate_diff": sa.recent_win_rate - sb.recent_win_rate,
        "last3_diff": sa.last3 - sb.last3,
        "ko_win_rate_diff": sa.ko_win_rate - sb.ko_win_rate,
        "sub_win_rate_diff": sa.sub_win_rate - sb.sub_win_rate,
        "ko_loss_rate_diff": sa.ko_loss_rate - sb.ko_loss_rate,
        "sub_loss_rate_diff": sa.sub_loss_rate - sb.sub_loss_rate,
        "decision_rate_diff": dec_diff,
        "opp_elo_last5_diff": sa.opp_elo_last5 - sb.opp_elo_last5,
        "elo_trend_diff": sa.elo_trend - sb.elo_trend,
        "log_layoff_diff": log_layoff(sa) - log_layoff(sb),
        "debut_diff": float(sa.n_bouts == 0) - float(sb.n_bouts == 0),
        "streak_diff": float(sa.streak - sb.streak),
        "h2h_score": h2h,
        "southpaw_edge": edge,
        "elo_diff_x_5rd": elo_diff * five,
        "decision_rate_diff_x_5rd": dec_diff * five,
        "slpm_diff": ya.slpm - yb.slpm,
        "sapm_diff": ya.sapm - yb.sapm,
        "str_acc_diff": ya.str_acc - yb.str_acc,
        "str_def_diff": ya.str_def - yb.str_def,
        "td15_diff": ya.td15 - yb.td15,
        "td_acc_diff": ya.td_acc - yb.td_acc,
        "td_def_diff": ya.td_def - yb.td_def,
        "kd15_diff": ya.kd15 - yb.kd15,
        "kd_absorbed15_diff": ya.kd_absorbed15 - yb.kd_absorbed15,
        "sub15_diff": ya.sub15 - yb.sub15,
        "ctrl_share_diff": ya.ctrl_share - yb.ctrl_share,
        "adj_str_off_diff": ya.adj_str_off - yb.adj_str_off,
        "adj_str_def_diff": ya.adj_str_def - yb.adj_str_def,
        "adj_td_off_diff": ya.adj_td_off - yb.adj_td_off,
        # Expected strikes landed per minute for each side given both styles, A minus B.
        "striking_matchup": (ya.slpm + yb.sapm) / 2 - (yb.slpm + ya.sapm) / 2,
        "wrestling_matchup": ya.td15 * (1 - yb.td_def) - yb.td15 * (1 - ya.td_def),
        "stats_minutes_diff": math.log1p(ya.minutes) - math.log1p(yb.minutes),
    }


def method_features(sw: Snapshot, sl: Snapshot, ctx: Context) -> dict[str, float]:
    """Features for P(method | this fighter wins), from the winner's perspective."""
    division = ctx.division or ""
    return {
        "elo_diff": sw.elo - sl.elo,
        "w_ko_win_rate": sw.ko_win_rate,
        "w_sub_win_rate": sw.sub_win_rate,
        "w_decision_rate": sw.decision_rate,
        "l_ko_loss_rate": sl.ko_loss_rate,
        "l_sub_loss_rate": sl.sub_loss_rate,
        "l_decision_rate": sl.decision_rate,
        "w_age": sw.age if sw.age is not None else float("nan"),
        "l_age": sl.age if sl.age is not None else float("nan"),
        "division_lbs": float(DIVISION_LIMITS.get(division, float("nan"))),
        "is_womens": float(division.startswith("Women's")),
        "five_rounds": 1.0 if ctx.scheduled_rounds == 5 else 0.0,
        "w_kd15": sw.style.kd15,
        "w_sub15": sw.style.sub15,
        "w_td15": sw.style.td15,
        "w_ctrl_share": sw.style.ctrl_share,
        "w_slpm": sw.style.slpm,
        "l_kd_absorbed15": sl.style.kd_absorbed15,
        "l_sapm": sl.style.sapm,
        "l_td_def": sl.style.td_def,
        "l_str_def": sl.style.str_def,
    }


@dataclass
class TrainingRow:
    bout: BoutRow
    winner_x: dict[str, float]  # oriented f1 vs f2
    f1_won: bool
    method_x_f1: dict[str, float]  # P(method | fighter 1 wins) features
    method_x_f2: dict[str, float]  # P(method | fighter 2 wins) features
    method_y: str | None

    @property
    def method_x(self) -> dict[str, float]:
        """Features from the actual winner's perspective (the training target's)."""
        return self.method_x_f1 if self.f1_won else self.method_x_f2


def build_training_rows(
    bouts: list[BoutRow], statics: dict[int, FighterStatic], elo_k: float = DEFAULT_ELO_K
) -> list[TrainingRow]:
    """One row per decisive completed bout, each built from pre-fight state only."""
    engine = HistoryEngine(statics, elo_k)
    rows: list[TrainingRow] = []
    for on, group in engine.iter_dates(bouts):
        for b in group:
            if b.outcome != "win":
                continue
            ctx = Context(b.scheduled_rounds, b.is_title, b.division)
            s1, s2 = engine.snapshot(b.f1, on), engine.snapshot(b.f2, on)
            rows.append(
                TrainingRow(
                    bout=b,
                    winner_x=winner_features(s1, s2, engine.h2h_score(b.f1, b.f2, on), ctx),
                    f1_won=b.winner == b.f1,
                    method_x_f1=method_features(s1, s2, ctx),
                    method_x_f2=method_features(s2, s1, ctx),
                    method_y=b.method if b.method in METHOD_CLASSES else None,
                )
            )
        engine.apply_all(group)
    return rows
