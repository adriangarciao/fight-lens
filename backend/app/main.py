from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import events, fighters, matchups, predictions, track_record
from app.config import get_settings

app = FastAPI(
    title="FightLens API",
    version="0.1.0",
    description="UFC matchup analysis. Outputs are model estimates, not guaranteed results.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(events.router)
app.include_router(fighters.router)
app.include_router(matchups.router)
app.include_router(predictions.router)
app.include_router(track_record.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
