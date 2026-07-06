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
