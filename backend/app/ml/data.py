"""Plain-data view of the bout history for feature building, decoupled from the ORM."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bout, Event, Fighter


@dataclass(frozen=True)
class BoutRow:
    bout_id: int
    on: date
    f1: int
    f2: int
    outcome: str | None  # win / draw / no_contest; None for scheduled
    winner: int | None
    method: str | None
    end_round: int | None
    scheduled_rounds: int | None
    is_title: bool
    division: str | None


@dataclass(frozen=True)
class FighterStatic:
    dob: date | None
    height_in: float | None
    reach_in: float | None
    stance: str | None


def load_history(session: Session) -> tuple[list[BoutRow], dict[int, FighterStatic]]:
    """All completed bouts (oldest first) and static fighter attributes."""
    rows = [
        BoutRow(
            bout_id=b.id,
            on=on,
            f1=b.fighter1_id,
            f2=b.fighter2_id,
            outcome=b.outcome,
            winner=b.winner_id,
            method=b.method,
            end_round=b.end_round,
            scheduled_rounds=b.scheduled_rounds,
            is_title=b.is_title_bout,
            division=b.division,
        )
        for b, on in session.execute(
            select(Bout, Event.event_date)
            .join(Bout.event)
            .where(Bout.status == "completed")
            .order_by(Event.event_date, Bout.id)
        )
    ]
    statics = {
        f.id: FighterStatic(f.dob, f.height_in, f.reach_in, f.stance)
        for f in session.scalars(select(Fighter))
    }
    return rows, statics
