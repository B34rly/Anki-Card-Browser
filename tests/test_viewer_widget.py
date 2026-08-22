"""Viewer widget smoke tests: construction and the auto-refresh plumbing.

These exist chiefly to catch refactor breaks in code paths that only fire on
external collection changes (the operation_did_execute handler), which the
tray-level tests never reach.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conftest import addon_module


@pytest.fixture
def widget(qapp, fake_mw, fake_webview_cls, monkeypatch):
    tray_mod = addon_module("tray.tray")
    monkeypatch.setattr(tray_mod, "TrayWebView", fake_webview_cls)
    widget_mod = addon_module("viewer.widget")
    w = widget_mod.CardBrowserWidget()
    w._populate_combo()  # normally deferred via QTimer.singleShot
    yield w
    w.cleanup()


def test_widget_constructs_and_renders(widget, fake_mw):
    assert widget.tray._tree_root is not None
    assert "Parent" in widget.tray.title


def test_filter_change_consumes_pending_search_debounce(widget, fake_mw):
    """Regression: a chip click (or clear-all) landing while the 300ms search
    debounce was pending rendered the identical page twice — a visible flash
    that also dropped in-flight lazy fills."""
    from webview_harness import spin

    widget._card_search.setText("che")  # textChanged starts the debounce
    assert widget._search_timer.isActive()
    pages_before = len(widget.tray._web.pages)
    widget._apply_filters()  # e.g. a chip click
    assert not widget._search_timer.isActive()
    spin(400)  # the debounce window passes without a second render
    assert len(widget.tray._web.pages) == pages_before + 1


def test_tag_pill_request_sets_combo_and_filters(widget, fake_mw):
    """A tag pill click in the page routes to the Qt combo and applies."""
    widget.tray.tag_filter_requested.emit("baking")
    assert widget._tag_combo.currentData() == "baking"
    assert widget.tray._filters.tag_filter == "baking"


def test_filter_chips_show_and_clear(widget, fake_mw):
    idx = widget._tag_combo.findData("baking")
    assert idx > 0, "sample tag should be in the dropdown"
    widget._tag_combo.setCurrentIndex(idx)  # → _apply_filters → chips

    layout = widget._active_chips_layout
    labels = [layout.itemAt(i).widget().text() for i in range(layout.count())]
    assert any(text.startswith("Tag: baking") for text in labels)

    layout.itemAt(0).widget().click()  # ✕ chip clears exactly that filter
    assert widget._tag_combo.currentData() == ""
    assert layout.count() == 0
    assert widget.tray._filters.tag_filter == ""


def test_saved_searches_roundtrip(widget, fake_mw, monkeypatch):
    searches = addon_module("viewer.searches")
    col = fake_mw.col
    monkeypatch.setattr(
        searches.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("Baking cards", True)),
    )
    widget._card_search.setText("tag:baking")
    searches._save_current(widget, col)
    assert searches.load_saved_searches(col) == {"Baking cards": "tag:baking"}

    searches._remove(col, "Baking cards")
    assert searches.load_saved_searches(col) == {}


def test_external_change_handler_survives_filters(widget, fake_mw):
    """The op pipeline's bulk-change branch (filters active, >1 note) must
    converge without touching removed attributes (regression)."""
    from aqt import gui_hooks

    col = fake_mw.col
    widget._card_search.setText("qqq")  # matches nothing → filter stays active
    widget._apply_filters()

    # Touch two notes so the watermark sweep reports them both.
    notes = col._test_notes
    for key in ("apple", "banana"):
        note = col.get_note(notes[key].id)
        note["Back"] += " edited"
        col.update_note(note)

    changes = SimpleNamespace(
        card=True, note=True, deck=False, notetype=False, study_queues=False
    )
    # isVisible() is False for unshown widgets; force the visible path so
    # both hook handlers (widget structural + tray card/note) actually run.
    widget.isVisible = lambda: True
    widget.tray.isVisible = lambda: True
    gui_hooks.operation_did_execute(changes, None)
    # convergence: the handlers must not blow up, and the tray still
    # reflects the filtered view (title shows filtered counts)
    assert "/" in widget.tray.title


def test_undo_buttons_track_undo_status(widget, fake_mw):
    """The toolbar undo/redo buttons follow col.undo_status() through the
    op pipeline: an op arms undo, undoing it arms redo."""
    cid = fake_mw.col._test_cids["apple"]
    widget.tray._on_bridge_cmd(f"suspend:{cid}")
    assert widget._undo_btn.isEnabled()
    assert "Undo" in widget._undo_btn.toolTip()

    widget.trigger_undo()
    assert widget._redo_btn.isEnabled()
    assert "Redo" in widget._redo_btn.toolTip()
