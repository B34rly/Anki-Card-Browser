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
    """Regression: the bulk-change branch read a tray attribute that a
    refactor had removed; it only runs with filters active and >1 note."""
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
    # isVisible() is False for an unshown widget; force the visible path so
    # the handler actually runs instead of deferring to showEvent.
    widget.isVisible = lambda: True
    widget._on_operation_did_execute(changes, handler=None)
    # convergence: the handler must not have blown up, and the tray still
    # reflects the filtered view (title shows filtered counts)
    assert "/" in widget.tray.title
