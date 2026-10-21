"""Time-correct fight history.

Every function here takes an `as_of` date and only sees completed bouts whose event date is
strictly before it. That is the same rule the training features will use, so a matchup page for
a past event shows what was knowable before that event, never later results.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Bout, Event, Fighter, FighterBoutStats
from app.ingestion.normalize import fight_seconds
from app.schemas.common import EventRef, FighterRef, Record, Result
from app.schemas.fighters import (
    Activity,
    FighterSummary,
    FightRecord,
    Physical,
    Streak,
    StyleStats,
    StyleSummary,
)

LONG_LAYOFF_DAYS = 365
SHORT_TURNAROUND_DAYS = 60
# Divisions that say nothing about a fighter's regular weight class.
NON_DIVISIONS = {None, "Catch Weight", "Open Weight"}


def completed_bouts(session: Session, fighter_ids: Iterable[int], as_of: date) -> list[Bout]:
    """Completed bouts involving any of `fighter_ids` before `as_of`, oldest first."""
    ids = list(set(fighter_ids))
    if not ids:
        return []
    stmt = (
        select(Bout)
        .join(Bout.event)
        .options(joinedload(Bout.event), joinedload(Bout.fighter1), joinedload(Bout.fighter2))
        .where(
            Bout.status == "completed",
            Event.event_date < as_of,
            or_(Bout.fighter1_id.in_(ids), Bout.fighter2_id.in_(ids)),
        )
        .order_by(Event.event_date, Bout.id)
    )
    return list(session.scalars(stmt).unique())


def result_for(bout: Bout, fighter_id: int) -> Result:
    if bout.outcome == "win":
        return "W" if bout.winner_id == fighter_id else "L"
    return "D" if bout.outcome == "draw" else "NC"


def opponent_of(bout: Bout, fighter_id: int) -> Fighter:
    return bout.fighter2 if bout.fighter1_id == fighter_id else bout.fighter1


def tally(results: Iterable[Result]) -> Record:
    rec = Record()
    for r in results:
        match r:
            case "W":
                rec.wins += 1
            case "L":
                rec.losses += 1
            case "D":
                rec.draws += 1
            case "NC":
                rec.no_contests += 1
    return rec


class RecordLookup:
    """Answers "what was fighter X's record before date D" for a set of fighters."""

    def __init__(self, session: Session, fighter_ids: Iterable[int], as_of: date):
        self._dated: dict[int, list[tuple[date, Result]]] = defaultdict(list)
        ids = set(fighter_ids)
        for bout in completed_bouts(session, ids, as_of):
            for fid in (bout.fighter1_id, bout.fighter2_id):
                if fid in ids:
                    self._dated[fid].append((bout.event.event_date, result_for(bout, fid)))

    def before(self, fighter_id: int, on: date) -> Record:
        return tally(r for d, r in self._dated[fighter_id] if d < on)


def fight_records(
    session: Session, fighter_id: int, bouts: list[Bout], as_of: date
) -> list[FightRecord]:
    """Fighter-perspective records for `bouts`, newest first."""
    mine = [b for b in bouts if fighter_id in (b.fighter1_id, b.fighter2_id)]
    lookup = RecordLookup(session, (opponent_of(b, fighter_id).id for b in mine), as_of)
    records = []
    for b in reversed(mine):
        opp = opponent_of(b, fighter_id)
        records.append(
            FightRecord(
                bout_id=b.id,
                event=event_ref(b.event),
                opponent=FighterRef(id=opp.id, name=opp.display_name),
                opponent_record_before=lookup.before(opp.id, b.event.event_date),
                result=result_for(b, fighter_id),
                method=b.method,
                method_detail=b.method_detail,
                finish_details=b.finish_details,
                end_round=b.end_round,
                end_time_seconds=b.end_time_seconds,
                scheduled_rounds=b.scheduled_rounds,
                division=b.division,
                is_title_bout=b.is_title_bout,
                days_before_as_of=(as_of - b.event.event_date).days,
            )
        )
    return records


def event_ref(event: Event) -> EventRef:
    return EventRef(id=event.id, name=event.name, date=event.event_date, location=event.location)


def streak(records: list[FightRecord]) -> Streak:
    """Current streak, newest first. No-contests are skipped rather than breaking a streak."""
    kind, count = None, 0
    for r in records:
        if r.result == "NC":
            continue
        if kind is None:
            kind = r.result
        if r.result != kind:
            break
        count += 1
    return Streak(kind=kind or "none", count=count)


def activity(records: list[FightRecord], as_of: date) -> Activity:
    if not records:
        return Activity(
            days_since_last_fight=None,
            fights_last_12_months=0,
            fights_last_24_months=0,
            layoff_flag="debut",
        )
    days = records[0].days_before_as_of
    # Descriptive labels only; whether a layoff matters is for the model to learn, not assume.
    flag = (
        "long_layoff"
        if days >= LONG_LAYOFF_DAYS
        else "short_turnaround"
        if days <= SHORT_TURNAROUND_DAYS
        else "normal"
    )
    return Activity(
        days_since_last_fight=days,
        fights_last_12_months=sum(r.event.date >= as_of - timedelta(days=365) for r in records),
        fights_last_24_months=sum(r.event.date >= as_of - timedelta(days=730) for r in records),
        layoff_flag=flag,
    )


def latest_division(records: list[FightRecord]) -> str | None:
    return next((r.division for r in records if r.division not in NON_DIVISIONS), None)


def style_summary(session: Session, fighter_id: int, bouts: list[Bout]) -> StyleSummary:
    """Career and last-five raw stat rates from the fighter's bouts (already before as-of)."""
    mine = [b for b in bouts if fighter_id in (b.fighter1_id, b.fighter2_id)]
    totals: dict[tuple[int, bool], dict[str, int]] = {}
    if mine:
        s = FighterBoutStats
        for row in session.execute(
            select(
                s.bout_id,
                s.fighter_id,
                func.sum(s.sig_landed),
                func.sum(s.sig_attempted),
                func.sum(s.td_landed),
                func.sum(s.td_attempted),
                func.sum(s.kd),
                func.sum(s.sub_attempts),
                func.sum(func.coalesce(s.ctrl_seconds, 0)),
            )
            .where(s.bout_id.in_([b.id for b in mine]))
            .group_by(s.bout_id, s.fighter_id)
        ):
            keys = ("sig_l", "sig_a", "td_l", "td_a", "kd", "sub", "ctrl")
            totals[(row[0], row[1] == fighter_id)] = dict(zip(keys, map(int, row[2:]), strict=True))

    usable = []  # newest first: (seconds, my totals, opponent totals)
    for b in reversed(mine):
        secs = fight_seconds(b.time_format, b.end_round, b.end_time_seconds)
        if secs and (b.id, True) in totals and (b.id, False) in totals:
            usable.append((secs, totals[(b.id, True)], totals[(b.id, False)]))

    def rates(items) -> StyleStats | None:
        if not items:
            return None
        minutes = sum(i[0] for i in items) / 60
        me = {k: sum(i[1][k] for i in items) for k in items[0][1]}
        opp = {k: sum(i[2][k] for i in items) for k in items[0][2]}
        return StyleStats(
            fights=len(items),
            minutes=round(minutes, 1),
            slpm=me["sig_l"] / minutes,
            sapm=opp["sig_l"] / minutes,
            str_acc=me["sig_l"] / me["sig_a"] if me["sig_a"] else None,
            str_def=1 - opp["sig_l"] / opp["sig_a"] if opp["sig_a"] else None,
            td15=me["td_l"] / minutes * 15,
            td_acc=me["td_l"] / me["td_a"] if me["td_a"] else None,
            td_def=1 - opp["td_l"] / opp["td_a"] if opp["td_a"] else None,
            kd15=me["kd"] / minutes * 15,
            sub15=me["sub"] / minutes * 15,
            ctrl_share=me["ctrl"] / 60 / minutes,
        )

    return StyleSummary(career=rates(usable), last5=rates(usable[:5]))


def summarize(session: Session, fighter: Fighter, as_of: date, bouts: list[Bout] | None = None):
    """Build a FighterSummary plus the full newest-first record list."""
    if bouts is None:
        bouts = completed_bouts(session, [fighter.id], as_of)
    records = fight_records(session, fighter.id, bouts, as_of)
    debut = records[-1].event.date if records else None

    limited = []
    if not records:
        limited.append("No prior UFC bouts in the source data (debut).")
    elif len(records) < 3:
        limited.append(f"Only {len(records)} prior UFC bout(s) in the source data.")
    if records and records[0].days_before_as_of > 730:
        limited.append("Most recent UFC bout was more than two years ago.")
    divisions = [r.division for r in records if r.division not in NON_DIVISIONS]
    if len(divisions) >= 2 and divisions[0] != divisions[1]:
        limited.append(f"Recent division change: {divisions[1]} -> {divisions[0]}.")
    if fighter.dob is None:
        limited.append("Date of birth unavailable; age unknown.")
    if fighter.reach_in is None:
        limited.append("Reach unavailable.")

    summary = FighterSummary(
        fighter=FighterRef(id=fighter.id, name=fighter.display_name),
        as_of=as_of,
        physical=Physical(
            age_years=round((as_of - fighter.dob).days / 365.25, 1) if fighter.dob else None,
            height_in=fighter.height_in,
            reach_in=fighter.reach_in,
            stance=fighter.stance,
        ),
        record=tally(r.result for r in records),
        last5_record=tally(r.result for r in records[:5]),
        coming_off=records[0].result if records else None,
        streak=streak(records),
        activity=activity(records, as_of),
        ufc_debut=debut,
        years_in_ufc=round((as_of - debut).days / 365.25, 1) if debut else None,
        latest_division=latest_division(records),
        recent_fights=records[:5],
        style=style_summary(session, fighter.id, bouts),
        limited_data=limited,
    )
    return summary, records
