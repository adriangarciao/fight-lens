"""Pure parsing helpers for source rows. Each returns None for unparseable input rather than
guessing; callers record those as missing fields in the ingestion report."""

import re
import unicodedata
from datetime import date, datetime

# Listed weight limit (lbs) per division, used for identity disambiguation.
DIVISION_LIMITS = {
    "Women's Strawweight": 115,
    "Women's Flyweight": 125,
    "Women's Bantamweight": 135,
    "Women's Featherweight": 145,
    "Flyweight": 125,
    "Bantamweight": 135,
    "Featherweight": 145,
    "Lightweight": 155,
    "Welterweight": 170,
    "Middleweight": 185,
    "Light Heavyweight": 205,
    "Heavyweight": 265,
    "Super Heavyweight": 300,
}
_DIVISIONS_LONGEST_FIRST = sorted(DIVISION_LIMITS, key=len, reverse=True)

METHOD_MAP = {
    "Decision - Unanimous": "DEC",
    "Decision - Split": "DEC",
    "Decision - Majority": "DEC",
    "KO/TKO": "KO/TKO",
    "TKO - Doctor's Stoppage": "KO/TKO",
    "Submission": "SUB",
    "DQ": "DQ",
    "Overturned": "OVERTURNED",
    "Could Not Continue": "CNC",
    "Other": "OTHER",
}


def clean(value: object) -> str | None:
    """Strip a raw cell; empty strings and NaN-like markers become None."""
    if value is None:
        return None
    s = str(value).strip()
    return None if s == "" or s.lower() in {"nan", "na", "--", "null"} else s


def name_key(name: str) -> str:
    """Accent-, case- and whitespace-insensitive key for matching fighter names."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_only = ascii_only.replace("’", "'").replace(".", " ")
    return re.sub(r"\s+", " ", ascii_only).strip().lower()


def parse_date(value: str | None) -> date | None:
    value = clean(value)
    if value is None:
        return None
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_time_seconds(value: str | None) -> int | None:
    """Accepts '2:48' (fightr live) or '5M 0S' / '15S' (TidyTuesday)."""
    value = clean(value)
    if value is None:
        return None
    if m := re.fullmatch(r"(\d+):(\d{1,2})", value):
        return int(m[1]) * 60 + int(m[2])
    if m := re.fullmatch(r"(?:(\d+)M)?\s*(?:(\d+)S)?", value):
        if m[1] is None and m[2] is None:
            return None
        return int(m[1] or 0) * 60 + int(m[2] or 0)
    return None


def parse_scheduled_rounds(time_format: str | None) -> int | None:
    """'3 Rnd (5-5-5)' -> 3, '3 Rnd + OT (5-5-5-5)' -> 3. Overtime rounds are not scheduled."""
    time_format = clean(time_format)
    if time_format is None:
        return None
    m = re.match(r"(\d+) Rnd", time_format)
    return int(m[1]) if m else None


def infer_scheduled_rounds(
    time_format: str | None, is_title: bool, event_name: str, name1: str, name2: str
) -> tuple[int | None, str | None]:
    """Scheduled rounds plus where the number came from.

    The source omits time_format for upcoming bouts. UFC rules fill the gap: title fights and
    main events are five rounds, everything else three. The returned source label keeps
    inferred values distinguishable from published ones.
    """
    if (rounds := parse_scheduled_rounds(time_format)) is not None:
        return rounds, "source"
    if is_title:
        return 5, "rule:title"
    headline = name_key(event_name.split(":", 1)[-1])
    surnames = [name_key(name1).split(" ")[-1], name_key(name2).split(" ")[-1]]
    if " vs " in f" {headline} " and all(s in headline.split(" ") for s in surnames):
        return 5, "rule:main_event"
    return 3, "rule:standard"


def parse_method(value: str | None) -> str | None:
    value = clean(value)
    return METHOD_MAP.get(value) if value else None


def parse_division(weight_class: str | None) -> str | None:
    weight_class = clean(weight_class)
    if weight_class is None:
        return None
    for division in _DIVISIONS_LONGEST_FIRST:
        if division in weight_class:
            return division
    if "Catch Weight" in weight_class:
        return "Catch Weight"
    if (
        "Open Weight" in weight_class
        or "Tournament" in weight_class
        or "Superfight" in weight_class
    ):
        return "Open Weight"
    return None


def is_title_bout(weight_class: str | None) -> bool:
    weight_class = clean(weight_class) or ""
    return "Title" in weight_class or "Championship" in weight_class


def parse_outcome(f1_result: str | None, f2_result: str | None) -> tuple[str | None, int | None]:
    """Returns (outcome, winner_position) where winner_position is 1, 2 or None.

    Raises ValueError on contradictory pairs such as W/W so the importer can report them.
    """
    pair = (clean(f1_result), clean(f2_result))
    match pair:
        case (None, None):
            return None, None
        case ("W", "L"):
            return "win", 1
        case ("L", "W"):
            return "win", 2
        case ("D", "D"):
            return "draw", None
        case ("NC", "NC"):
            return "no_contest", None
    raise ValueError(f"contradictory result pair {pair}")


def parse_height_in(value: str | None) -> float | None:
    """'5\\' 11"' -> 71.0. Numeric strings are taken as inches."""
    value = clean(value)
    if value is None:
        return None
    if m := re.fullmatch(r"(\d+)'\s*(\d+)\"?", value):
        return int(m[1]) * 12 + int(m[2])
    return _parse_number(value)


def parse_inches(value: str | None) -> float | None:
    """'74"' -> 74.0"""
    value = clean(value)
    return _parse_number(value.rstrip('"')) if value else None


def parse_lbs(value: str | None) -> float | None:
    """'155 lbs.' -> 155.0"""
    value = clean(value)
    return _parse_number(value.replace("lbs.", "").replace("lbs", "")) if value else None


def _parse_number(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None
