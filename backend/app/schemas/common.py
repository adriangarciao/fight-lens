from datetime import date
from typing import Literal

from pydantic import BaseModel

Result = Literal["W", "L", "D", "NC"]


class FighterRef(BaseModel):
    id: int
    name: str


class Record(BaseModel):
    """UFC record as covered by the source data, counting only bouts before the as-of date."""

    wins: int = 0
    losses: int = 0
    draws: int = 0
    no_contests: int = 0

    def __str__(self) -> str:
        base = f"{self.wins}-{self.losses}-{self.draws}"
        return f"{base} ({self.no_contests} NC)" if self.no_contests else base


class EventRef(BaseModel):
    id: int
    name: str
    date: date
    location: str | None
