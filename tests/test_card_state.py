"""Pure-logic tests for card_state.py: state classification, countdown
formatting, chip/criteria filtering, sorting, and flag consensus.

Meta dicts are built by hand (plain dicts) — no collection needed for
any of these, they operate purely on the queue/type/due/... fields.
"""
from __future__ import annotations

from anki.consts import (
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_LRN,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_DAY_LEARN_RELEARN,
    QUEUE_TYPE_SUSPENDED,
    QUEUE_TYPE_MANUALLY_BURIED,
    QUEUE_TYPE_SIBLING_BURIED,
    CARD_TYPE_NEW,
    CARD_TYPE_LRN,
    CARD_TYPE_REV,
    CARD_TYPE_RELEARNING,
)

from conftest import addon_module

card_state = addon_module("core.card_state")

TODAY = 100


def _meta(queue, type_, due, factor=2500, ivl=10, lapses=0, reps=3, mod=0, sfld="card", flags=0):
    return {
        "queue": queue,
        "type": type_,
        "due": due,
        "factor": factor,
        "ivl": ivl,
        "lapses": lapses,
        "reps": reps,
        "mod": mod,
        "sfld": sfld,
        "flags": flags,
    }


# ── card_state_from_meta ──


def test_state_new():
    m = _meta(QUEUE_TYPE_NEW, CARD_TYPE_NEW, 5)
    assert card_state.card_state_from_meta(m, TODAY) == "new"


def test_state_learn_via_queue():
    m = _meta(QUEUE_TYPE_LRN, CARD_TYPE_LRN, TODAY + 1)
    assert card_state.card_state_from_meta(m, TODAY) == "learn"


def test_state_learn_via_day_learn_relearn_queue():
    m = _meta(QUEUE_TYPE_DAY_LEARN_RELEARN, CARD_TYPE_RELEARNING, TODAY + 1)
    assert card_state.card_state_from_meta(m, TODAY) == "learn"


def test_state_review_due_boundary_today():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY)
    assert card_state.card_state_from_meta(m, TODAY) == "review-due"


def test_state_review_due_overdue():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY - 5)
    assert card_state.card_state_from_meta(m, TODAY) == "review-due"


def test_state_review_soon_boundaries():
    for days in (1, 3):
        m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + days)
        assert card_state.card_state_from_meta(m, TODAY) == "review-soon", days


def test_state_review_mid_boundaries():
    for days in (4, 14):
        m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + days)
        assert card_state.card_state_from_meta(m, TODAY) == "review-mid", days


def test_state_review_later_boundary():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 15)
    assert card_state.card_state_from_meta(m, TODAY) == "review-later"
    m2 = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 1000)
    assert card_state.card_state_from_meta(m2, TODAY) == "review-later"


def test_state_suspended_is_blank():
    m = _meta(QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV, TODAY)
    assert card_state.card_state_from_meta(m, TODAY) == ""


def test_state_buried_is_blank():
    for q in (QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED):
        m = _meta(q, CARD_TYPE_REV, TODAY)
        assert card_state.card_state_from_meta(m, TODAY) == ""


# ── card_countdown_from_meta ──


def test_countdown_due_for_overdue_and_today():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY - 3)
    assert card_state.card_countdown_from_meta(m, TODAY) == "Due"
    m2 = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY)
    assert card_state.card_countdown_from_meta(m2, TODAY) == "Due"


def test_countdown_one_day():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 1)
    assert card_state.card_countdown_from_meta(m, TODAY) == "1 day"


def test_countdown_n_days():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 29)
    assert card_state.card_countdown_from_meta(m, TODAY) == "29 days"


def test_countdown_n_months():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 30)
    assert card_state.card_countdown_from_meta(m, TODAY) == "1 mo"
    m2 = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 364)
    assert card_state.card_countdown_from_meta(m2, TODAY) == "12 mo"


def test_countdown_n_years():
    m = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 365)
    assert card_state.card_countdown_from_meta(m, TODAY) == "1 yr"
    m2 = _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 800)
    assert card_state.card_countdown_from_meta(m2, TODAY) == "2 yr"


def test_countdown_day_learn_relearn_uses_day_math():
    """DAY_LEARN_RELEARN is classified as 'learn' state-wise but its
    countdown is computed via the day-based review branch (not seconds)."""
    m = _meta(QUEUE_TYPE_DAY_LEARN_RELEARN, CARD_TYPE_RELEARNING, TODAY + 2)
    assert card_state.card_countdown_from_meta(m, TODAY) == "2 days"


def test_countdown_blank_for_new_suspended_buried():
    for q in (QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED, QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED):
        m = _meta(q, CARD_TYPE_NEW, TODAY)
        assert card_state.card_countdown_from_meta(m, TODAY) == ""


def test_countdown_learn_queue_uses_wall_clock_seconds(monkeypatch):
    """QUEUE_TYPE_LRN countdown is second-based (wall clock), not day-based;
    time.time() is monkeypatched so the test stays deterministic."""
    monkeypatch.setattr(card_state.time, "time", lambda: 1_000_000)

    m_secs = _meta(QUEUE_TYPE_LRN, CARD_TYPE_LRN, 1_000_000 + 45)
    assert card_state.card_countdown_from_meta(m_secs, TODAY) == "45s"

    m_mins = _meta(QUEUE_TYPE_LRN, CARD_TYPE_LRN, 1_000_000 + 90)
    assert card_state.card_countdown_from_meta(m_mins, TODAY) == "1m"

    m_hours = _meta(QUEUE_TYPE_LRN, CARD_TYPE_LRN, 1_000_000 + 7200)
    assert card_state.card_countdown_from_meta(m_hours, TODAY) == "2h"

    m_past = _meta(QUEUE_TYPE_LRN, CARD_TYPE_LRN, 1_000_000 - 10)
    assert card_state.card_countdown_from_meta(m_past, TODAY) == ""


# ── filter_cards_by_states ──


def _states_meta():
    return {
        1: _meta(QUEUE_TYPE_NEW, CARD_TYPE_NEW, 5),                      # new
        2: _meta(QUEUE_TYPE_LRN, CARD_TYPE_LRN, TODAY),                   # learning
        3: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY),                   # due
        4: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 5),                # upcoming (mid)
        5: _meta(QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV, TODAY),              # suspended
    }


def test_filter_by_states_empty_chips_returns_all():
    meta = _states_meta()
    assert card_state.filter_cards_by_states(meta, TODAY, set()) == set(meta.keys())


def test_filter_by_states_new_chip():
    meta = _states_meta()
    assert card_state.filter_cards_by_states(meta, TODAY, {"new"}) == {1}


def test_filter_by_states_learning_chip():
    meta = _states_meta()
    assert card_state.filter_cards_by_states(meta, TODAY, {"learning"}) == {2}


def test_filter_by_states_due_chip():
    meta = _states_meta()
    assert card_state.filter_cards_by_states(meta, TODAY, {"due"}) == {3}


def test_filter_by_states_upcoming_chip():
    meta = _states_meta()
    assert card_state.filter_cards_by_states(meta, TODAY, {"upcoming"}) == {4}


def test_filter_by_states_suspended_chip():
    meta = _states_meta()
    assert card_state.filter_cards_by_states(meta, TODAY, {"suspended"}) == {5}


def test_filter_by_states_suspended_excluded_when_other_chips_active():
    meta = _states_meta()
    # "new" alone should not pull in the suspended card even though it would
    # normally show up in the unfiltered ("no chips") view.
    result = card_state.filter_cards_by_states(meta, TODAY, {"new", "due"})
    assert result == {1, 3}
    assert 5 not in result


def test_filter_by_states_new_and_suspended_together():
    meta = _states_meta()
    result = card_state.filter_cards_by_states(meta, TODAY, {"new", "suspended"})
    assert result == {1, 5}


# ── filter_cards_by_criteria ──


def _criteria_meta():
    return {
        1: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY, factor=2000, ivl=5, lapses=0, reps=2, flags=1),
        2: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY, factor=2500, ivl=10, lapses=2, reps=5, flags=2),
        3: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY, factor=3000, ivl=20, lapses=4, reps=10, flags=0),
    }


def test_filter_by_criteria_empty_is_all():
    meta = _criteria_meta()
    assert card_state.filter_cards_by_criteria(meta, {}) == set(meta.keys())


def test_filter_by_criteria_flag_exact_match():
    meta = _criteria_meta()
    assert card_state.filter_cards_by_criteria(meta, {"flag": 1}) == {1}
    assert card_state.filter_cards_by_criteria(meta, {"flag": 2}) == {2}


def test_filter_by_criteria_min_max_ease():
    meta = _criteria_meta()
    assert card_state.filter_cards_by_criteria(meta, {"min_ease": 2500}) == {2, 3}
    assert card_state.filter_cards_by_criteria(meta, {"max_ease": 2500}) == {1, 2}
    assert card_state.filter_cards_by_criteria(meta, {"min_ease": 2000, "max_ease": 3000}) == {1, 2, 3}


def test_filter_by_criteria_min_max_ivl():
    meta = _criteria_meta()
    assert card_state.filter_cards_by_criteria(meta, {"min_ivl": 10}) == {2, 3}
    assert card_state.filter_cards_by_criteria(meta, {"max_ivl": 10}) == {1, 2}


def test_filter_by_criteria_min_max_lapses():
    meta = _criteria_meta()
    assert card_state.filter_cards_by_criteria(meta, {"min_lapses": 2}) == {2, 3}
    assert card_state.filter_cards_by_criteria(meta, {"max_lapses": 2}) == {1, 2}


def test_filter_by_criteria_min_max_reps():
    meta = _criteria_meta()
    assert card_state.filter_cards_by_criteria(meta, {"min_reps": 5}) == {2, 3}
    assert card_state.filter_cards_by_criteria(meta, {"max_reps": 5}) == {1, 2}


def test_filter_by_criteria_combination_narrows_results():
    meta = _criteria_meta()
    result = card_state.filter_cards_by_criteria(meta, {"min_ivl": 10, "max_lapses": 2})
    assert result == {2}


# ── sort_cards ──


def _sort_meta():
    return {
        1: _meta(QUEUE_TYPE_NEW, CARD_TYPE_NEW, 0, factor=2000, ivl=1, lapses=5, reps=1, mod=500, sfld="Banana"),
        2: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY - 5, factor=1500, ivl=30, lapses=1, reps=20, mod=100, sfld="apple"),
        3: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 10, factor=3000, ivl=5, lapses=3, reps=8, mod=900, sfld="Cherry"),
    }


def test_sort_deck_is_noop_but_reverse_flips():
    meta = _sort_meta()
    ids = [3, 1, 2]
    assert card_state.sort_cards(ids, meta, TODAY, "deck") == [3, 1, 2]
    assert card_state.sort_cards(ids, meta, TODAY, "deck", reverse=True) == [2, 1, 3]


def test_sort_unknown_key_is_passthrough():
    meta = _sort_meta()
    ids = [3, 1, 2]
    assert card_state.sort_cards(ids, meta, TODAY, "not_a_real_key") == [3, 1, 2]
    assert card_state.sort_cards(ids, meta, TODAY, "not_a_real_key", reverse=True) == [2, 1, 3]


def test_sort_due_new_cards_last_by_default():
    meta = _sort_meta()
    # card 2 overdue, card 3 due later, card 1 is new -> new goes last
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "due") == [2, 3, 1]


def test_sort_due_reverse_is_not_a_simple_flip():
    """NOTE: reverse=True on 'due' does not just reverse the ascending
    order — new cards sort to the FRONT instead of staying last, because the
    (is_new, value) tuple key is sorted descending as a whole. Documenting
    actual behaviour rather than the (new-last) doc-comment's implication."""
    meta = _sort_meta()
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "due", reverse=True) == [1, 3, 2]


def test_sort_state_most_urgent_first():
    meta = _sort_meta()
    # states: 1=new(prio1), 2=review-due(prio5, overdue), 3=review-mid(prio3, +10d)
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "state") == [2, 3, 1]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "state", reverse=True) == [1, 3, 2]


def test_sort_field_alphabetical_case_insensitive():
    meta = _sort_meta()
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "sort_field") == [2, 1, 3]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "sort_field", reverse=True) == [3, 1, 2]


def test_sort_ease_lowest_first():
    meta = _sort_meta()
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "ease") == [2, 1, 3]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "ease", reverse=True) == [3, 1, 2]


def test_sort_interval_shortest_first():
    meta = _sort_meta()
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "interval") == [1, 3, 2]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "interval", reverse=True) == [2, 3, 1]


def test_sort_lapses_most_first():
    meta = _sort_meta()
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "lapses") == [1, 3, 2]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "lapses", reverse=True) == [2, 3, 1]


def test_sort_reps_most_first():
    meta = _sort_meta()
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "reps") == [2, 3, 1]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "reps", reverse=True) == [1, 3, 2]


def test_sort_created_newest_first_by_default():
    meta = _sort_meta()
    # 'created' sorts by card id itself (higher id assumed newer)
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "created") == [3, 2, 1]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "created", reverse=True) == [1, 2, 3]


def test_sort_modified_recent_first():
    meta = _sort_meta()
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "modified") == [3, 1, 2]
    assert card_state.sort_cards([1, 2, 3], meta, TODAY, "modified", reverse=True) == [2, 1, 3]


# ── group_flag ──


def test_group_flag_consensus():
    assert card_state.group_flag([3, 3, 3]) == 3


def test_group_flag_disagreement_is_zero():
    assert card_state.group_flag([1, 2]) == 0


def test_group_flag_zero_consensus():
    assert card_state.group_flag([0, 0]) == 0


def test_group_flag_single_value():
    assert card_state.group_flag([5]) == 5


def test_group_flag_low_three_bits_masking():
    # 9 == 0b1001 -> low 3 bits = 0b001 = 1; agrees with a literal 1.
    assert card_state.group_flag([9, 1]) == 1
