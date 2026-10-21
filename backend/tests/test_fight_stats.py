import csv
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import FighterBoutStats
from app.ingestion.fight_stats import import_fight_stats
from tests.conftest import fighter_id

STAT_COLUMNS = [
    "EVENT",
    "BOUT",
    "ROUND",
    "FIGHTER",
    "KD",
    "SIG.STR.",
    "SIG.STR. %",
    "TOTAL STR.",
    "TD",
    "TD %",
    "SUB.ATT",
    "REV.",
    "CTRL",
    "HEAD",
    "BODY",
    "LEG",
    "DISTANCE",
    "CLINCH",
    "GROUND",
]


def stat_row(event, bout, rnd, fighter, sig="10 of 20", td="1 of 2", kd="0.0", ctrl="1:30"):
    return {
        "EVENT": event,
        "BOUT": bout,
        "ROUND": f"Round {rnd}",
        "FIGHTER": fighter,
        "KD": kd,
        "SIG.STR.": sig,
        "SIG.STR. %": "50%",
        "TOTAL STR.": sig,
        "TD": td,
        "TD %": "50%",
        "SUB.ATT": "0.0",
        "REV.": "0.0",
        "CTRL": ctrl,
        "HEAD": "6 of 14",
        "BODY": "2 of 3",
        "LEG": "2 of 3",
        "DISTANCE": "7 of 15",
        "CLINCH": "2 of 3",
        "GROUND": "1 of 2",
    }


def write(directory: Path, details: list[tuple[str, str, str]], stats: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "ufc_fight_details.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["EVENT", "BOUT", "URL"])
        for event, bout, key in details:
            w.writerow([event, bout, f"http://ufcstats.com/fight-details/{key}"])
    with open(directory / "ufc_fight_stats.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, STAT_COLUMNS)
        w.writeheader()
        w.writerows(stats)
    return directory


def test_import_joins_by_fight_url_and_assigns_sides(loaded, tmp_path):
    details = [
        ("UFC F", "Alpha Ace vs. Bravo Bell", "b07"),
        ("UFC F Renamed", "Alpha Ace vs. Bravo Bell", "b07"),  # same fight, renamed event
        ("UFC C", "Bravo Bell vs. Alpha Ace", "b03"),
    ]
    stats = [
        stat_row("UFC F", "Alpha Ace vs. Bravo Bell", 1, "Alpha Ace", sig="20 of 40", kd="1.0"),
        stat_row("UFC F", "Alpha Ace vs. Bravo Bell", 1, "Bravo Bell", sig="5 of 30"),
        stat_row("UFC F", "Alpha Ace vs. Bravo Bell", 2, "Alpha Ace"),
        stat_row("UFC F", "Alpha Ace vs. Bravo Bell", 2, "Bravo Bel"),  # misspelt -> similarity
        stat_row(
            "UFC F Renamed", "Alpha Ace vs. Bravo Bell", 1, "Alpha Ace", sig="20 of 40", kd="1.0"
        ),
        stat_row("UFC C", "Bravo Bell vs. Alpha Ace", 1, "Somebody Else"),  # unassignable
        stat_row("UFC Z", "Nobody vs. Noone", 1, "Nobody"),  # no fight URL
    ]
    report = import_fight_stats(loaded, write(tmp_path / "s", details, stats))
    assert report.inserted == 4
    assert {k: len(v) for k, v in report.issues.items()} == {
        "duplicate_row": 1,
        "fighter_unassigned": 1,
        "no_fight_url": 1,
    }
    alpha = fighter_id(loaded, "Alpha Ace")
    r1 = loaded.scalar(
        select(FighterBoutStats).where(
            FighterBoutStats.fighter_id == alpha, FighterBoutStats.round == 1
        )
    )
    assert (r1.sig_landed, r1.sig_attempted, r1.kd, r1.ctrl_seconds) == (20, 40, 1, 90)

    again = import_fight_stats(loaded, write(tmp_path / "s", details, stats))
    assert (again.inserted, again.unchanged) == (0, 4)
    assert loaded.scalar(select(func.count()).select_from(FighterBoutStats)) == 4


def test_tale_of_the_tape_includes_raw_style(client, loaded, tmp_path):
    details = [("UFC F", "Alpha Ace vs. Bravo Bell", "b07")]
    stats = [
        stat_row(
            "UFC F",
            "Alpha Ace vs. Bravo Bell",
            1,
            "Alpha Ace",
            sig="20 of 40",
            td="2 of 4",
            ctrl="1:00",
        ),
        stat_row("UFC F", "Alpha Ace vs. Bravo Bell", 1, "Bravo Bell", sig="5 of 25", td="0 of 3"),
        stat_row(
            "UFC F",
            "Alpha Ace vs. Bravo Bell",
            2,
            "Alpha Ace",
            sig="4 of 10",
            td="0 of 0",
            ctrl="0:05",
        ),
        stat_row("UFC F", "Alpha Ace vs. Bravo Bell", 2, "Bravo Bell", sig="1 of 5", td="0 of 0"),
    ]
    import_fight_stats(loaded, write(tmp_path / "s", details, stats))
    a, b = fighter_id(loaded, "Alpha Ace"), fighter_id(loaded, "Bravo Bell")
    body = client.get(
        "/api/matchups", params={"fighterA": a, "fighterB": b, "asOf": "2026-10-20"}
    ).json()
    career = body["fighter_a"]["style"]["career"]
    # b07 ended in round 2 at 1:05 of a 3 x 5-minute format.
    minutes = (300 + 65) / 60
    assert career["fights"] == 1 and career["minutes"] == round(minutes, 1)
    assert career["slpm"] == 24 / minutes and career["str_acc"] == 24 / 50
    assert career["str_def"] == 1 - 6 / 30 and career["td_def"] == 1 - 0 / 3
    # Before UFC F there were no stats at all.
    early = client.get(
        "/api/matchups", params={"fighterA": a, "fighterB": b, "asOf": "2024-08-17"}
    ).json()
    assert early["fighter_a"]["style"]["career"] is None
