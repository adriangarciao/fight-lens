"""Import per-round fight statistics (UFCStats data published by Greco1899/scrape_ufc_stats).

Rows join to bouts through the UFCStats fight-details URL, the same key our bouts use, so the
join is exact. A fighter row is assigned to a bout side by name; rows that can't be assigned
unambiguously are skipped and reported rather than guessed.
"""

import csv
import hashlib
import shutil
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Bout, FighterBoutStats
from app.ingestion.normalize import (
    clean,
    name_key,
    name_similarity,
    parse_int,
    parse_of,
    parse_time_seconds,
)

SOURCE_KEY = "ufcstats-greco"
RAW_BASE_URL = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main"
FILES = ("ufc_fight_stats.csv", "ufc_fight_details.csv")
NAME_MIN_SIMILARITY = 0.8


def fetch_stats_snapshot(data_dir: Path, today: date | None = None) -> Path:
    target = data_dir / "raw" / f"{SOURCE_KEY}-{(today or date.today()).isoformat()}"
    target.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        with urllib.request.urlopen(f"{RAW_BASE_URL}/{name}", timeout=120) as resp:
            with open(target / name, "wb") as out:
                shutil.copyfileobj(resp, out)
    return target


def latest_stats_snapshot(data_dir: Path) -> Path | None:
    snapshots = sorted((data_dir / "raw").glob(f"{SOURCE_KEY}-*"))
    return snapshots[-1] if snapshots else None


@dataclass
class StatsImportReport:
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    bouts_with_stats: int = 0
    issues: dict[str, list] = field(default_factory=dict)

    def add(self, kind: str, detail: object) -> None:
        self.issues.setdefault(kind, []).append(detail)

    def stats(self) -> dict:
        return {
            "rows": self.rows,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "bouts_with_stats": self.bouts_with_stats,
            "issue_counts": {k: len(v) for k, v in self.issues.items()},
        }


STAT_FIELDS = (
    "kd",
    "sig_landed",
    "sig_attempted",
    "total_landed",
    "total_attempted",
    "td_landed",
    "td_attempted",
    "sub_attempts",
    "reversals",
    "ctrl_seconds",
    "head_landed",
    "body_landed",
    "leg_landed",
    "distance_landed",
    "clinch_landed",
    "ground_landed",
)


def _parse_row(row: dict) -> dict | None:
    sig, tot, td = (
        parse_of(row.get("SIG.STR.")),
        parse_of(row.get("TOTAL STR.")),
        parse_of(row.get("TD")),
    )
    head, body, leg = parse_of(row.get("HEAD")), parse_of(row.get("BODY")), parse_of(row.get("LEG"))
    dist, clinch, ground = (
        parse_of(row.get("DISTANCE")),
        parse_of(row.get("CLINCH")),
        parse_of(row.get("GROUND")),
    )
    kd, sub, rev = (
        parse_int(row.get("KD")),
        parse_int(row.get("SUB.ATT")),
        parse_int(row.get("REV.")),
    )
    required = (sig, tot, td, head, body, leg, dist, clinch, ground, kd, sub, rev)
    if any(v is None for v in required):
        return None
    return {
        "kd": kd,
        "sig_landed": sig[0],
        "sig_attempted": sig[1],
        "total_landed": tot[0],
        "total_attempted": tot[1],
        "td_landed": td[0],
        "td_attempted": td[1],
        "sub_attempts": sub,
        "reversals": rev,
        "ctrl_seconds": parse_time_seconds(row.get("CTRL")),
        "head_landed": head[0],
        "body_landed": body[0],
        "leg_landed": leg[0],
        "distance_landed": dist[0],
        "clinch_landed": clinch[0],
        "ground_landed": ground[0],
    }


def import_fight_stats(session: Session, snapshot_dir: Path) -> StatsImportReport:
    report = StatsImportReport()
    stats_path = snapshot_dir / "ufc_fight_stats.csv"
    sha = hashlib.sha256(stats_path.read_bytes()).hexdigest()

    # (event, bout) -> fight-details key; duplicate pairs (two bouts, same names, same night)
    # are ambiguous and skipped.
    url_for: dict[tuple[str, str], str | None] = {}
    with open(snapshot_dir / "ufc_fight_details.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (clean(row["EVENT"]) or "", clean(row["BOUT"]) or "")
            ext = (clean(row["URL"]) or "").rsplit("/", 1)[-1]
            url_for[key] = None if key in url_for else ext

    bouts = {
        b.external_key: b
        for b in session.scalars(
            select(Bout)
            .options(joinedload(Bout.fighter1), joinedload(Bout.fighter2))
            .where(Bout.status == "completed")
        )
    }
    existing = {
        (s.bout_id, s.fighter_id, s.round): s for s in session.scalars(select(FighterBoutStats))
    }
    side_cache: dict[tuple[int, str], int | None] = {}
    seen_bouts: set[int] = set()
    # The same fight can appear under two event names (renamed events share a fight URL).
    seen_rows: dict[tuple[int, int, int], dict] = {}

    with open(stats_path, newline="", encoding="utf-8") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            report.rows += 1
            key = (clean(row.get("EVENT")) or "", clean(row.get("BOUT")) or "")
            if key not in url_for:
                report.add("no_fight_url", {"line": line_no, "event": key[0], "bout": key[1]})
                continue
            ext = url_for[key]
            if ext is None:
                report.add("ambiguous_bout", {"line": line_no, "event": key[0], "bout": key[1]})
                continue
            bout = bouts.get(ext)
            if bout is None:
                report.add("bout_not_found", {"line": line_no, "fight_key": ext})
                continue
            rnd_text = clean(row.get("ROUND")) or ""
            if not rnd_text.startswith("Round "):
                report.add("missing_round", {"line": line_no, "bout_id": bout.id})
                continue
            values = _parse_row(row)
            if values is None:
                report.add("unparseable_stats", {"line": line_no, "bout_id": bout.id})
                continue
            fighter_name = clean(row.get("FIGHTER")) or ""
            fighter_id = _side(side_cache, bout, fighter_name)
            if fighter_id is None:
                report.add(
                    "fighter_unassigned",
                    {"line": line_no, "bout_id": bout.id, "fighter": fighter_name},
                )
                continue

            seen_bouts.add(bout.id)
            rnd = int(rnd_text.split()[1])
            row_key = (bout.id, fighter_id, rnd)
            if row_key in seen_rows:
                kind = "duplicate_row" if seen_rows[row_key] == values else "conflicting_duplicate"
                report.add(kind, {"line": line_no, "bout_id": bout.id, "round": rnd})
                continue
            seen_rows[row_key] = values
            stat = existing.get(row_key)
            if stat is None:
                session.add(
                    FighterBoutStats(
                        bout_id=bout.id,
                        fighter_id=fighter_id,
                        round=rnd,
                        source_sha256=sha,
                        **values,
                    )
                )
                report.inserted += 1
            elif any(getattr(stat, k) != v for k, v in values.items()):
                for k, v in values.items():
                    setattr(stat, k, v)
                stat.source_sha256 = sha
                report.updated += 1
            else:
                report.unchanged += 1
    report.bouts_with_stats = len(seen_bouts)
    session.commit()
    return report


def _side(cache: dict, bout: Bout, fighter_name: str) -> int | None:
    """Which of the bout's fighters this row belongs to; None if unclear."""
    key = (bout.id, fighter_name)
    if key not in cache:
        target = name_key(fighter_name)
        k1, k2 = name_key(bout.fighter1.display_name), name_key(bout.fighter2.display_name)
        if target in (k1, k2) and k1 != k2:
            cache[key] = bout.fighter1_id if target == k1 else bout.fighter2_id
        else:
            s1, s2 = name_similarity(target, k1), name_similarity(target, k2)
            best = max(s1, s2)
            cache[key] = (
                (bout.fighter1_id if s1 > s2 else bout.fighter2_id)
                if best >= NAME_MIN_SIMILARITY and s1 != s2
                else None
            )
    return cache[key]
