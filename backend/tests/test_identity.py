from datetime import date

from app.ingestion.identity import IdentityResolver, RosterEntry

FLY = RosterEntry("Bruno Silva", 125, date(1990, 3, 16), 64, 65, "Orthodox")
MW = RosterEntry("Bruno Silva", 185, date(1989, 7, 13), 72, 74, "Orthodox")
OLD = RosterEntry("Mike Davis", 155, date(1950, 1, 1), None, None, None)
YOUNG = RosterEntry("Mike Davis", 155, date(1992, 10, 7), None, None, None)


def test_unique_names_resolve_to_plain_key():
    res = IdentityResolver([FLY, MW]).resolve("Alpha Ace", "Lightweight", date(2024, 1, 1))
    assert res.external_key == "alpha ace"
    assert res.roster is None
    assert not res.ambiguous


def test_shared_name_split_by_division_weight():
    resolver = IdentityResolver([FLY, MW])
    fly = resolver.resolve("Bruno Silva", "Flyweight", date(2024, 8, 17))
    mw = resolver.resolve("Bruno Silva", "Middleweight", date(2024, 8, 17))
    assert fly.roster == FLY and mw.roster == MW
    assert fly.external_key != mw.external_key
    assert not fly.ambiguous and not mw.ambiguous


def test_shared_name_uses_age_plausibility_before_weight():
    res = IdentityResolver([OLD, YOUNG]).resolve("Mike Davis", "Lightweight", date(2022, 1, 1))
    assert res.roster == YOUNG
    assert not res.ambiguous


def test_shared_name_without_division_is_flagged():
    res = IdentityResolver([FLY, MW]).resolve("Bruno Silva", "Catch Weight", date(2024, 1, 1))
    assert res.ambiguous
