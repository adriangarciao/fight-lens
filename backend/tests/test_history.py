"""Time-correctness and symmetry of the comparison layer. These are the Phase 1 leakage guards."""

from datetime import date

from app.db.models import Fighter
from app.services.history import summarize
from app.services.matchups import compare
from tests.conftest import fighter_id

AS_OF = date(2026, 10, 20)


def get(session, name):
    return session.get(Fighter, fighter_id(session, name))


def test_summary_counts_only_bouts_before_as_of(loaded):
    alpha = get(loaded, "Alpha Ace")
    s, records = summarize(loaded, alpha, AS_OF)
    assert (s.record.wins, s.record.losses, s.record.no_contests) == (3, 1, 1)
    assert [r.bout_id for r in records] == sorted([r.bout_id for r in records], reverse=True)

    # Before UFC D (2022-06-04) Alpha had only fought twice.
    early, _ = summarize(loaded, alpha, date(2022, 6, 4))
    assert (early.record.wins, early.record.losses) == (1, 1)
    assert early.coming_off == "L"


def test_scheduled_bouts_never_count(loaded):
    s, _ = summarize(loaded, get(loaded, "Charlie Cole"), date(2100, 1, 1))
    assert s.record.wins + s.record.losses == 2


def test_opponent_record_is_as_of_that_bout(loaded):
    alpha = get(loaded, "Alpha Ace")
    _, records = summarize(loaded, alpha, AS_OF)
    by_event = {r.event.name: r for r in records}
    # Bravo was 1-0 before UFC C, and 2-0-1 before UFC F; later results must not leak in.
    assert by_event["UFC C"].opponent_record_before.model_dump() == {
        "wins": 1,
        "losses": 0,
        "draws": 0,
        "no_contests": 0,
    }
    assert by_event["UFC F"].opponent_record_before.model_dump() == {
        "wins": 2,
        "losses": 0,
        "draws": 1,
        "no_contests": 0,
    }


def test_streak_skips_no_contest_and_activity(loaded):
    s, _ = summarize(loaded, get(loaded, "Alpha Ace"), AS_OF)
    assert (s.streak.kind, s.streak.count) == ("W", 2)  # W (UFC F), NC skipped, W (UFC D)
    assert s.activity.days_since_last_fight == (AS_OF - date(2024, 8, 17)).days
    assert s.activity.layoff_flag == "long_layoff"
    assert s.activity.fights_last_12_months == 0
    assert s.latest_division == "Welterweight"


def test_debut_and_limited_data(loaded):
    s, _ = summarize(loaded, get(loaded, "Echo Eve"), date(2023, 1, 1))
    assert s.activity.layoff_flag == "debut"
    assert s.streak.kind == "none"
    assert any("debut" in m for m in s.limited_data)
    charlie, _ = summarize(loaded, get(loaded, "Charlie Cole"), AS_OF)
    assert any("Reach unavailable" in m for m in charlie.limited_data)
    assert charlie.physical.age_years is None


def test_head_to_head_with_division_change(loaded):
    a, b = get(loaded, "Alpha Ace"), get(loaded, "Bravo Bell")
    m = compare(loaded, a, b, AS_OF)
    assert [x.event.name for x in m.head_to_head] == ["UFC F", "UFC C"]
    first = m.head_to_head[1]
    assert first.winner.id == b.id
    assert first.division_changes[a.id] == ["Welterweight"]
    assert first.fights_since[a.id] == 3


def test_common_opponents_and_limits(loaded):
    a, b = get(loaded, "Alpha Ace"), get(loaded, "Bravo Bell")
    m = compare(loaded, a, b, AS_OF)
    names = {c.opponent.name for c in m.common_opponents}
    assert names == {"Charlie Cole", "Delta Dunn"}
    charlie = next(c for c in m.common_opponents if c.opponent.name == "Charlie Cole")
    assert charlie.fighter_a.fights[0].result == "W" and charlie.fighter_b.fights[0].result == "W"
    assert any("2019" in note for note in charlie.limited_comparison)
    delta = next(c for c in m.common_opponents if c.opponent.name == "Delta Dunn")
    assert any("different divisions" in note for note in delta.limited_comparison)


def test_compare_is_symmetric_in_fighter_order(loaded):
    a, b = get(loaded, "Alpha Ace"), get(loaded, "Bravo Bell")
    ab, ba = compare(loaded, a, b, AS_OF), compare(loaded, b, a, AS_OF)
    assert ab.fighter_a == ba.fighter_b and ab.fighter_b == ba.fighter_a
    assert [x.bout_id for x in ab.head_to_head] == [x.bout_id for x in ba.head_to_head]
    assert {c.opponent.id for c in ab.common_opponents} == {
        c.opponent.id for c in ba.common_opponents
    }


def test_compare_for_past_date_hides_later_meeting(loaded):
    a, b = get(loaded, "Alpha Ace"), get(loaded, "Bravo Bell")
    m = compare(loaded, a, b, date(2024, 8, 17))  # the day of their rematch
    assert [x.event.name for x in m.head_to_head] == ["UFC C"]
