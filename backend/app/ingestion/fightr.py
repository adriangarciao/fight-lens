"""Importer for the fightr bout file (completed + scheduled) and roster physical attributes.

Idempotent: re-importing the same snapshot changes nothing. Re-importing a newer snapshot
records scheduled bouts that became results. A completed bout whose result *changes* is never
overwritten silently; it goes into the report as `result_changed` and is left as-is.
"""

import csv
import hashlib
import json
import shutil
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bout, DataSource, Event, Fighter, FighterExternalId, IngestionRun
from app.ingestion import normalize as n
from app.ingestion.identity import IdentityResolver, RosterEntry

SOURCE_KEY = "fightr"
RAW_BASE_URL = "https://raw.githubusercontent.com/benyamindsmith/fightr/HEAD/data"
# ultimate_ufc_dataset.csv carries bookmaker odds; it is only read by app.benchmarks.
FILES = ("ufc_fights.csv", "ufcstats_data.csv", "ultimate_ufc_dataset.csv")


def fetch_snapshot(data_dir: Path, today: date | None = None) -> Path:
    """Download the current fightr files into data/raw/fightr-YYYY-MM-DD/."""
    target = data_dir / "raw" / f"{SOURCE_KEY}-{(today or date.today()).isoformat()}"
    target.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        with urllib.request.urlopen(f"{RAW_BASE_URL}/{name}", timeout=60) as resp:
            with open(target / name, "wb") as out:
                shutil.copyfileobj(resp, out)
    return target


def latest_snapshot(data_dir: Path) -> Path | None:
    snapshots = sorted((data_dir / "raw").glob(f"{SOURCE_KEY}-*"))
    return snapshots[-1] if snapshots else None


@dataclass
class ImportReport:
    bouts_inserted: int = 0
    bouts_updated: int = 0
    bouts_unchanged: int = 0
    results_recorded: int = 0
    fighters_created: int = 0
    events_created: int = 0
    issues: dict[str, list] = field(default_factory=dict)

    def add(self, kind: str, detail: object) -> None:
        self.issues.setdefault(kind, []).append(detail)

    def stats(self) -> dict:
        return {
            "bouts_inserted": self.bouts_inserted,
            "bouts_updated": self.bouts_updated,
            "bouts_unchanged": self.bouts_unchanged,
            "results_recorded": self.results_recorded,
            "fighters_created": self.fighters_created,
            "events_created": self.events_created,
            "issue_counts": {k: len(v) for k, v in self.issues.items()},
        }


def read_roster(path: Path) -> list[RosterEntry]:
    """Accepts both fightr live headers (Name, STANCE, DOB, ...) and TidyTuesday snake_case."""
    if not path.exists():
        return []
    entries = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row = {k.strip().lower(): v for k, v in row.items()}
            name = n.clean(row.get("name"))
            if not name:
                continue
            entries.append(
                RosterEntry(
                    name=name,
                    weight_lbs=n.parse_lbs(row.get("weight")),
                    dob=n.parse_date(row.get("dob")),
                    height_in=n.parse_height_in(row.get("height")),
                    reach_in=n.parse_inches(row.get("reach")),
                    stance=n.clean(row.get("stance")),
                )
            )
    return entries


def import_snapshot(session: Session, snapshot_dir: Path) -> ImportReport:
    fights_path = snapshot_dir / "ufc_fights.csv"
    source = _get_or_create_source(session)
    run = IngestionRun(
        source_id=source.id,
        snapshot_path=str(snapshot_dir),
        snapshot_sha256=hashlib.sha256(fights_path.read_bytes()).hexdigest(),
        stats={},
        report={},
    )
    session.add(run)
    session.flush()

    importer = _Importer(
        session, source, run, IdentityResolver(read_roster(snapshot_dir / "ufcstats_data.csv"))
    )
    with open(fights_path, newline="", encoding="utf-8") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            importer.import_row(line_no, row)

    report = importer.report
    run.finished_at = datetime.now(UTC)
    run.stats = report.stats()
    run.report = report.issues
    session.commit()
    return report


def _get_or_create_source(session: Session) -> DataSource:
    source = session.scalar(select(DataSource).where(DataSource.key == SOURCE_KEY))
    if source is None:
        source = DataSource(
            key=SOURCE_KEY,
            name="fightr R package data (derived from UFCStats)",
            url="https://github.com/benyamindsmith/fightr",
            license="MIT (code); underlying facts from UFCStats - verify before commercial use",
        )
        session.add(source)
        session.flush()
    return source


class _Importer:
    def __init__(
        self, session: Session, source: DataSource, run: IngestionRun, resolver: IdentityResolver
    ):
        self.session = session
        self.source = source
        self.run = run
        self.resolver = resolver
        self.report = ImportReport()
        self._fighters: dict[str, Fighter] = {
            ext.external_key: ext.fighter
            for ext in session.scalars(
                select(FighterExternalId).where(FighterExternalId.source_id == source.id)
            )
        }
        self._events: dict[str, Event] = {
            e.external_key: e
            for e in session.scalars(select(Event).where(Event.source_id == source.id))
        }
        self._bouts: dict[str, Bout] = {
            b.external_key: b
            for b in session.scalars(select(Bout).where(Bout.source_id == source.id))
        }
        self._seen_pairings: dict[tuple, str] = {}

    def import_row(self, line_no: int, row: dict) -> None:
        url = n.clean(row.get("fight_url"))
        event_name = n.clean(row.get("event_name"))
        event_date = n.parse_date(row.get("date"))
        name1, name2 = n.clean(row.get("f1_name")), n.clean(row.get("f2_name"))
        if not (url and event_name and event_date and name1 and name2):
            self.report.add("missing_required_field", {"line": line_no, "fight_url": url})
            return
        try:
            outcome, winner_pos = n.parse_outcome(row.get("f1_result"), row.get("f2_result"))
        except ValueError as exc:
            self.report.add(
                "contradictory_result", {"line": line_no, "fight_url": url, "error": str(exc)}
            )
            return

        division = n.parse_division(row.get("weight_class"))
        if division is None:
            self.report.add(
                "unknown_division", {"line": line_no, "weight_class": row.get("weight_class")}
            )
        f1 = self._fighter(name1, division, event_date, url)
        f2 = self._fighter(name2, division, event_date, url)
        if f1.id == f2.id:
            self.report.add("same_fighter_both_sides", {"line": line_no, "fight_url": url})
            return

        status = "completed" if outcome else "scheduled"
        method_raw = n.clean(row.get("method"))
        method = n.parse_method(method_raw)
        if status == "completed" and method is None:
            self.report.add("unknown_method", {"line": line_no, "method": method_raw})
        title = n.is_title_bout(row.get("weight_class"))
        rounds, rounds_source = n.infer_scheduled_rounds(
            row.get("time_format"), title, event_name, name1, name2
        )
        values = {
            "event_id": self._event(event_name, event_date, n.clean(row.get("location"))).id,
            "fighter1_id": f1.id,
            "fighter2_id": f2.id,
            "status": status,
            "outcome": outcome,
            "winner_id": {1: f1.id, 2: f2.id}.get(winner_pos),
            "method": method,
            "method_detail": method_raw,
            "finish_details": n.clean(row.get("judging_details")),
            "end_round": int(r) if (r := n.clean(row.get("round"))) else None,
            "end_time_seconds": n.parse_time_seconds(row.get("time")),
            "scheduled_rounds": rounds,
            "scheduled_rounds_source": rounds_source,
            "time_format": n.clean(row.get("time_format")),
            "weight_class_raw": n.clean(row.get("weight_class")),
            "division": division,
            "is_title_bout": title,
            "referee": n.clean(row.get("referee")),
        }
        if status == "completed":
            pairing = (event_date, frozenset((f1.id, f2.id)))
            if pairing in self._seen_pairings:
                self.report.add(
                    "duplicate_pairing",
                    {"line": line_no, "fight_url": url, "other": self._seen_pairings[pairing]},
                )
            self._seen_pairings[pairing] = url
        self._upsert_bout(url.rsplit("/", 1)[-1], values, line_no)

    def _upsert_bout(self, external_key: str, values: dict, line_no: int) -> None:
        row_hash = hashlib.sha256(
            json.dumps(values, sort_keys=True, default=str).encode()
        ).hexdigest()
        bout = self._bouts.get(external_key)
        if bout is None:
            bout = Bout(
                source_id=self.source.id,
                external_key=external_key,
                source_row_hash=row_hash,
                first_seen_run_id=self.run.id,
                last_seen_run_id=self.run.id,
                **values,
            )
            self.session.add(bout)
            self._bouts[external_key] = bout
            self.report.bouts_inserted += 1
            return

        bout.last_seen_run_id = self.run.id
        if bout.source_row_hash == row_hash:
            self.report.bouts_unchanged += 1
            return
        if bout.status == "completed" and (
            values["status"] != "completed"
            or (bout.outcome, bout.winner_id, bout.method)
            != (values["outcome"], values["winner_id"], values["method"])
        ):
            # Historical results are immutable; surface the contradiction instead of applying it.
            self.report.add(
                "result_changed",
                {
                    "line": line_no,
                    "bout_id": bout.id,
                    "stored": [bout.outcome, bout.winner_id, bout.method],
                    "incoming": [values["outcome"], values["winner_id"], values["method"]],
                },
            )
            return
        if bout.status == "scheduled" and values["status"] == "completed":
            self.report.results_recorded += 1
        for key, value in values.items():
            setattr(bout, key, value)
        bout.source_row_hash = row_hash
        self.report.bouts_updated += 1

    def _fighter(self, name: str, division: str | None, on: date, url: str) -> Fighter:
        res = self.resolver.resolve(name, division, on)
        if res.ambiguous:
            self.report.add(
                "ambiguous_identity",
                {
                    "name": name,
                    "division": division,
                    "date": on.isoformat(),
                    "fight_url": url,
                    "assigned": res.external_key,
                },
            )
        fighter = self._fighters.get(res.external_key)
        if fighter is None:
            roster = res.roster
            fighter = Fighter(
                display_name=name,
                name_key=n.name_key(name),
                dob=roster.dob if roster else None,
                height_in=roster.height_in if roster else None,
                reach_in=roster.reach_in if roster else None,
                stance=roster.stance if roster else None,
            )
            self.session.add(fighter)
            self.session.flush()
            self.session.add(
                FighterExternalId(
                    fighter_id=fighter.id, source_id=self.source.id, external_key=res.external_key
                )
            )
            self._fighters[res.external_key] = fighter
            self.report.fighters_created += 1
        return fighter

    def _event(self, name: str, on: date, location: str | None) -> Event:
        key = f"{on.isoformat()}|{name}"
        event = self._events.get(key)
        if event is None:
            event = Event(
                source_id=self.source.id,
                external_key=key,
                name=name,
                event_date=on,
                location=location,
            )
            self.session.add(event)
            self.session.flush()
            self._events[key] = event
            self.report.events_created += 1
        return event
