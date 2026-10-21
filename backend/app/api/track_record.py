from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.track_record import TrackRecord
from app.services import track_record

router = APIRouter(prefix="/api/track-record", tags=["track record"])


@router.get("", response_model=TrackRecord)
def get_track_record(db: DbSession):
    return track_record.track_record(db)
