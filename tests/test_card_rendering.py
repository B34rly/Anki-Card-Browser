"""Pure-logic tests for card_rendering.py: HTML-building helper functions.

Most functions here take plain data (no collection needed); render_normal_card
is the one exception and is tested against `sample_col`.
"""
from __future__ import annotations

from conftest import addon_module

card_rendering = addon_module("rendering")


# ── frame_classes ──


def test_frame_classes_suspended_outranks_buried():
    cls = card_rendering.frame_classes("review-due", suspended=True, buried=True)
    parts = cls.split()
    assert "suspended" in parts
    assert "buried" not in parts


def test_frame_classes_buried_when_not_suspended():
    cls = card_rendering.frame_classes("review-due", suspended=False, buried=True)
    parts = cls.split()
    assert "buried" in parts
    assert "suspended" not in parts


def test_frame_classes_extra_classes_included():
    cls = card_rendering.frame_classes("new", False, False, "note-group", "foo")
    parts = cls.split()
    assert "note-group" in parts
    assert "foo" in parts
    assert "card-frame" in parts


def test_frame_classes_state_class():
    cls = card_rendering.frame_classes("learn", False, False)
    assert "state-learn" in cls.split()


def test_frame_classes_no_state_class_when_state_blank():
    cls = card_rendering.frame_classes("", False, False)
    assert not any(p.startswith("state-") for p in cls.split())
    assert cls.split()[0] == "card-frame"


# ── build_tag_strip ──


def test_build_tag_strip_escapes_html():
    html = card_rendering.build_tag_strip(["<script>", "a&b"])
    assert "&lt;script&gt;" in html
    assert "a&amp;b" in html
    assert "<script>" not in html


def test_build_tag_strip_empty_is_blank():
    assert card_rendering.build_tag_strip([]) == ""


# ── build_flag_indicator ──


def test_build_flag_indicator_valid_flags_produce_dot():
    for flag, color in card_rendering.FLAG_COLORS.items():
        html = card_rendering.build_flag_indicator(flag)
        assert "card-flag" in html
        assert color in html
        assert f"Flag {flag}" in html


def test_build_flag_indicator_zero_and_out_of_range_are_blank():
    assert card_rendering.build_flag_indicator(0) == ""
    assert card_rendering.build_flag_indicator(8) == ""


# ── build_svg_mask ──


def test_build_svg_mask_rect_coordinates():
    mask = {"shape": "rect", "left": "0.1", "top": "0.2", "width": "0.3", "height": "0.4"}
    svg = card_rendering.build_svg_mask(mask)
    assert '<rect x="0.1" y="0.2" width="0.3" height="0.4"' in svg
    assert "rgba(255, 100, 100, 0.4)" in svg


def test_build_svg_mask_ellipse_coordinates():
    mask = {"shape": "ellipse", "left": "0.2", "top": "0.2", "width": "0.4", "height": "0.4"}
    svg = card_rendering.build_svg_mask(mask)
    assert '<ellipse cx="0.4" cy="0.4" rx="0.2" ry="0.2"' in svg


def test_build_svg_mask_polygon_points():
    mask = {"shape": "polygon", "points": "0.1,0.1 0.2,0.1 0.15,0.2"}
    svg = card_rendering.build_svg_mask(mask)
    assert '<polygon points="0.1,0.1 0.2,0.1 0.15,0.2"' in svg


def test_build_svg_mask_suspended_uses_grey_fill():
    mask = {"shape": "rect", "left": "0", "top": "0", "width": "1", "height": "1"}
    svg = card_rendering.build_svg_mask(mask, suspended=True)
    assert "rgba(150, 150, 150, 0.5)" in svg
    assert "rgba(255, 100, 100, 0.4)" not in svg


def test_build_svg_mask_unknown_shape_returns_empty():
    assert card_rendering.build_svg_mask({"shape": "triangle"}) == ""


# ── format_deck_path ──


def test_format_deck_path_short_path_no_prefix():
    html = card_rendering.format_deck_path("Parent")
    assert html == '<span class="deck-leaf">Parent</span>'


def test_format_deck_path_two_level():
    html = card_rendering.format_deck_path("Parent::Alpha")
    assert '<span class="deck-path">Parent::</span>' in html
    assert '<span class="deck-leaf">Alpha</span>' in html


def test_format_deck_path_deep_path_truncates_with_ellipsis():
    html = card_rendering.format_deck_path("A::B::C::D")
    assert '<span class="deck-path">...::B::C::</span>' in html
    assert '<span class="deck-leaf">D</span>' in html


def test_format_deck_path_very_long_segments_fall_back_to_tail2():
    long_name = "X" * 30
    full_path = f"{long_name}::{long_name}::{long_name}::Leaf"
    html = card_rendering.format_deck_path(full_path)
    # Falls back to only the immediate parent instead of the last 2 ancestors.
    assert html == (
        f'<span class="deck-path">...::{long_name}::</span>'
        f'<span class="deck-leaf">Leaf</span>'
    )


def test_format_deck_path_escapes_html():
    html = card_rendering.format_deck_path("Pare<nt>::Al&pha")
    assert "&lt;nt&gt;" in html
    assert "Al&amp;pha" in html
    assert "<nt>" not in html


# ── build_note_fields_table ──


def test_build_note_fields_table_empty_field_placeholder():
    html = card_rendering.build_note_fields_table([("Extra", ""), ("Extra2", "   ")])
    assert html.count("note-field-placeholder") == 2
    assert html.count("note-field-empty") == 2
    assert "empty" in html


def test_build_note_fields_table_cloze_marker_no_hint():
    html = card_rendering.build_note_fields_table([("Text", "{{c1::Paris}} is a city")])
    assert '<span class="cloze-marker">' in html
    assert '<span class="cloze-num">c1::</span>' in html
    assert "Paris" in html
    assert "cloze-hint" not in html


def test_build_note_fields_table_cloze_marker_with_hint():
    html = card_rendering.build_note_fields_table(
        [("Text", "{{c1::Paris::capital}} of France")]
    )
    assert '<span class="cloze-num">c1::</span>' in html
    assert "Paris" in html
    assert '<span class="cloze-hint">::capital</span>' in html


# ── render_normal_card (needs a real collection) ──


def test_render_normal_card_contains_expected_pieces(sample_col):
    cids = sample_col._test_cids
    html = card_rendering.render_normal_card(sample_col, cids["apple"])
    assert f'data-cid="{cids["apple"]}"' in html
    assert "apple pie" in html
    assert "crust" in html
    assert "Suspend" in html
    assert "Delete card" in html
    assert "state-new" in html


def test_render_normal_card_suspended_card_shows_unsuspend(sample_col):
    cids = sample_col._test_cids
    html = card_rendering.render_normal_card(sample_col, cids["date"])
    assert "Unsuspend" in html
    # Suspended cards have no state (card_state_from_meta returns "" for
    # suspended), so the frame class is just "card-frame suspended".
    assert 'class="card-frame suspended"' in html


def test_render_normal_card_flagged_card_shows_flag_indicator(sample_col):
    cids = sample_col._test_cids
    html = card_rendering.render_normal_card(sample_col, cids["banana"])
    assert "card-flag" in html
    assert "Flag 1" in html


# ── build_qa_content ──


def test_build_qa_content_has_toggle_and_both_sides():
    html = card_rendering.build_qa_content("<div>Q-marker</div>", "<div>A-marker</div>")
    assert "Question" in html
    assert "Answer" in html
    assert "Q-marker" in html
    assert "A-marker" in html
    assert 'class="detail-content show-a"' in html


# ── build_detail_actions ──


def test_build_detail_actions_present_buttons():
    html = card_rendering.build_detail_actions(
        "123", edit_cid=123, suspended=False, buried=False,
        can_reposition=False, delete_label="Delete card",
    )
    for expected in (
        "Suspend", "Bury", "Review now", "Set due", "Forget",
        "Add tag", "Change deck", "Delete card",
    ):
        assert expected in html, f"missing {expected!r}"


def test_build_detail_actions_suspended_shows_unsuspend():
    html = card_rendering.build_detail_actions(
        "123", edit_cid=123, suspended=True, buried=False,
        can_reposition=False, delete_label="Delete card",
    )
    assert "Unsuspend" in html
    assert ">Suspend<" not in html


def test_build_detail_actions_reposition_gated_by_can_reposition():
    html_without = card_rendering.build_detail_actions(
        "123", edit_cid=123, suspended=False, buried=False,
        can_reposition=False, delete_label="Delete card",
    )
    html_with = card_rendering.build_detail_actions(
        "123", edit_cid=123, suspended=False, buried=False,
        can_reposition=True, delete_label="Delete card",
    )
    assert "Reposition" not in html_without
    assert "Reposition" in html_with


# ── build_detail_html ──


def test_build_detail_html_escapes_stat_labels_but_trusts_values():
    actions_html = card_rendering.build_detail_actions(
        "1", edit_cid=1, suspended=False, buried=False,
        can_reposition=False, delete_label="Delete card",
    )
    html = card_rendering.build_detail_html(
        deck_path="Parent::Alpha",
        type_line="Basic - Card 1",
        state="review-due",
        countdown="Due",
        flag=2,
        stats=[("Some <b>Label</b>", "<b>5</b>")],
        tags=["baking"],
        content_html="<p>content</p>",
        actions_html=actions_html,
    )
    assert "Some &lt;b&gt;Label&lt;/b&gt;" in html   # label escaped
    assert "<b>5</b>" in html                          # value trusted/raw
    assert "Parent::Alpha" in html
    assert "detail-actions" in html
    assert "baking" in html


def test_build_detail_html_includes_actions_and_content():
    actions_html = card_rendering.build_detail_actions(
        "1", edit_cid=1, suspended=False, buried=False,
        can_reposition=True, delete_label="Delete card",
    )
    html = card_rendering.build_detail_html(
        deck_path="Parent",
        type_line="Basic - Card 1",
        state="new",
        countdown="",
        flag=0,
        stats=[],
        tags=[],
        content_html="<p>question and answer</p>",
        actions_html=actions_html,
    )
    assert "question and answer" in html
    assert "Reposition" in html
    assert "overlayNav" in html
