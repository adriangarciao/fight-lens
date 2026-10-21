"""Plain-data view of the bout history for feature building, decoupled from the ORM."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Bout, Event, Fighter, FighterBoutStats
from app.ingestion.normalize import fight_seconds


@dataclass(frozen=True)
class StatLine:
    """One fighter's whole-fight totals in one bout."""

    kd: int
    sig_landed: int
    sig_attempted: int
    td_landed: int
    td_attempted: int
    sub_attempts: int
    ctrl_seconds: int
    distance_landed: int
    clinch_landed: int
    ground_landed: int


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
    seconds: int | None = None  # elapsed fight time
    stats: tuple[StatLine, StatLine] | None = None  # (fighter 1, fighter 2) when both exist


@dataclass(frozen=True)
class FighterStatic:
    dob: date | None
    height_in: float | None
    reach_in: float | None
    stance: str | None


def _load_stats(session: Session) -> dict[tuple[int, int], StatLine]:
    s = FighterBoutStats
    rows = session.execute(
        select(
            s.bout_id,
            s.fighter_id,
            func.sum(s.kd),
            func.sum(s.sig_landed),
            func.sum(s.sig_attempted),
            func.sum(s.td_landed),
            func.sum(s.td_attempted),
            func.sum(s.sub_attempts),
            func.sum(func.coalesce(s.ctrl_seconds, 0)),
            func.sum(s.distance_landed),
            func.sum(s.clinch_landed),
            func.sum(s.ground_landed),
        ).group_by(s.bout_id, s.fighter_id)
    )
    return {(r[0], r[1]): StatLine(*(int(v) for v in r[2:])) for r in rows}


def load_history(session: Session) -> tuple[list[BoutRow], dict[int, FighterStatic]]:
    """All completed bouts (oldest first) with per-fight stats, and static fighter attributes."""
    stats = _load_stats(session)
    rows = []
    for b, on in session.execute(
        select(Bout, Event.event_date)
        .join(Bout.event)
        .where(Bout.status == "completed")
        .order_by(Event.event_date, Bout.id)
    ):
        s1, s2 = stats.get((b.id, b.fighter1_id)), stats.get((b.id, b.fighter2_id))
        rows.append(
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
                seconds=fight_seconds(b.time_format, b.end_round, b.end_time_seconds),
                stats=(s1, s2) if s1 is not None and s2 is not None else None,
            )
        )
    statics = {
        f.id: FighterStatic(f.dob, f.height_in, f.reach_in, f.stance)
        for f in session.scalars(select(Fighter))
    }
    return rows, statics
