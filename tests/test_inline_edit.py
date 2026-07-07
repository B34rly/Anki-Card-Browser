"""In-place field editing inside the detail overlay.

The same popup that shows a card (header, action bar, stats, history)
carries a #detail-fields section of contenteditable field blocks. Typing
marks it dirty — revealing Revert/Save and deferring refresh pushes — and
Save round-trips through the save_note bridge. The edit_target config only
governs the explicit ✎ buttons on card frames.
"""
from __future__ import annotations

import json

from webview_harness import DomPage


def _detail_evals(tray):
    return tray._web.evals_matching("showCardDetail(")


def test_detail_popup_contains_editable_fields(tray, fake_mw):
    """Every card detail is the edit surface: fields section + wiring."""
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"card_detail:{cids['apple']}")

    html = _detail_evals(tray)[0]
    for expected in (
        "detail-fields", "contenteditable", "apple pie", "crust",
        "saveNoteEdit", "revertNoteEdit", "focusDetailFields",
    ):
        assert expected in html, f"missing {expected!r}"
    # still the full inspector around it, not a separate form
    for expected in ("detail-actions", "detail-stats", "Suspend"):
        assert expected in html, f"missing {expected!r}"
    # the fields are a third tab on the Q/A toggle (no duplicated content
    # stacked under the rendered card), shown one pane at a time
    assert ">Fields</button>" in html
    assert "detail-f" in html


def test_note_detail_fields_are_editable_too(tray, fake_mw):
    from conftest import deck_node

    col = fake_mw.col
    nt = col.models.by_name("Basic (and reversed card)")
    note = col.new_note(nt)
    note["Front"] = "front side"
    note["Back"] = "back side"
    col.add_note(note, col.decks.id("Parent::Beta"))
    tray.display_mode = "notes"
    tray.set_deck_tree(deck_node(col, "Parent"), "Parent")
    lead = note.card_ids()[0]

    tray._web.reset_log()
    tray._on_bridge_cmd(f"note_detail:{lead}")
    html = _detail_evals(tray)[0]
    assert "detail-fields" in html and "contenteditable" in html
    # the read-only fields table only renders for view mode
    assert "view-only" in html


def test_save_note_updates_and_repushes_the_same_popup(tray, fake_mw):
    col = fake_mw.col
    cids = col._test_cids
    note = col._test_notes["apple"]
    tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
    tray._web.reset_log()

    payload = json.dumps({
        "nid": note.id, "unit": cids["apple"],
        "fields": ["apple strudel", "flaky crust"],
    })
    tray._on_bridge_cmd(f"save_note:{payload}")

    assert col.get_note(note.id).fields == ["apple strudel", "flaky crust"]
    # grid card refreshed through the op pipeline
    assert tray._web.evals_matching("replaceCard(")
    assert 'showToast("Saved")' in tray._web.evals
    # the popup refreshed in place with the new content
    assert tray._open_detail == ("card", cids["apple"])
    details = _detail_evals(tray)
    assert details and "apple strudel" in details[-1]


def test_save_note_field_count_mismatch_is_refused(tray, fake_mw):
    """A save landing after the notetype changed must not scramble fields."""
    col = fake_mw.col
    cids = col._test_cids
    note = col._test_notes["apple"]
    before = col.get_note(note.id).fields

    payload = json.dumps({
        "nid": note.id, "unit": cids["apple"], "fields": ["only one"],
    })
    tray._web.reset_log()
    tray._on_bridge_cmd(f"save_note:{payload}")

    assert col.get_note(note.id).fields == before
    assert tray._web.evals_matching('showToast("Note layout changed')


def test_edit_target_browser_pencil_opens_anki_browser(tray, fake_mw, monkeypatch):
    """Default config: the card-frame pencil bounces to Anki's Browser."""
    import aqt

    opened: list[tuple] = []
    monkeypatch.setattr(
        aqt.dialogs, "open", lambda *a, **k: opened.append(a) or None
    )
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"edit_card:{cids['apple']}")

    assert opened and opened[0][0] == "Browser"
    assert "closeOverlay()" in tray._web.evals
    assert not _detail_evals(tray)


def test_edit_target_inline_pencil_opens_popup_focused(tray, fake_mw):
    """edit_target: inline — the pencil opens the detail popup and drops
    focus straight into the first field."""
    tray._edit_target = "inline"
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"edit_card:{cids['apple']}")

    details = _detail_evals(tray)
    assert len(details) == 1 and "detail-fields" in details[0]
    assert tray._open_detail == ("card", cids["apple"])
    assert "focusDetailFields()" in tray._web.evals


def test_dom_edit_save_round_trip(qapp, tray, fake_mw):
    """Real DOM: type into a field of the open popup, save — the note
    changes and the same popup refreshes with the result."""
    col = fake_mw.col
    cids = col._test_cids
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        tray._web.evals.clear()
        tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
        for js in tray._web.evals:
            page.run_js(js + "; true")
        tray._web.evals.clear()
        assert page.run_js("!!document.getElementById('detail-fields')")

        # calm until edited: no dirty class, save bar hidden, save a no-op
        page.drain_pycmds()
        page.run_js("saveNoteEdit(); true")
        assert not [c for c in page.drain_pycmds() if c.startswith("save_note:")]

        page.run_js(
            "var f = document.querySelector('#detail-fields .edit-field');"
            "f.innerHTML = 'apple crumble';"
            "f.dispatchEvent(new InputEvent('input', {bubbles: true})); true"
        )
        assert page.run_js(
            "document.getElementById('detail-fields').classList.contains('dirty')"
        )
        page.run_js("saveNoteEdit(); true")
        save = [c for c in page.drain_pycmds() if c.startswith("save_note:")]
        assert len(save) == 1

        tray._on_bridge_cmd(save[0])
        assert col.get_note(col._test_notes["apple"].id).fields[0] == "apple crumble"
        for js in tray._web.evals:
            page.run_js(js + "; true")
        tray._web.evals.clear()
        # same popup, refreshed: still open, fields clean, new content shown
        assert page.run_js(
            "document.getElementById('overlay').classList.contains('open')"
        )
        assert not page.run_js(
            "document.getElementById('detail-fields').classList.contains('dirty')"
        )
        assert page.run_js(
            "document.getElementById('overlay-card-content')"
            ".textContent.indexOf('apple crumble') >= 0"
        )
    finally:
        page.close()


def test_dom_dirty_fields_block_refresh_pushes(qapp, tray, fake_mw):
    """[RACE] An op refresh landing mid-edit must not wipe the typed text —
    refresh pushes back off while the fields are dirty."""
    cids = fake_mw.col._test_cids
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        tray._web.evals.clear()
        tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
        for js in tray._web.evals:
            page.run_js(js + "; true")
        tray._web.evals.clear()

        page.run_js(
            "var f = document.querySelector('#detail-fields .edit-field');"
            "f.innerHTML = 'unsaved typing';"
            "f.dispatchEvent(new InputEvent('input', {bubbles: true})); true"
        )
        page.run_js(
            f"showCardDetail('<p>refresh</p>', {cids['apple']}, true); true"
        )
        assert page.run_js(
            "document.getElementById('overlay-card-content')"
            ".textContent.indexOf('unsaved typing') >= 0"
        ), "the refresh push must not replace dirty fields"
        # a user-initiated push (isRefresh=false) still wins
        page.run_js(
            f"showCardDetail('<p>fresh open</p>', {cids['apple']}, false); true"
        )
        assert page.run_js(
            "document.getElementById('overlay-card-content')"
            ".textContent.indexOf('fresh open') >= 0"
        )
    finally:
        page.close()


def test_dom_escape_blurs_field_before_closing(qapp, tray, fake_mw):
    cids = fake_mw.col._test_cids
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        tray._web.evals.clear()
        tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
        for js in tray._web.evals:
            page.run_js(js + "; true")
        tray._web.evals.clear()

        page.run_js("focusDetailFields(); true")
        assert page.run_js(
            "document.activeElement.classList.contains('edit-field')"
        )
        esc = ("document.dispatchEvent(new KeyboardEvent('keydown',"
               " {key: 'Escape', bubbles: true})); true")
        page.run_js(esc)  # steps out of the field
        assert not page.run_js(
            "document.activeElement.classList.contains('edit-field')"
        )
        assert page.run_js(
            "document.getElementById('overlay').classList.contains('open')"
        )
        page.run_js(esc)  # now closes the popup
        assert not page.run_js(
            "document.getElementById('overlay').classList.contains('visible')"
        )
    finally:
        page.close()
