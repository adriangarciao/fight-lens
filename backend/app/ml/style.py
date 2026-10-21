"""Striking and grappling style from per-fight stats, time-correct and opponent-adjusted.

Rates are recency-weighted (2-year half-life) and shrunk toward the *league average as of the
same date*, accumulated from earlier bouts only, so small samples don't produce extreme
values and no future information enters through the prior.

Opponent adjustment: each past fight's output is compared with what that opponent typically
allowed *before* that fight. Landing 6 significant strikes per minute on someone who usually
absorbs 6 is average, not elite.
"""

from dataclasses import dataclass
from datetime import date

from app.ml.data import StatLine

HALF_LIFE_DAYS = 730
K_MINUTES = 15.0  # pseudo-minutes of league-average performance added to every rate
K_STRIKES = 40.0  # pseudo-attempts for striking accuracy/defense
K_TAKEDOWNS = 6.0  # pseudo-attempts for takedown accuracy/defense
K_LANDED = 30.0  # pseudo-strikes for position shares

# Used only until the league itself has history (the first few events of 1994).
FALLBACK = {
    "slpm": 3.5,
    "str_acc": 0.45,
    "td15": 1.2,
    "td_acc": 0.35,
    "kd15": 0.3,
    "sub15": 0.5,
    "ctrl_share": 0.15,
    "distance_share": 0.65,
    "ground_share": 0.15,
}


@dataclass(frozen=True)
class StyleEntry:
    on: date
    minutes: float
    mine: StatLine
    theirs: StatLine
    # The opponent's pre-fight rates, for opponent adjustment.
    opp_allowed_slpm: float
    opp_slpm: float
    opp_allowed_td15: float


@dataclass(frozen=True)
class Style:
    minutes: float  # unweighted UFC minutes with stats
    slpm: float  # significant strikes landed per minute
    sapm: float  # significant strikes absorbed per minute
    str_acc: float
    str_def: float
    td15: float
    td_allowed15: float
    td_acc: float
    td_def: float
    kd15: float
    kd_absorbed15: float
    sub15: float
    ctrl_share: float  # share of fight time spent controlling the opponent
    distance_share: float
    ground_share: float
    adj_str_off: float  # landed per minute above what opponents usually allow
    adj_str_def: float  # absorbed per minute below what opponents usually land
    adj_td_off: float  # takedowns per 15 above what opponents usually allow


class League:
    """Running league totals (one row per fighter-bout) from bouts already applied."""

    def __init__(self) -> None:
        self.minutes = 0.0
        self.sig_landed = self.sig_attempted = 0
        self.td_landed = self.td_attempted = 0
        self.kd = self.sub = 0
        self.ctrl_seconds = self.distance = self.ground = 0

    def add(self, minutes: float, s: StatLine) -> None:
        self.minutes += minutes
        self.sig_landed += s.sig_landed
        self.sig_attempted += s.sig_attempted
        self.td_landed += s.td_landed
        self.td_attempted += s.td_attempted
        self.kd += s.kd
        self.sub += s.sub_attempts
        self.ctrl_seconds += s.ctrl_seconds
        self.distance += s.distance_landed
        self.ground += s.ground_landed

    def priors(self) -> dict[str, float]:
        if self.minutes < 500:
            return dict(FALLBACK)
        m = self.minutes
        return {
            "slpm": self.sig_landed / m,
            "str_acc": self.sig_landed / max(self.sig_attempted, 1),
            "td15": self.td_landed / m * 15,
            "td_acc": self.td_landed / max(self.td_attempted, 1),
            "kd15": self.kd / m * 15,
            "sub15": self.sub / m * 15,
            "ctrl_share": self.ctrl_seconds / 60 / m,
            "distance_share": self.distance / max(self.sig_landed, 1),
            "ground_share": self.ground / max(self.sig_landed, 1),
        }


def compute_style(entries: list[StyleEntry], on: date, league: League) -> Style:
    p = league.priors()
    w = [0.5 ** ((on - e.on).days / HALF_LIFE_DAYS) for e in entries]
    wmin = sum(wi * e.minutes for wi, e in zip(w, entries, strict=True))

    def total(get) -> float:
        return sum(wi * get(e) for wi, e in zip(w, entries, strict=True))

    def per_min(get, prior: float) -> float:
        return (total(get) + prior * K_MINUTES) / (wmin + K_MINUTES)

    def ratio(num, den, prior: float, k: float) -> float:
        return (total(num) + prior * k) / (total(den) + k)

    def adjusted(get) -> float:
        # Minute-weighted residuals, shrunk toward 0 (no evidence of being above/below par).
        return total(lambda e: e.minutes * get(e)) / (wmin + K_MINUTES)

    def rate(count: int, minutes: float) -> float:
        return count / minutes if minutes > 0 else 0.0

    return Style(
        minutes=sum(e.minutes for e in entries),
        slpm=per_min(lambda e: e.mine.sig_landed, p["slpm"]),
        sapm=per_min(lambda e: e.theirs.sig_landed, p["slpm"]),
        str_acc=ratio(
            lambda e: e.mine.sig_landed, lambda e: e.mine.sig_attempted, p["str_acc"], K_STRIKES
        ),
        str_def=1
        - ratio(
            lambda e: e.theirs.sig_landed, lambda e: e.theirs.sig_attempted, p["str_acc"], K_STRIKES
        ),
        td15=per_min(lambda e: e.mine.td_landed, p["td15"] / 15) * 15,
        td_allowed15=per_min(lambda e: e.theirs.td_landed, p["td15"] / 15) * 15,
        td_acc=ratio(
            lambda e: e.mine.td_landed, lambda e: e.mine.td_attempted, p["td_acc"], K_TAKEDOWNS
        ),
        td_def=1
        - ratio(
            lambda e: e.theirs.td_landed, lambda e: e.theirs.td_attempted, p["td_acc"], K_TAKEDOWNS
        ),
        kd15=per_min(lambda e: e.mine.kd, p["kd15"] / 15) * 15,
        kd_absorbed15=per_min(lambda e: e.theirs.kd, p["kd15"] / 15) * 15,
        sub15=per_min(lambda e: e.mine.sub_attempts, p["sub15"] / 15) * 15,
        ctrl_share=per_min(lambda e: e.mine.ctrl_seconds / 60, p["ctrl_share"]),
        distance_share=ratio(
            lambda e: e.mine.distance_landed,
            lambda e: e.mine.sig_landed,
            p["distance_share"],
            K_LANDED,
        ),
        ground_share=ratio(
            lambda e: e.mine.ground_landed, lambda e: e.mine.sig_landed, p["ground_share"], K_LANDED
        ),
        adj_str_off=adjusted(lambda e: rate(e.mine.sig_landed, e.minutes) - e.opp_allowed_slpm),
        adj_str_def=adjusted(lambda e: e.opp_slpm - rate(e.theirs.sig_landed, e.minutes)),
        adj_td_off=adjusted(lambda e: rate(e.mine.td_landed, e.minutes) * 15 - e.opp_allowed_td15),
    )
