from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import EventRef, FighterRef, Record, Result


class FighterSearchResult(BaseModel):
    id: int
    name: str
    latest_division: str | None
    last_fight_date: date | None
    record: Record


class FightRecord(BaseModel):
    """One completed bout from a fighter's perspective."""

    bout_id: int
    event: EventRef
    opponent: FighterRef
    # Opponent's UFC record strictly before this bout: a time-correct (if crude) quality signal.
    opponent_record_before: Record
    result: Result
    method: str | None
    method_detail: str | None
    finish_details: str | None
    end_round: int | None
    end_time_seconds: int | None
    scheduled_rounds: int | None
    division: str | None
    is_title_bout: bool
    days_before_as_of: int


class Streak(BaseModel):
    kind: Literal["W", "L", "D", "none"]
    count: int


class Activity(BaseModel):
    days_since_last_fight: int | None
    fights_last_12_months: int
    fights_last_24_months: int
    layoff_flag: Literal["debut", "long_layoff", "short_turnaround", "normal"]


class Physical(BaseModel):
    age_years: float | None
    height_in: float | None
    reach_in: float | None
    stance: str | None


class StyleStats(BaseModel):
    """Raw per-fight stat rates over a set of UFC bouts (as UFCStats reports them)."""

    fights: int
    minutes: float
    slpm: float  # significant strikes landed per minute
    sapm: float  # significant strikes absorbed per minute
    str_acc: float | None
    str_def: float | None
    td15: float
    td_acc: float | None
    td_def: float | None
    kd15: float
    sub15: float
    ctrl_share: float  # share of fight time in control


class StyleSummary(BaseModel):
    career: StyleStats | None
    last5: StyleStats | None


class FighterSummary(BaseModel):
    fighter: FighterRef
    as_of: date
    physical: Physical
    record: Record
    last5_record: Record
    coming_off: Result | None
    streak: Streak
    activity: Activity
    ufc_debut: date | None
    years_in_ufc: float | None
    latest_division: str | None
    recent_fights: list[FightRecord]
    style: StyleSummary
    limited_data: list[str]


class FighterDetail(FighterSummary):
    all_fights: list[FightRecord]
