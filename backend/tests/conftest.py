import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.ingestion.fightr import import_snapshot
from app.main import app

FIGHT_COLUMNS = [
    "fight_url",
    "event_name",
    "date",
    "location",
    "f1_name",
    "f1_result",
    "f2_name",
    "f2_result",
    "weight_class",
    "method",
    "round",
    "time",
    "time_format",
    "referee",
    "judging_details",
]
ROSTER_COLUMNS = [
    "Name",
    "Wins",
    "Losses",
    "Draws",
    "NC",
    "Height",
    "Weight",
    "Reach",
    "STANCE",
    "DOB",
]


def bout(
    key, event, date, f1, r1, f2, r2, weight_class, method="", rnd="", time="", fmt="3 Rnd (5-5-5)"
):
    return {
        "fight_url": f"http://www.ufcstats.com/fight-details/{key}",
        "event_name": event,
        "date": date,
        "location": "Las Vegas, Nevada, USA",
        "f1_name": f1,
        "f1_result": r1,
        "f2_name": f2,
        "f2_result": r2,
        "weight_class": weight_class,
        "method": method,
        "round": rnd,
        "time": time,
        "time_format": fmt,
        "referee": "Herb Dean" if r1 else "",
        "judging_details": "",
    }


def default_bouts() -> list[dict]:
    return [
        bout(
            "b01",
            "UFC A",
            "March 02, 2019",
            "Alpha Ace",
            "W",
            "Charlie Cole",
            "L",
            "Lightweight Bout",
            "KO/TKO",
            "1",
            "2:30",
        ),
        bout(
            "b02",
            "UFC B",
            "May 09, 2020",
            "Bravo Bell",
            "W",
            "Charlie Cole",
            "L",
            "Lightweight Bout",
            "Decision - Unanimous",
            "3",
            "5:00",
        ),
        bout(
            "b03",
            "UFC C",
            "January 16, 2021",
            "Bravo Bell",
            "W",
            "Alpha Ace",
            "L",
            "Lightweight Bout",
            "Submission",
            "2",
            "3:10",
        ),
        bout(
            "b04",
            "UFC D",
            "June 04, 2022",
            "Alpha Ace",
            "W",
            "Delta Dunn",
            "L",
            "Welterweight Bout",
            "Decision - Split",
            "3",
            "5:00",
        ),
        bout(
            "b05",
            "UFC E",
            "February 11, 2023",
            "Alpha Ace",
            "NC",
            "Echo Eve",
            "NC",
            "Welterweight Bout",
            "Overturned",
            "1",
            "4:00",
        ),
        bout(
            "b06",
            "UFC E",
            "February 11, 2023",
            "Bravo Bell",
            "D",
            "Delta Dunn",
            "D",
            "Lightweight Bout",
            "Decision - Majority",
            "3",
            "5:00",
        ),
        bout(
            "b07",
            "UFC F",
            "August 17, 2024",
            "Alpha Ace",
            "W",
            "Bravo Bell",
            "L",
            "Welterweight Bout",
            "KO/TKO",
            "2",
            "1:05",
        ),
        bout(
            "b08",
            "UFC F",
            "August 17, 2024",
            "Bruno Silva",
            "W",
            "Foxtrot Fox",
            "L",
            "Flyweight Bout",
            "Submission",
            "1",
            "3:00",
        ),
        bout(
            "b09",
            "UFC F",
            "August 17, 2024",
            "Golf Gray",
            "W",
            "Bruno Silva",
            "L",
            "Middleweight Bout",
            "KO/TKO",
            "1",
            "0:45",
        ),
        bout(
            "b10",
            "UFC 999",
            "January 01, 2099",
            "Alpha Ace",
            "",
            "Charlie Cole",
            "",
            "UFC Welterweight Title Bout",
            fmt="5 Rnd (5-5-5-5-5)",
        ),
    ]


def default_roster() -> list[dict]:
    def r(name, height, weight, reach, stance, dob):
        return {
            "Name": name,
            "Wins": "0",
            "Losses": "0",
            "Draws": "0",
            "NC": "0",
            "Height": height,
            "Weight": weight,
            "Reach": reach,
            "STANCE": stance,
            "DOB": dob,
        }

    return [
        r("Alpha Ace", "5' 10\"", "155 lbs.", '72"', "Orthodox", "Jan 01, 1990"),
        r("Bravo Bell", "5' 9\"", "155 lbs.", '70"', "Southpaw", "Feb 02, 1992"),
        r("Charlie Cole", "5' 8\"", "155 lbs.", "--", "", "--"),
        r("Bruno Silva", "5' 4\"", "125 lbs.", '65"', "Orthodox", "Mar 16, 1990"),
        r("Bruno Silva", "6' 0\"", "185 lbs.", '74"', "Orthodox", "Jul 13, 1989"),
    ]


def write_snapshot(directory: Path, bouts: list[dict], roster: list[dict] | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "ufc_fights.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, FIGHT_COLUMNS)
        writer.writeheader()
        writer.writerows(bouts)
    with open(directory / "ufcstats_data.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, ROSTER_COLUMNS)
        writer.writeheader()
        writer.writerows(default_roster() if roster is None else roster)
    return directory


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def snapshot(tmp_path) -> Path:
    return write_snapshot(tmp_path / "fightr-2026-10-20", default_bouts())


@pytest.fixture
def loaded(session: Session, snapshot: Path) -> Session:
    import_snapshot(session, snapshot)
    return session


@pytest.fixture
def client(engine, loaded):
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def fighter_id(session: Session, name: str) -> int:
    from sqlalchemy import select

    from app.db.models import Fighter

    ids = session.scalars(select(Fighter.id).where(Fighter.display_name == name)).all()
    assert len(ids) == 1, f"{name!r} matched {len(ids)} fighters"
    return ids[0]
