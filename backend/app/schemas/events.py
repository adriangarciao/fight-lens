from datetime import date

from pydantic import BaseModel

from app.schemas.common import FighterRef, Record
from app.schemas.predictions import CardPrediction


class CardBout(BaseModel):
    bout_id: int
    fighter_1: FighterRef
    fighter_2: FighterRef
    record_1: Record
    record_2: Record
    division: str | None
    weight_class_raw: str | None
    scheduled_rounds: int | None
    is_title_bout: bool
    status: str
    winner_id: int | None
    outcome: str | None
    method: str | None
    end_round: int | None
    end_time_seconds: int | None
    scheduled_rounds_source: str | None = None
    # Stored batch prediction from the active model; None until `fightlens predict` has run.
    prediction: CardPrediction | None = None


class EventSummary(BaseModel):
    id: int
    name: str
    date: date
    location: str | None
    bout_count: int
    status: str


class EventDetail(EventSummary):
    bouts: list[CardBout]
