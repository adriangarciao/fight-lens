from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AsOf, DbSession, get_fighter_or_404
from app.schemas.fighters import FighterDetail, FighterSearchResult
from app.services import catalog
from app.services.history import summarize

router = APIRouter(prefix="/api/fighters", tags=["fighters"])


@router.get("/search", response_model=list[FighterSearchResult])
def search(db: DbSession, as_of: AsOf, q: Annotated[str, Query(min_length=2, max_length=100)]):
    return catalog.search_fighters(db, q, as_of)


@router.get("/{fighter_id}", response_model=FighterDetail)
def detail(fighter_id: int, db: DbSession, as_of: AsOf):
    summary, records = summarize(db, get_fighter_or_404(db, fighter_id), as_of)
    return FighterDetail(**summary.model_dump(), all_fights=records)
