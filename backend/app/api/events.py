from datetime import date

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession
from app.schemas.events import EventDetail, EventSummary
from app.services import catalog

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/upcoming", response_model=list[EventSummary])
def upcoming(db: DbSession):
    return catalog.upcoming_events(db, date.today())


@router.get("/recent", response_model=list[EventSummary])
def recent(db: DbSession):
    return catalog.recent_events(db, date.today())


@router.get("/{event_id}", response_model=EventDetail)
def detail(event_id: int, db: DbSession):
    event = catalog.event_detail(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return event
