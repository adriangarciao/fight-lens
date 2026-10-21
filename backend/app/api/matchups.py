from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AsOf, DbSession, get_fighter_or_404
from app.schemas.matchups import H2HResponse, MatchupComparison
from app.schemas.profile import MatchupProfile
from app.services import matchups, predictions

router = APIRouter(prefix="/api/matchups", tags=["matchups"])

FighterA = Annotated[int, Query(alias="fighterA")]
FighterB = Annotated[int, Query(alias="fighterB")]


@router.get("", response_model=MatchupComparison)
def compare(db: DbSession, as_of: AsOf, fighter_a: FighterA, fighter_b: FighterB):
    if fighter_a == fighter_b:
        raise HTTPException(status_code=422, detail="Choose two different fighters")
    return matchups.compare(
        db, get_fighter_or_404(db, fighter_a), get_fighter_or_404(db, fighter_b), as_of
    )


@router.get("/history", response_model=H2HResponse)
def history(db: DbSession, as_of: AsOf, fighter_a: FighterA, fighter_b: FighterB):
    a, b = get_fighter_or_404(db, fighter_a), get_fighter_or_404(db, fighter_b)
    return H2HResponse(as_of=as_of, meetings=matchups.head_to_head(db, a, b, as_of))


@router.get("/profile", response_model=MatchupProfile)
def profile(db: DbSession, as_of: AsOf, fighter_a: FighterA, fighter_b: FighterB):
    """Rating histories and league averages for charts; works without an active model."""
    a, b = get_fighter_or_404(db, fighter_a), get_fighter_or_404(db, fighter_b)
    return predictions.matchup_profile(db, a, b, as_of)
