from datetime import date

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession, get_fighter_or_404
from app.ml.artifacts import IncompatibleArtifact
from app.schemas.predictions import MatchupPredictionRequest, PredictionOut
from app.services import predictions

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


def _guard(fn):
    try:
        return fn()
    except predictions.NoActiveModel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IncompatibleArtifact as exc:
        # Refuse inference rather than feed a model features it wasn't trained on.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/matchup", response_model=PredictionOut)
def matchup(req: MatchupPredictionRequest, db: DbSession):
    if req.fighter_a == req.fighter_b:
        raise HTTPException(status_code=422, detail="Choose two different fighters")
    a, b = get_fighter_or_404(db, req.fighter_a), get_fighter_or_404(db, req.fighter_b)
    return _guard(
        lambda: predictions.predict_matchup(
            db, a, b, req.as_of or date.today(), req.scheduled_rounds, req.title_bout
        )
    )


@router.get("/{bout_id}", response_model=PredictionOut)
def for_bout(bout_id: int, db: DbSession):
    out = _guard(lambda: predictions.predict_bout(db, bout_id))
    if out is None:
        raise HTTPException(status_code=404, detail=f"Bout {bout_id} not found")
    return out
