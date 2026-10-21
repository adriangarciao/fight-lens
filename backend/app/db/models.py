"""ORM models.

Bouts store fighters in source listing order (`fighter1`, `fighter2`). That order is NOT a
corner assignment and is correlated with the result (UFCStats lists winners first), so nothing
downstream may treat it as a signal. See docs/data-audit.md.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

BOUT_STATUSES = ("scheduled", "completed")
BOUT_OUTCOMES = ("win", "draw", "no_contest")
METHODS = ("KO/TKO", "SUB", "DEC", "DQ", "OVERTURNED", "CNC", "OTHER")


class Base(DeclarativeBase):
    pass


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_path: Mapped[str] = mapped_column(String(500))
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    report: Mapped[dict] = mapped_column(JSON, default=dict)


class Fighter(Base):
    __tablename__ = "fighters"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(200), index=True)
    # Static physical attributes only. Career aggregates from roster files are as-of-scrape and
    # would leak future information into historical examples, so they are not stored here.
    dob: Mapped[date | None] = mapped_column(Date)
    height_in: Mapped[float | None] = mapped_column(Float)
    reach_in: Mapped[float | None] = mapped_column(Float)
    stance: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    external_ids: Mapped[list["FighterExternalId"]] = relationship(back_populates="fighter")


class FighterExternalId(Base):
    __tablename__ = "fighter_external_ids"
    __table_args__ = (UniqueConstraint("source_id", "external_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fighter_id: Mapped[int] = mapped_column(ForeignKey("fighters.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    external_key: Mapped[str] = mapped_column(String(300))

    fighter: Mapped[Fighter] = relationship(back_populates="external_ids")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source_id", "external_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    external_key: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(300))
    event_date: Mapped[date] = mapped_column(Date, index=True)
    location: Mapped[str | None] = mapped_column(String(300))

    bouts: Mapped[list["Bout"]] = relationship(back_populates="event")


class Bout(Base):
    __tablename__ = "bouts"
    __table_args__ = (
        UniqueConstraint("source_id", "external_key"),
        CheckConstraint(f"status IN {BOUT_STATUSES}", name="ck_bout_status"),
        CheckConstraint(f"outcome IS NULL OR outcome IN {BOUT_OUTCOMES}", name="ck_bout_outcome"),
        CheckConstraint("fighter1_id <> fighter2_id", name="ck_bout_distinct_fighters"),
        CheckConstraint(
            "(outcome = 'win') = (winner_id IS NOT NULL)", name="ck_bout_winner_iff_win"
        ),
        Index("ix_bouts_fighter1_event", "fighter1_id", "event_id"),
        Index("ix_bouts_fighter2_event", "fighter2_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    external_key: Mapped[str] = mapped_column(String(100))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    fighter1_id: Mapped[int] = mapped_column(ForeignKey("fighters.id"))
    fighter2_id: Mapped[int] = mapped_column(ForeignKey("fighters.id"))

    status: Mapped[str] = mapped_column(String(20), index=True)
    outcome: Mapped[str | None] = mapped_column(String(20))
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("fighters.id"))
    method: Mapped[str | None] = mapped_column(String(20))
    method_detail: Mapped[str | None] = mapped_column(String(100))
    finish_details: Mapped[str | None] = mapped_column(Text)
    end_round: Mapped[int | None] = mapped_column(Integer)
    end_time_seconds: Mapped[int | None] = mapped_column(Integer)

    scheduled_rounds: Mapped[int | None] = mapped_column(Integer)
    # "source" when parsed from time_format; "rule:title" / "rule:main_event" when inferred from
    # UFC rules (title fights and main events are five rounds) for bouts the source left blank.
    scheduled_rounds_source: Mapped[str | None] = mapped_column(String(30))
    time_format: Mapped[str | None] = mapped_column(String(50))
    weight_class_raw: Mapped[str | None] = mapped_column(String(100))
    division: Mapped[str | None] = mapped_column(String(50))
    is_title_bout: Mapped[bool] = mapped_column(Boolean, default=False)
    referee: Mapped[str | None] = mapped_column(String(100))

    source_row_hash: Mapped[str] = mapped_column(String(64))
    first_seen_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"))
    last_seen_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"))

    event: Mapped[Event] = relationship(back_populates="bouts")
    fighter1: Mapped[Fighter] = relationship(foreign_keys=[fighter1_id])
    fighter2: Mapped[Fighter] = relationship(foreign_keys=[fighter2_id])


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(100), unique=True)
    feature_set_version: Mapped[str] = mapped_column(String(20))
    schema_hash: Mapped[str] = mapped_column(String(32))
    winner_model: Mapped[str] = mapped_column(String(30))
    method_model: Mapped[str] = mapped_column(String(30))
    artifact_path: Mapped[str] = mapped_column(String(500))
    data_snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    trained_through: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Prediction(Base):
    """A stored pre-fight estimate. Keyed so a re-run with the same inputs is a no-op."""

    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint(
            "bout_id", "model_version_id", "as_of", name="uq_prediction_bout_model_asof"
        ),
        CheckConstraint("p_a >= 0 AND p_a <= 1", name="ck_prediction_p_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bout_id: Mapped[int] = mapped_column(ForeignKey("bouts.id"), index=True)
    fighter_a_id: Mapped[int] = mapped_column(ForeignKey("fighters.id"))
    fighter_b_id: Mapped[int] = mapped_column(ForeignKey("fighters.id"))
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    feature_set_version: Mapped[str] = mapped_column(String(20))
    as_of: Mapped[date] = mapped_column(Date)
    scheduled_rounds: Mapped[int | None] = mapped_column(Integer)
    p_a: Mapped[float] = mapped_column(Float)
    outcomes: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    model_version: Mapped[ModelVersion] = relationship()


class BenchmarkOdds(Base):
    """Bookmaker odds kept strictly as an evaluation benchmark.

    Nothing in app.ml features, models or inference may read this table; tests enforce it.
    Moneylines are American odds, mapped onto the bout's fighter1/fighter2 order.
    """

    __tablename__ = "benchmark_odds"
    __table_args__ = (
        UniqueConstraint("bout_id", "source_key", name="uq_benchmark_odds_bout_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bout_id: Mapped[int] = mapped_column(ForeignKey("bouts.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(50))
    source_sha256: Mapped[str] = mapped_column(String(64))
    match_method: Mapped[str] = mapped_column(String(20))  # exact / fuzzy
    f1_moneyline: Mapped[float] = mapped_column(Float)
    f2_moneyline: Mapped[float] = mapped_column(Float)
    # Method props ("fighter wins by ..."), American odds; any may be missing.
    f1_ko: Mapped[float | None] = mapped_column(Float)
    f1_sub: Mapped[float | None] = mapped_column(Float)
    f1_dec: Mapped[float | None] = mapped_column(Float)
    f2_ko: Mapped[float | None] = mapped_column(Float)
    f2_sub: Mapped[float | None] = mapped_column(Float)
    f2_dec: Mapped[float | None] = mapped_column(Float)


class PredictionResult(Base):
    """How a stored prediction fared once its bout had a result. One row per prediction."""

    __tablename__ = "prediction_results"
    __table_args__ = (
        CheckConstraint("status IN ('scored', 'void')", name="ck_prediction_result_status"),
        CheckConstraint(
            "timing IN ('pre_fight', 'same_day', 'after')", name="ck_prediction_result_timing"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), unique=True)
    bout_id: Mapped[int] = mapped_column(ForeignKey("bouts.id"), index=True)
    # pre_fight: stored before the event's calendar day (UTC). Only these count as forecasts.
    timing: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # void = draw / no contest (win-only model)
    actual_outcome: Mapped[str] = mapped_column(String(20))
    actual_method: Mapped[str | None] = mapped_column(String(20))
    p_actual_winner: Mapped[float | None] = mapped_column(Float)
    favourite_correct: Mapped[bool | None] = mapped_column(Boolean)
    log_loss: Mapped[float | None] = mapped_column(Float)
    brier: Mapped[float | None] = mapped_column(Float)
    # P(exact winner + method); None when the method isn't one we model (DQ, overturned, ...).
    p_actual_outcome: Mapped[float | None] = mapped_column(Float)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prediction: Mapped[Prediction] = relationship()
