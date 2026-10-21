from datetime import date

from pydantic import BaseModel

from app.schemas.common import FighterRef


class Metrics(BaseModel):
    n: int
    accuracy: float | None
    log_loss: float | None
    brier: float | None
    coin_flip_log_loss: float = 0.6931471805599453
    # Mean probability given to the exact winner+method, over bouts with a modeled method.
    mean_p_actual_outcome: float | None
    n_outcome: int


class CalibrationRow(BaseModel):
    bucket: str
    n: int
    mean_predicted: float
    observed: float


class ScoredPick(BaseModel):
    bout_id: int
    event_name: str
    event_date: date
    fighter_a: FighterRef
    fighter_b: FighterRef
    p_a: float
    winner: FighterRef | None
    actual_outcome: str
    actual_method: str | None
    p_actual_winner: float | None
    favourite_correct: bool | None
    model_version: str
    status: str


class ModelVersionRecord(BaseModel):
    model_version: str
    metrics: Metrics


class TrackRecord(BaseModel):
    """Genuine pre-fight forecasts only: one per bout (the latest stored before fight day)."""

    headline: Metrics
    calibration: list[CalibrationRow]
    voided: int
    pending: int
    excluded_not_pre_fight: int
    by_model_version: list[ModelVersionRecord]
    recent: list[ScoredPick]
    next_event: str | None
    next_event_date: date | None
