from sqlalchemy import func, select

from app.db.models import Bout, Event, Fighter
from app.ingestion.fightr import import_snapshot
from tests.conftest import bout, default_bouts, fighter_id, write_snapshot


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_import_counts_and_statuses(session, snapshot):
    report = import_snapshot(session, snapshot)
    assert report.bouts_inserted == 10
    assert count(session, Event) == 7
    # Two different Bruno Silvas must not merge.
    assert session.scalar(select(func.count()).where(Fighter.display_name == "Bruno Silva")) == 2
    assert session.scalar(select(func.count()).where(Bout.status == "scheduled")) == 1
    assert report.issues == {}


def test_bout_fields_are_normalized(loaded):
    b = loaded.scalar(select(Bout).where(Bout.external_key == "b07"))
    assert (b.status, b.outcome, b.method, b.end_round, b.end_time_seconds) == (
        "completed",
        "win",
        "KO/TKO",
        2,
        65,
    )
    assert b.winner_id == fighter_id(loaded, "Alpha Ace")
    scheduled = loaded.scalar(select(Bout).where(Bout.external_key == "b10"))
    assert (scheduled.scheduled_rounds, scheduled.is_title_bout, scheduled.winner_id) == (
        5,
        True,
        None,
    )


def test_physical_attributes_attach_but_missing_stays_missing(loaded):
    alpha = loaded.get(Fighter, fighter_id(loaded, "Alpha Ace"))
    assert (alpha.height_in, alpha.reach_in, alpha.stance) == (70, 72, "Orthodox")
    charlie = loaded.get(Fighter, fighter_id(loaded, "Charlie Cole"))
    assert charlie.reach_in is None and charlie.dob is None
    echo = loaded.get(Fighter, fighter_id(loaded, "Echo Eve"))  # not on roster at all
    assert echo.height_in is None


def test_reimport_is_idempotent(loaded, snapshot):
    before = (count(loaded, Bout), count(loaded, Fighter), count(loaded, Event))
    report = import_snapshot(loaded, snapshot)
    assert (report.bouts_inserted, report.bouts_updated, report.bouts_unchanged) == (0, 0, 10)
    assert (count(loaded, Bout), count(loaded, Fighter), count(loaded, Event)) == before


def test_scheduled_bout_becomes_result(loaded, tmp_path):
    rows = default_bouts()
    rows[-1] = bout(
        "b10",
        "UFC 999",
        "January 01, 2099",
        "Alpha Ace",
        "W",
        "Charlie Cole",
        "L",
        "UFC Welterweight Title Bout",
        "Submission",
        "4",
        "1:00",
        fmt="5 Rnd (5-5-5-5-5)",
    )
    report = import_snapshot(loaded, write_snapshot(tmp_path / "next", rows))
    assert report.results_recorded == 1
    b = loaded.scalar(select(Bout).where(Bout.external_key == "b10"))
    assert (b.status, b.method, b.winner_id) == (
        "completed",
        "SUB",
        fighter_id(loaded, "Alpha Ace"),
    )


def test_completed_result_is_immutable_and_reported(loaded, tmp_path):
    rows = default_bouts()
    rows[0] = {**rows[0], "f1_result": "L", "f2_result": "W"}
    report = import_snapshot(loaded, write_snapshot(tmp_path / "next", rows))
    assert len(report.issues["result_changed"]) == 1
    b = loaded.scalar(select(Bout).where(Bout.external_key == "b01"))
    assert b.winner_id == fighter_id(loaded, "Alpha Ace")


def test_bad_rows_are_reported_not_imported(session, tmp_path):
    rows = default_bouts() + [
        bout(
            "x1",
            "UFC Z",
            "March 01, 2025",
            "Alpha Ace",
            "W",
            "Bravo Bell",
            "W",
            "Lightweight Bout",
            "KO/TKO",
            "1",
            "1:00",
        ),
        bout(
            "x2",
            "UFC Z",
            "",
            "Alpha Ace",
            "W",
            "Bravo Bell",
            "L",
            "Lightweight Bout",
            "KO/TKO",
            "1",
            "1:00",
        ),
        bout(
            "x3",
            "UFC F",
            "August 17, 2024",
            "Bravo Bell",
            "W",
            "Alpha Ace",
            "L",
            "Welterweight Bout",
            "KO/TKO",
            "1",
            "1:00",
        ),
    ]
    report = import_snapshot(session, write_snapshot(tmp_path / "s", rows))
    assert len(report.issues["contradictory_result"]) == 1
    assert len(report.issues["missing_required_field"]) == 1
    assert len(report.issues["duplicate_pairing"]) == 1
