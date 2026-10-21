from datetime import date

from sqlalchemy.orm import Session

from app.db.models import Bout, Fighter
from app.schemas.common import FighterRef
from app.schemas.fighters import FightRecord
from app.schemas.matchups import CommonOpponent, CommonOpponentSide, MatchupComparison, Meeting
from app.services.history import NON_DIVISIONS, completed_bouts, event_ref, summarize

STANDING_NOTES = [
    "Common-opponent results are context, not proof: MMA results are not transitive.",
    "Per-bout striking and grappling statistics are not available from the current data source.",
    "Records count only UFC bouts present in the source data before the as-of date.",
]


def head_to_head(session: Session, a: Fighter, b: Fighter, as_of: date) -> list[Meeting]:
    return _meetings(completed_bouts(session, [a.id, b.id], as_of), a.id, b.id, as_of)


def compare(session: Session, a: Fighter, b: Fighter, as_of: date) -> MatchupComparison:
    bouts = completed_bouts(session, [a.id, b.id], as_of)
    summary_a, records_a = summarize(session, a, as_of, bouts)
    summary_b, records_b = summarize(session, b, as_of, bouts)

    notes = list(STANDING_NOTES)
    meetings = _meetings(bouts, a.id, b.id, as_of)
    if meetings and meetings[0].days_before_as_of > 3 * 365:
        notes.append("The most recent meeting is over three years old; weigh it lightly.")

    return MatchupComparison(
        as_of=as_of,
        fighter_a=summary_a,
        fighter_b=summary_b,
        head_to_head=meetings,
        common_opponents=_common_opponents(records_a, records_b, a.id, b.id, as_of),
        notes=notes,
    )


def _meetings(bouts: list[Bout], a_id: int, b_id: int, as_of: date) -> list[Meeting]:
    pair = {a_id, b_id}
    meetings = []
    for i, bout in enumerate(bouts):
        if {bout.fighter1_id, bout.fighter2_id} != pair:
            continue
        later = bouts[i + 1 :]
        division_changes, fights_since = {}, {}
        for fid in pair:
            theirs = [x for x in later if fid in (x.fighter1_id, x.fighter2_id)]
            fights_since[fid] = len(theirs)
            division_changes[fid] = sorted(
                {x.division for x in theirs if x.division not in NON_DIVISIONS} - {bout.division}
            )
        winner = None
        if bout.winner_id is not None:
            w = bout.fighter1 if bout.winner_id == bout.fighter1_id else bout.fighter2
            winner = FighterRef(id=w.id, name=w.display_name)
        meetings.append(
            Meeting(
                bout_id=bout.id,
                event=event_ref(bout.event),
                winner=winner,
                outcome=bout.outcome,
                method=bout.method,
                method_detail=bout.method_detail,
                end_round=bout.end_round,
                end_time_seconds=bout.end_time_seconds,
                division=bout.division,
                days_before_as_of=(as_of - bout.event.event_date).days,
                division_changes=division_changes,
                fights_since=fights_since,
            )
        )
    return list(reversed(meetings))


def _common_opponents(
    records_a: list[FightRecord], records_b: list[FightRecord], a_id: int, b_id: int, as_of: date
) -> list[CommonOpponent]:
    by_opp_a = _group_by_opponent(records_a, exclude=b_id)
    by_opp_b = _group_by_opponent(records_b, exclude=a_id)
    result = []
    for opp_id in by_opp_a.keys() & by_opp_b.keys():
        fights_a, fights_b = by_opp_a[opp_id], by_opp_b[opp_id]
        latest_a, latest_b = fights_a[0].event.date, fights_b[0].event.date
        gap = abs((latest_a - latest_b).days)
        oldest = min(f.event.date for f in fights_a + fights_b)

        limited = []
        if gap > 3 * 365:
            limited.append(f"Bouts against this opponent are {gap / 365.25:.1f} years apart.")
        if (as_of - oldest).days > 5 * 365:
            limited.append(f"Relies on a bout from {oldest.year}.")
        divisions = {f.division for f in fights_a + fights_b if f.division not in NON_DIVISIONS}
        if len(divisions) > 1:
            limited.append(
                "Bouts took place in different divisions: " + ", ".join(sorted(divisions))
            )

        result.append(
            CommonOpponent(
                opponent=fights_a[0].opponent,
                fighter_a=CommonOpponentSide(fights=fights_a),
                fighter_b=CommonOpponentSide(fights=fights_b),
                gap_days=gap,
                limited_comparison=limited,
            )
        )
    result.sort(
        key=lambda c: max(c.fighter_a.fights[0].event.date, c.fighter_b.fights[0].event.date),
        reverse=True,
    )
    return result


def _group_by_opponent(records: list[FightRecord], exclude: int) -> dict[int, list[FightRecord]]:
    grouped: dict[int, list[FightRecord]] = {}
    for r in records:
        if r.opponent.id != exclude:
            grouped.setdefault(r.opponent.id, []).append(r)
    return grouped
