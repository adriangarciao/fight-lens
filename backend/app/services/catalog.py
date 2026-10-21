"""Fighter search and event listings."""

from datetime import date

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Bout, Event, Fighter
from app.ingestion.normalize import name_key
from app.schemas.common import FighterRef
from app.schemas.events import CardBout, EventDetail, EventSummary
from app.schemas.fighters import FighterSearchResult
from app.services.history import RecordLookup, completed_bouts, latest_division, result_for, tally
from app.services.predictions import card_predictions


def search_fighters(
    session: Session, q: str, as_of: date, limit: int = 20
) -> list[FighterSearchResult]:
    key = name_key(q)
    if not key:
        return []
    fighters = list(
        session.scalars(
            select(Fighter)
            .where(or_(Fighter.name_key.like(f"{key}%"), Fighter.name_key.like(f"% {key}%")))
            .order_by(Fighter.display_name)
            .limit(200)
        )
    )
    bouts = completed_bouts(session, (f.id for f in fighters), as_of)
    results = []
    for f in fighters:
        mine = [b for b in reversed(bouts) if f.id in (b.fighter1_id, b.fighter2_id)]
        results.append(
            FighterSearchResult(
                id=f.id,
                name=f.display_name,
                latest_division=latest_division(mine),
                last_fight_date=mine[0].event.event_date if mine else None,
                record=tally(result_for(b, f.id) for b in mine),
            )
        )
    # Exact/prefix name matches first, then the most experienced fighters.
    results.sort(
        key=lambda r: (not name_key(r.name).startswith(key), -(r.record.wins + r.record.losses))
    )
    return results[:limit]


def upcoming_events(session: Session, today: date) -> list[EventSummary]:
    return _event_summaries(session, Event.event_date >= today, Event.event_date.asc())


def recent_events(session: Session, today: date, limit: int = 10) -> list[EventSummary]:
    return _event_summaries(session, Event.event_date < today, Event.event_date.desc(), limit)


def _event_summaries(
    session: Session, condition, order, limit: int | None = None
) -> list[EventSummary]:
    stmt = (
        select(Event, func.count(Bout.id), func.sum(case((Bout.status == "scheduled", 1), else_=0)))
        .join(Bout)
        .where(condition)
        .group_by(Event.id)
        .order_by(order)
        .limit(limit)
    )
    summaries = []
    for event, count, scheduled in session.execute(stmt):
        summaries.append(
            EventSummary(
                id=event.id,
                name=event.name,
                date=event.event_date,
                location=event.location,
                bout_count=count,
                status="scheduled" if scheduled else "completed",
            )
        )
    return summaries


def event_detail(session: Session, event_id: int) -> EventDetail | None:
    event = session.get(Event, event_id)
    if event is None:
        return None
    bouts = list(
        session.scalars(
            select(Bout)
            .options(joinedload(Bout.fighter1), joinedload(Bout.fighter2))
            .where(Bout.event_id == event_id)
            .order_by(Bout.id)
        )
    )
    # Records shown on a card are as of the event date: what was known going in.
    lookup = RecordLookup(
        session, [fid for b in bouts for fid in (b.fighter1_id, b.fighter2_id)], event.event_date
    )
    preds = card_predictions(session, [b.id for b in bouts])
    card = [
        CardBout(
            bout_id=b.id,
            fighter_1=FighterRef(id=b.fighter1.id, name=b.fighter1.display_name),
            fighter_2=FighterRef(id=b.fighter2.id, name=b.fighter2.display_name),
            record_1=lookup.before(b.fighter1_id, event.event_date),
            record_2=lookup.before(b.fighter2_id, event.event_date),
            division=b.division,
            weight_class_raw=b.weight_class_raw,
            scheduled_rounds=b.scheduled_rounds,
            scheduled_rounds_source=b.scheduled_rounds_source,
            is_title_bout=b.is_title_bout,
            status=b.status,
            winner_id=b.winner_id,
            outcome=b.outcome,
            method=b.method,
            end_round=b.end_round,
            end_time_seconds=b.end_time_seconds,
            prediction=preds.get(b.id),
        )
        for b in bouts
    ]
    has_scheduled = any(b.status == "scheduled" for b in bouts)
    return EventDetail(
        id=event.id,
        name=event.name,
        date=event.event_date,
        location=event.location,
        bout_count=len(card),
        status="scheduled" if has_scheduled else "completed",
        bouts=card,
    )
