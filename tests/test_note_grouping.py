"""Tests for note_grouping.py: note-level grouping and summarisation.

group_cards_by_note is exercised against a real collection (sample_col plus
a "Basic (and reversed card)" note for multi-card grouping); the pure
summary functions (note_state_summary / note_summary_counts) operate on
hand-built meta dicts, matching the style used for card_state.py.
"""
from __future__ import annotations

from anki.consts import (
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_DAY_LEARN_RELEARN,
    QUEUE_TYPE_SUSPENDED,
    QUEUE_TYPE_MANUALLY_BURIED,
    QUEUE_TYPE_SIBLING_BURIED,
    CARD_TYPE_NEW,
    CARD_TYPE_REV,
    CARD_TYPE_RELEARNING,
)

from conftest import addon_module

note_grouping = addon_module("core.note_grouping")
card_data = addon_module("core.card_data")

TODAY = 100


def _add_multicard_note(col, deck="Parent::Beta", front="front side", back="back side"):
    nt = col.models.by_name("Basic (and reversed card)")
    note = col.new_note(nt)
    note["Front"] = front
    note["Back"] = back
    col.add_note(note, col.decks.id(deck))
    return note


# ── group_cards_by_note ──


def test_group_cards_by_note_single_card_notes(sample_col):
    cids = sample_col._test_cids
    groups = note_grouping.group_cards_by_note(
        sample_col, [cids["apple"], cids["banana"]]
    )
    assert len(groups) == 2
    assert all(len(g.cids) == 1 for g in groups)
    assert groups[0].cids == [cids["apple"]]
    assert groups[1].cids == [cids["banana"]]
    assert all(g.is_io is False for g in groups)


def test_group_cards_by_note_groups_multicard_note(sample_col):
    note = _add_multicard_note(sample_col)
    multi_cids = list(note.card_ids())
    assert len(multi_cids) == 2

    groups = note_grouping.group_cards_by_note(sample_col, multi_cids)
    assert len(groups) == 1
    g = groups[0]
    assert g.nid == note.id
    assert g.cids == multi_cids
    assert g.is_io is False


def test_group_cards_by_note_preserves_first_appearance_order(sample_col):
    cids = sample_col._test_cids
    note = _add_multicard_note(sample_col)
    multi_cids = list(note.card_ids())

    # Interleave: apple, then first half of the multi-card note, then banana,
    # then the second card of the multi-card note.
    card_ids = [cids["apple"], multi_cids[0], cids["banana"], multi_cids[1]]
    groups = note_grouping.group_cards_by_note(sample_col, card_ids)

    assert [g.nid for g in groups] == [
        sample_col._test_notes["apple"].id, note.id, sample_col._test_notes["banana"].id,
    ]
    # Both cards of the multi-card note end up under the one group, in the
    # order they appeared in card_ids (not necessarily template/ord order).
    multi_group = groups[1]
    assert multi_group.cids == [multi_cids[0], multi_cids[1]]


def test_group_cards_by_note_empty_input_returns_empty(sample_col):
    assert note_grouping.group_cards_by_note(sample_col, []) == []


def test_group_cards_by_note_meta_prefetch_matches_auto_fetch(sample_col):
    cids = sample_col._test_cids
    note = _add_multicard_note(sample_col)
    multi_cids = list(note.card_ids())
    card_ids = [cids["apple"], cids["banana"], *multi_cids]

    groups_auto = note_grouping.group_cards_by_note(sample_col, card_ids)

    prefetched_meta = card_data.get_cards_metadata(sample_col, card_ids)
    groups_manual = note_grouping.group_cards_by_note(sample_col, card_ids, meta=prefetched_meta)

    assert groups_auto == groups_manual


def test_group_cards_by_note_accepts_superset_meta(sample_col):
    """A meta dict covering more cards than requested is fine — only the
    requested card_ids are grouped."""
    cids = sample_col._test_cids
    all_cids = list(cids.values())
    superset_meta = card_data.get_cards_metadata(sample_col, all_cids)

    requested = [cids["apple"], cids["banana"]]
    groups = note_grouping.group_cards_by_note(sample_col, requested, meta=superset_meta)

    assert {g.nid for g in groups} == {
        sample_col._test_notes["apple"].id, sample_col._test_notes["banana"].id,
    }
    assert len(groups) == 2


# ── note_state_summary ──


def _meta(queue, type_, due, **kw):
    base = {"queue": queue, "type": type_, "due": due}
    base.update(kw)
    return base


def test_note_state_summary_counts_and_dominant_state():
    meta = {
        1: _meta(QUEUE_TYPE_NEW, CARD_TYPE_NEW, 0),
        2: _meta(QUEUE_TYPE_DAY_LEARN_RELEARN, CARD_TYPE_RELEARNING, TODAY + 2),  # "learn" (highest prio)
        3: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY),                          # review-due
        4: _meta(QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV, TODAY),                     # suspended
    }
    summary = note_grouping.note_state_summary(meta, [1, 2, 3, 4], TODAY)

    assert summary["total"] == 4
    assert summary["new"] == 1
    assert summary["learn"] == 1
    assert summary["due"] == 1
    assert summary["upcoming"] == 0
    assert summary["suspended"] == 1
    # "learn" (priority 6) outranks "review-due" (priority 5)
    assert summary["dominant_state"] == "learn"
    assert summary["dominant_countdown"] == "2 days"
    assert summary["all_suspended"] is False
    assert summary["all_buried"] is False


def test_note_state_summary_upcoming_bucket():
    meta = {
        1: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 5),   # review-mid -> upcoming
        2: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 20),  # review-later -> upcoming
    }
    summary = note_grouping.note_state_summary(meta, [1, 2], TODAY)
    assert summary["upcoming"] == 2
    assert summary["due"] == 0


def test_note_state_summary_all_suspended():
    meta = {
        1: _meta(QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV, TODAY),
        2: _meta(QUEUE_TYPE_SUSPENDED, CARD_TYPE_NEW, TODAY),
    }
    summary = note_grouping.note_state_summary(meta, [1, 2], TODAY)
    assert summary["all_suspended"] is True
    assert summary["dominant_state"] == ""
    assert summary["dominant_countdown"] == ""


def test_note_state_summary_all_buried():
    meta = {
        1: _meta(QUEUE_TYPE_MANUALLY_BURIED, CARD_TYPE_REV, TODAY),
        2: _meta(QUEUE_TYPE_SIBLING_BURIED, CARD_TYPE_REV, TODAY),
    }
    summary = note_grouping.note_state_summary(meta, [1, 2], TODAY)
    assert summary["all_buried"] is True
    assert summary["all_suspended"] is False


def test_note_state_summary_partial_buried_is_not_all_buried():
    meta = {
        1: _meta(QUEUE_TYPE_MANUALLY_BURIED, CARD_TYPE_REV, TODAY),
        2: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY),
    }
    summary = note_grouping.note_state_summary(meta, [1, 2], TODAY)
    assert summary["all_buried"] is False


def test_note_state_summary_skips_missing_meta():
    meta = {1: _meta(QUEUE_TYPE_NEW, CARD_TYPE_NEW, 0)}
    summary = note_grouping.note_state_summary(meta, [1, 999], TODAY)
    assert summary["total"] == 1


# ── note_summary_counts ──


def test_note_summary_counts_notes_vs_cards():
    meta = {
        1: _meta(QUEUE_TYPE_NEW, CARD_TYPE_NEW, 0, nid=100),
        2: _meta(QUEUE_TYPE_NEW, CARD_TYPE_NEW, 0, nid=100),  # same note, 2nd card
        3: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY, nid=200),
        4: _meta(QUEUE_TYPE_DAY_LEARN_RELEARN, CARD_TYPE_RELEARNING, TODAY, nid=300),
        5: _meta(QUEUE_TYPE_REV, CARD_TYPE_REV, TODAY + 20, nid=400),
        6: _meta(QUEUE_TYPE_SUSPENDED, CARD_TYPE_REV, TODAY, nid=500),
    }
    result = note_grouping.note_summary_counts(meta, [1, 2, 3, 4, 5, 6], TODAY)

    assert result["cards"] == 6
    assert result["notes"] == 5  # nid 100 counted once despite 2 cards
    assert result["new"] == 2
    assert result["learn"] == 1
    assert result["due"] == 1
    assert result["upcoming"] == 1
    # Suspended card contributes to "cards"/"notes" but no state bucket.
    assert result["new"] + result["learn"] + result["due"] + result["upcoming"] == 5


def test_note_summary_counts_empty_input():
    result = note_grouping.note_summary_counts({}, [], TODAY)
    assert result == {"notes": 0, "cards": 0, "new": 0, "learn": 0, "due": 0, "upcoming": 0}
