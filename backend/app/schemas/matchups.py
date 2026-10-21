from datetime import date

from pydantic import BaseModel

from app.schemas.common import EventRef, FighterRef
from app.schemas.fighters import FighterSummary, FightRecord


class Meeting(BaseModel):
    bout_id: int
    event: EventRef
    winner: FighterRef | None
    outcome: str
    method: str | None
    method_detail: str | None
    end_round: int | None
    end_time_seconds: int | None
    division: str | None
    days_before_as_of: int
    # Divisions each fighter has competed in since this meeting, when different from it.
    division_changes: dict[int, list[str]]
    fights_since: dict[int, int]


class CommonOpponentSide(BaseModel):
    fights: list[FightRecord]


class CommonOpponent(BaseModel):
    opponent: FighterRef
    fighter_a: CommonOpponentSide
    fighter_b: CommonOpponentSide
    gap_days: int
    limited_comparison: list[str]


class MatchupComparison(BaseModel):
    as_of: date
    fighter_a: FighterSummary
    fighter_b: FighterSummary
    head_to_head: list[Meeting]
    common_opponents: list[CommonOpponent]
    notes: list[str]


class H2HResponse(BaseModel):
    as_of: date
    meetings: list[Meeting]
