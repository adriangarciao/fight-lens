from datetime import date

import pytest

from app.ingestion import normalize as n


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-06-27", date(2026, 6, 27)),
        ("October 17, 2026", date(2026, 10, 17)),
        ("Mar 16, 1990", date(1990, 3, 16)),
        ("", None),
        ("--", None),
        ("garbage", None),
    ],
)
def test_parse_date_accepts_both_snapshot_formats(raw, expected):
    assert n.parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2:48", 168),
        ("5:00", 300),
        ("5M 0S", 300),
        ("15S", 15),
        ("1M 31S", 91),
        ("", None),
        ("??", None),
    ],
)
def test_parse_time_seconds(raw, expected):
    assert n.parse_time_seconds(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("3 Rnd (5-5-5)", 3),
        ("5 Rnd (5-5-5-5-5)", 5),
        ("3 Rnd + OT (5-5-5-5)", 3),
        ("1 Rnd + 2OT (15-3-3)", 1),
        ("No Time Limit", None),
    ],
)
def test_parse_scheduled_rounds_ignores_overtime(raw, expected):
    assert n.parse_scheduled_rounds(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Lightweight Bout", "Lightweight"),
        ("Light Heavyweight Bout", "Light Heavyweight"),
        ("UFC Interim Heavyweight Title Bout", "Heavyweight"),
        ("Women's Flyweight Bout", "Women's Flyweight"),
        ("UFC Women's Strawweight Title Bout", "Women's Strawweight"),
        ("Ultimate Fighter 34 Bantamweight Tournament Title Bout", "Bantamweight"),
        ("UFC 4 Tournament Title Bout", "Open Weight"),
        ("Catch Weight Bout", "Catch Weight"),
        ("Super Heavyweight Bout", "Super Heavyweight"),
    ],
)
def test_parse_division_prefers_longest_match(raw, expected):
    assert n.parse_division(raw) == expected


def test_title_detection():
    assert n.is_title_bout("UFC Superfight Championship Bout")
    assert n.is_title_bout("UFC Lightweight Title Bout")
    assert not n.is_title_bout("Lightweight Bout")


def test_method_mapping_groups_doctor_stoppage_with_tko():
    assert n.parse_method("TKO - Doctor's Stoppage") == "KO/TKO"
    assert n.parse_method("Decision - Split") == "DEC"
    assert n.parse_method("Something New") is None


def test_parse_outcome():
    assert n.parse_outcome("W", "L") == ("win", 1)
    assert n.parse_outcome("L", "W") == ("win", 2)
    assert n.parse_outcome("D", "D") == ("draw", None)
    assert n.parse_outcome("NC", "NC") == ("no_contest", None)
    assert n.parse_outcome("", None) == (None, None)
    with pytest.raises(ValueError):
        n.parse_outcome("W", "W")


def test_name_key_is_accent_case_and_punctuation_insensitive():
    assert n.name_key("José  Aldo") == n.name_key("jose aldo")
    assert n.name_key("B.J. Penn") == "b j penn"


def test_physical_parsers():
    assert n.parse_height_in("5' 11\"") == 71
    assert n.parse_inches('74"') == 74
    assert n.parse_lbs("155 lbs.") == 155
    assert n.parse_inches("--") is None


@pytest.mark.parametrize(
    "fmt, title, event, f1, f2, expected",
    [
        ("3 Rnd (5-5-5)", True, "UFC 1: A vs. B", "X A", "Y B", (3, "source")),
        (
            "",
            True,
            "UFC 333: Volkanovski vs. Evloev",
            "Petr Yan",
            "Merab Dvalishvili",
            (5, "rule:title"),
        ),
        (
            "",
            False,
            "UFC 333: Volkanovski vs. Evloev",
            "Alexander Volkanovski",
            "Movsar Evloev",
            (5, "rule:main_event"),
        ),
        (
            "",
            False,
            "UFC 333: Volkanovski vs. Evloev",
            "Aaron Pico",
            "Losene Keita",
            (3, "rule:standard"),
        ),
    ],
)
def test_infer_scheduled_rounds_labels_its_source(fmt, title, event, f1, f2, expected):
    assert n.infer_scheduled_rounds(fmt, title, event, f1, f2) == expected
