"""Fighter identity resolution for name-keyed sources.

The bout file identifies fighters only by name. Rules:

1. A name with zero or one roster entry is one fighter; its external key is the name key.
2. A name shared by several roster entries (e.g. two different "Bruno Silva"s) is resolved per
   bout: drop candidates who would be under 18 or over 50 on the bout date, then pick the
   candidate whose listed weight is closest to the bout's division limit. The external key gets
   a suffix (DOB, else listed weight) so the two people never merge.
3. When rule 2 can't decide (unknown division, or a tie), the first candidate is used and the
   bout is reported as `ambiguous_identity` so a human can add an override.
"""

from dataclasses import dataclass, field
from datetime import date

from app.ingestion.normalize import DIVISION_LIMITS, name_key


@dataclass(frozen=True)
class RosterEntry:
    name: str
    weight_lbs: float | None
    dob: date | None
    height_in: float | None
    reach_in: float | None
    stance: str | None

    @property
    def key(self) -> str:
        return name_key(self.name)


@dataclass
class Resolution:
    external_key: str
    roster: RosterEntry | None
    ambiguous: bool = False


@dataclass
class IdentityResolver:
    roster: list[RosterEntry]
    _by_key: dict[str, list[RosterEntry]] = field(init=False)

    def __post_init__(self) -> None:
        self._by_key = {}
        for entry in self.roster:
            self._by_key.setdefault(entry.key, []).append(entry)

    @property
    def colliding_keys(self) -> set[str]:
        return {k for k, entries in self._by_key.items() if len(entries) > 1}

    def resolve(self, name: str, division: str | None, bout_date: date | None) -> Resolution:
        key = name_key(name)
        candidates = self._by_key.get(key, [])
        if len(candidates) <= 1:
            return Resolution(key, candidates[0] if candidates else None)

        plausible = [c for c in candidates if _plausible_age(c.dob, bout_date)] or candidates
        limit = DIVISION_LIMITS.get(division or "")
        chosen, ambiguous = plausible[0], True
        if len(plausible) == 1:
            ambiguous = False
        elif limit is not None:
            ranked = sorted(plausible, key=lambda c: _weight_distance(c.weight_lbs, limit))
            best, runner_up = ranked[0], ranked[1]
            chosen = best
            ambiguous = _weight_distance(best.weight_lbs, limit) == _weight_distance(
                runner_up.weight_lbs, limit
            )
        return Resolution(f"{key}#{_suffix(chosen)}", chosen, ambiguous)


def _plausible_age(dob: date | None, on: date | None) -> bool:
    if dob is None or on is None:
        return True
    age = (on - dob).days / 365.25
    return 18 <= age <= 50


def _weight_distance(weight: float | None, limit: int) -> float:
    return abs(weight - limit) if weight is not None else float("inf")


def _suffix(entry: RosterEntry) -> str:
    if entry.dob:
        return entry.dob.isoformat()
    if entry.weight_lbs:
        return f"{entry.weight_lbs:g}lbs"
    return "unknown"
