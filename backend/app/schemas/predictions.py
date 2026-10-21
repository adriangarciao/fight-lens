from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import FighterRef


class MatchupPredictionRequest(BaseModel):
    fighter_a: int = Field(alias="fighterA")
    fighter_b: int = Field(alias="fighterB")
    as_of: date | None = Field(default=None, alias="asOf")
    scheduled_rounds: Literal[3, 5] = Field(default=3, alias="scheduledRounds")
    title_bout: bool = Field(default=False, alias="titleBout")


class Outcome(BaseModel):
    fighter_id: int
    method: str
    # Unconditional probability of this exact outcome; the six outcomes sum to 1.
    probability: float


class Reason(BaseModel):
    feature: str
    label: str
    detail: str
    contribution: float  # logit units toward this fighter


class DataConfidence(BaseModel):
    level: Literal["high", "medium", "low"]
    reasons: list[str]


class PredictionOut(BaseModel):
    fighter_a: FighterRef
    fighter_b: FighterRef
    as_of: date
    scheduled_rounds: int | None
    scheduled_rounds_source: str | None
    model_version: str
    feature_set_version: str
    generated_at: datetime
    stored: bool
    # True when the model's training data already included bouts on/after this date, i.e. a
    # hindsight estimate rather than a genuine pre-fight one.
    in_sample: bool
    win_probability: dict[str, float]  # {"a": .., "b": ..}
    method_given_win: dict[str, dict[str, float]]
    outcomes: list[Outcome]
    reasons: dict[str, list[Reason]]
    unknowns: list[str]
    data_confidence: DataConfidence
    disclaimer: str = (
        "Model estimate from historical UFC data. Not a guaranteed result and not sportsbook odds."
    )


class CardPrediction(BaseModel):
    p_1: float
    p_2: float
    likely_outcome: str
    likely_outcome_probability: float
    model_version: str
    generated_at: datetime
