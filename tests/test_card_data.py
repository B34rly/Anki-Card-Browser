"""Pure-logic tests for card_data.py against a real collection.

Most functions here are bulk SQL helpers, so they're exercised against
`sample_col` (a real, populated Collection) rather than mocked.
"""
from __future__ import annotations

from anki.consts import (
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_SUSPENDED,
    CARD_TYPE_NEW,
    CARD_TYPE_REV,
)

from conftest import addon_module, add_basic_note

card_data = addon_module("core.card_data")


# ── get_cards_metadata ──


def test_get_cards_metadata_keys_and_values(sample_col):
    cids = sample_col._test_cids
    meta = card_data.get_cards_metadata(sample_col, list(cids.values()))

    expected_keys = {
        "cid", "type", "queue", "due", "nid", "mid", "did",
        "factor", "ivl", "lapses", "reps", "flags", "mod", "sfld",
    }
    assert set(meta[cids["apple"]].keys()) == expected_keys

    apple = meta[cids["apple"]]
    assert apple["queue"] == QUEUE_TYPE_NEW
    assert apple["type"] == CARD_TYPE_NEW
    assert apple["sfld"] == "apple pie"

    banana = meta[cids["banana"]]
    assert banana["queue"] == QUEUE_TYPE_REV
    assert banana["type"] == CARD_TYPE_REV
    assert banana["due"] == sample_col.sched.today
    assert banana["lapses"] == 2
    assert banana["flags"] == 1
    assert banana["sfld"] == "banana bread"

    date = meta[cids["date"]]
    assert date["queue"] == QUEUE_TYPE_SUSPENDED


def test_get_cards_metadata_empty_input_returns_empty(sample_col):
    assert card_data.get_cards_metadata(sample_col, []) == {}


# ── get_card_decks / get_deck_cards / get_note_cards ──


def test_get_card_decks(sample_col):
    cids = sample_col._test_cids
    parent_did = sample_col.decks.id("Parent")
    alpha_did = sample_col.decks.id("Parent::Alpha")

    decks = card_data.get_card_decks(sample_col, [cids["apple"], cids["cherry"]])
    assert decks == {cids["apple"]: parent_did, cids["cherry"]: alpha_did}


def test_get_deck_cards(sample_col):
    cids = sample_col._test_cids
    alpha_did = sample_col.decks.id("Parent::Alpha")

    result = card_data.get_deck_cards(sample_col, [alpha_did])
    assert result == {cids["cherry"]: alpha_did, cids["date"]: alpha_did}


def test_get_note_cards_single_and_multi(sample_col):
    notes = sample_col._test_notes
    cids = sample_col._test_cids

    single = card_data.get_note_cards(sample_col, [notes["apple"].id])
    assert single == {notes["apple"].id: [cids["apple"]]}

    # Add a two-card note and check ordering by ord.
    nt = sample_col.models.by_name("Basic (and reversed card)")
    note = sample_col.new_note(nt)
    note["Front"] = "front side"
    note["Back"] = "back side"
    sample_col.add_note(note, sample_col.decks.id("Parent::Beta"))

    multi = card_data.get_note_cards(sample_col, [note.id])
    assert multi[note.id] == list(note.card_ids())
    assert len(multi[note.id]) == 2


def test_get_note_cards_empty_input(sample_col):
    assert card_data.get_note_cards(sample_col, []) == {}


# ── search_cards_by_content ──


def test_search_case_insensitive(sample_col):
    cids = sample_col._test_cids
    all_cids = list(cids.values())
    result = card_data.search_cards_by_content(sample_col, all_cids, "BANANA")
    assert result == [cids["banana"]]


def test_search_strips_html_tags(sample_col):
    cids = sample_col._test_cids
    styled_note = add_basic_note(sample_col, "Parent", "<b>styled</b> word", "back")
    styled_cid = styled_note.card_ids()[0]

    all_cids = list(cids.values()) + [styled_cid]
    result = card_data.search_cards_by_content(sample_col, all_cids, "styled word")
    assert result == [styled_cid]


def test_search_empty_query_returns_all(sample_col):
    cids = list(sample_col._test_cids.values())
    assert card_data.search_cards_by_content(sample_col, cids, "") == cids


def test_search_empty_card_ids_returns_empty(sample_col):
    assert card_data.search_cards_by_content(sample_col, [], "banana") == []


# ── filter_cards_by_tag / get_tags_for_cards / get_flags_for_cards ──


def test_filter_cards_by_tag(sample_col):
    cids = sample_col._test_cids
    all_cids = list(cids.values())
    result = card_data.filter_cards_by_tag(sample_col, all_cids, "baking")
    assert set(result) == {cids["banana"], cids["date"]}


def test_filter_cards_by_tag_empty_tag_returns_all(sample_col):
    cids = list(sample_col._test_cids.values())
    assert card_data.filter_cards_by_tag(sample_col, cids, "") == cids


def test_get_tags_for_cards(sample_col):
    cids = list(sample_col._test_cids.values())
    assert card_data.get_tags_for_cards(sample_col, cids) == ["baking"]


def test_get_tags_for_cards_sorted_case_insensitive(sample_col):
    add_basic_note(sample_col, "Parent", "extra1", "back1", tags=["Zebra"])
    add_basic_note(sample_col, "Parent", "extra2", "back2", tags=["apple-tag"])
    # pull in the new notes too — search everything via get_card_decks scan
    parent_did = sample_col.decks.id("Parent")
    deck_cids = list(card_data.get_deck_cards(sample_col, [parent_did]).keys())
    tags = card_data.get_tags_for_cards(sample_col, deck_cids)
    assert tags == sorted(tags, key=str.lower)
    assert "apple-tag" in tags and "Zebra" in tags and "baking" in tags


def test_get_flags_for_cards(sample_col):
    cids = list(sample_col._test_cids.values())
    assert card_data.get_flags_for_cards(sample_col, cids) == [1]


def test_get_flags_for_cards_empty_input(sample_col):
    assert card_data.get_flags_for_cards(sample_col, []) == []


# ── is_io_mid / clear_caches ──


def test_is_io_mid_false_for_basic(sample_col):
    basic_mid = sample_col.models.by_name("Basic")["id"]
    assert card_data.is_io_mid(sample_col, basic_mid) is False


def test_clear_caches_resets_cache(sample_col):
    basic_mid = sample_col.models.by_name("Basic")["id"]
    card_data.is_io_mid(sample_col, basic_mid)
    assert basic_mid in card_data._io_mid_cache

    card_data.clear_caches()
    assert card_data._io_mid_cache == {}


# ── extract_io_data ──


def test_extract_io_data_image_and_masks():
    answer_html = (
        '<div class="io-image-container">'
        '<img src="paste-1234.jpg">'
        '<div class="cloze" data-ordinal="1" data-shape="rect" '
        'data-left="0.1" data-top="0.2" data-width="0.3" data-height="0.15"></div>'
        '<div class="cloze-inactive" data-ordinal="2" data-shape="ellipse" '
        'data-left="0.5" data-top="0.5" data-width="0.2" data-height="0.1"></div>'
        '<div class="cloze-highlight" data-ordinal="3" data-shape="polygon" '
        'data-points="0.1,0.1 0.2,0.1 0.15,0.2"></div>'
        '</div>'
    )
    img_src, masks = card_data.extract_io_data(answer_html)
    assert img_src == "paste-1234.jpg"
    assert len(masks) == 3

    by_ordinal = {m["ordinal"]: m for m in masks}
    assert by_ordinal["1"]["shape"] == "rect"
    assert by_ordinal["1"]["left"] == "0.1"
    assert by_ordinal["2"]["shape"] == "ellipse"
    assert by_ordinal["3"]["shape"] == "polygon"
    assert by_ordinal["3"]["points"] == "0.1,0.1 0.2,0.1 0.15,0.2"


def test_extract_io_data_no_image_or_masks():
    img_src, masks = card_data.extract_io_data("<div>no io content here</div>")
    assert img_src is None
    assert masks == []


# ── _query_in_chunks over > 500 ids ──


def test_query_in_chunks_handles_over_500_ids(sample_col):
    cids = list(sample_col._test_cids.values())
    fake_ids = list(range(10**9, 10**9 + 600))
    ids = fake_ids + cids

    meta = card_data.get_cards_metadata(sample_col, ids)
    assert set(meta.keys()) == set(cids)
    assert len(meta) == len(cids)
