from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import Fighter
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]


def as_of_or_today(
    as_of: Annotated[
        date | None, Query(alias="asOf", description="Only bouts before this date count")
    ] = None,
) -> date:
    return as_of or date.today()


AsOf = Annotated[date, Depends(as_of_or_today)]


def get_fighter_or_404(session: Session, fighter_id: int) -> Fighter:
    fighter = session.get(Fighter, fighter_id)
    if fighter is None:
        raise HTTPException(status_code=404, detail=f"Fighter {fighter_id} not found")
    return fighter
