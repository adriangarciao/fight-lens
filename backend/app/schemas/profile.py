from datetime import date

from pydantic import BaseModel

from app.schemas.common import FighterRef, Result


class RatingPoint(BaseModel):
    date: date
    elo: float  # rating after this bout
    elo_before: float
    opponent: FighterRef
    result: Result
    method: str | None


class LeagueAverages(BaseModel):
    """League-wide per-fight stat averages from bouts before the as-of date."""

    slpm: float
    str_acc: float
    str_def: float
    td15: float
    td_acc: float
    td_def: float
    kd15: float
    sub15: float
    ctrl_share: float


class MatchupProfile(BaseModel):
    as_of: date
    model_version: str | None
    elo_k: float
    ratings: dict[str, list[RatingPoint]]  # {"a": [...], "b": [...]}
    league: LeagueAverages
