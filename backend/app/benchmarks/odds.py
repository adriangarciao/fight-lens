"""Import historical bookmaker odds (the "Ultimate UFC Dataset" via fightr/TidyTuesday) and
attach them to bouts for benchmarking only.

Rows are matched to bouts by date (±1 day for timezone differences) and fighter names. A row is
skipped, and reported, when no unique bout matches or when its recorded winner disagrees with
the bout's result, since a mis-joined benchmark would be worse than none.
"""

import csv
import difflib
import hashlib
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import BenchmarkOdds, Bout
from app.ingestion.normalize import clean, name_key, parse_date

SOURCE_KEY = "ultimate_ufc_dataset"
FUZZY_MIN_RATIO = 0.85


@dataclass
class OddsImportReport:
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    fuzzy_matches: int = 0
    issues: dict[str, list] = field(default_factory=dict)

    def add(self, kind: str, detail: object) -> None:
        self.issues.setdefault(kind, []).append(detail)

    def stats(self) -> dict:
        return {
            "rows": self.rows,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "removed": self.removed,
            "fuzzy_matches": self.fuzzy_matches,
            "issue_counts": {k: len(v) for k, v in self.issues.items()},
        }


def _num(value: str | None) -> float | None:
    value = clean(value)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def import_odds(session: Session, path: Path) -> OddsImportReport:
    report = OddsImportReport()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    bouts = session.scalars(
        select(Bout)
        .options(joinedload(Bout.event), joinedload(Bout.fighter1), joinedload(Bout.fighter2))
        .where(Bout.status == "completed")
    ).all()
    by_date: dict = {}
    for b in bouts:
        by_date.setdefault(b.event.event_date, []).append(b)
    existing = {
        o.bout_id: o
        for o in session.scalars(
            select(BenchmarkOdds).where(BenchmarkOdds.source_key == SOURCE_KEY)
        )
    }
    claimed: set[int] = set()

    with open(path, newline="", encoding="utf-8") as fh:
        for line_no, raw in enumerate(csv.DictReader(fh), start=2):
            row = {k.strip().lower(): v for k, v in raw.items()}
            report.rows += 1
            red, blue = clean(row.get("r_fighter")), clean(row.get("b_fighter"))
            on = parse_date(row.get("date"))
            ml_red, ml_blue = _num(row.get("r_odds")), _num(row.get("b_odds"))
            if not (red and blue and on):
                report.add("missing_required_field", {"line": line_no})
                continue
            if ml_red is None or ml_blue is None:
                report.add("no_moneyline", {"line": line_no})
                continue

            match = _match(by_date, on, red, blue)
            if match is None:
                report.add(
                    "unmatched", {"line": line_no, "date": on.isoformat(), "red": red, "blue": blue}
                )
                continue
            bout, red_is_f1, method = match
            if bout.id in claimed:
                report.add("duplicate_match", {"line": line_no, "bout_id": bout.id})
                continue

            winner = clean(row.get("winner"))
            if bout.outcome == "win" and winner in ("Red", "Blue"):
                red_won = bout.winner_id == (bout.fighter1_id if red_is_f1 else bout.fighter2_id)
                if red_won != (winner == "Red"):
                    report.add("winner_mismatch", {"line": line_no, "bout_id": bout.id})
                    continue
            claimed.add(bout.id)
            if method == "fuzzy":
                report.fuzzy_matches += 1
                report.add(
                    "fuzzy_match", {"line": line_no, "bout_id": bout.id, "red": red, "blue": blue}
                )

            side = {
                "red": {k: _num(row.get(f"r_{k}_odds")) for k in ("ko", "sub", "dec")},
                "blue": {k: _num(row.get(f"b_{k}_odds")) for k in ("ko", "sub", "dec")},
            }
            s1, s2 = ("red", "blue") if red_is_f1 else ("blue", "red")
            values = {
                "source_sha256": sha,
                "match_method": method,
                "f1_moneyline": ml_red if red_is_f1 else ml_blue,
                "f2_moneyline": ml_blue if red_is_f1 else ml_red,
                **{f"f1_{k}": v for k, v in side[s1].items()},
                **{f"f2_{k}": v for k, v in side[s2].items()},
            }
            odds = existing.get(bout.id)
            if odds is None:
                session.add(BenchmarkOdds(bout_id=bout.id, source_key=SOURCE_KEY, **values))
                report.inserted += 1
            elif any(getattr(odds, k) != v for k, v in values.items() if k != "source_sha256"):
                for k, v in values.items():
                    setattr(odds, k, v)
                report.updated += 1
            else:
                report.unchanged += 1
    # Odds are a derived benchmark, not history: drop matches this source no longer supports.
    for bout_id, odds in existing.items():
        if bout_id not in claimed:
            session.delete(odds)
            report.removed += 1
    session.commit()
    return report


def _similarity(a: str, b: str) -> float:
    """Best of plain and token-sorted similarity: handles both "Kara France" vs "Kara-France"
    and reordered names such as "Ning Guangyou" vs "Guangyou Ning"."""
    plain = difflib.SequenceMatcher(None, a, b).ratio()
    tokens = difflib.SequenceMatcher(
        None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))
    ).ratio()
    return max(plain, tokens)


def _match(by_date: dict, on, red: str, blue: str):
    """Returns (bout, red_is_fighter1, "exact"|"fuzzy") or None."""
    rk, bk = name_key(red), name_key(blue)
    candidates = [
        b for d in (on, on - timedelta(days=1), on + timedelta(days=1)) for b in by_date.get(d, [])
    ]
    exact = [
        b
        for b in candidates
        if {name_key(b.fighter1.display_name), name_key(b.fighter2.display_name)} == {rk, bk}
    ]
    if len(exact) == 1:
        b = exact[0]
        return b, name_key(b.fighter1.display_name) == rk, "exact"
    if exact:
        return None

    fuzzy = []
    for b in candidates:
        k1, k2 = name_key(b.fighter1.display_name), name_key(b.fighter2.display_name)
        for red_is_f1, (red_target, blue_target) in ((True, (k1, k2)), (False, (k2, k1))):
            r_ratio, b_ratio = _similarity(rk, red_target), _similarity(bk, blue_target)
            # One name must match exactly; the other only closely (spelling variants).
            if max(r_ratio, b_ratio) == 1.0 and min(r_ratio, b_ratio) >= FUZZY_MIN_RATIO:
                fuzzy.append((b, red_is_f1))
    if len(fuzzy) == 1:
        return fuzzy[0][0], fuzzy[0][1], "fuzzy"
    return None
