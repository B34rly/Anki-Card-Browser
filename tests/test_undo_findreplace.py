"""Undo/redo and find & replace: the ops, their toasts, and the bulk route.

Both run through CollectionOp (synchronous under the fake_mw fixture), so
the op pipeline's refresh and the in-page toast are assertable directly on
the tray's FakeWebView log.
"""
from __future__ import annotations

from anki.cards import CardId
from anki.consts import QUEUE_TYPE_SUSPENDED

from conftest import addon_module

actions = addon_module("tray.actions")


def _queue(col, cid):
    return col.get_card(CardId(cid)).queue


# ── undo / redo ──


def test_undo_reverts_last_op_and_toasts(tray, fake_mw):
    col = fake_mw.col
    cid = col._test_cids["apple"]
    tray._on_bridge_cmd(f"suspend:{cid}")
    assert _queue(col, cid) == QUEUE_TYPE_SUSPENDED

    actions.undo_redo(tray)
    assert _queue(col, cid) != QUEUE_TYPE_SUSPENDED
    assert any("Undid" in e for e in tray._web.evals)


def test_redo_reapplies_undone_op(tray, fake_mw):
    col = fake_mw.col
    cid = col._test_cids["apple"]
    tray._on_bridge_cmd(f"suspend:{cid}")
    actions.undo_redo(tray)
    assert _queue(col, cid) != QUEUE_TYPE_SUSPENDED

    actions.undo_redo(tray, redo=True)
    assert _queue(col, cid) == QUEUE_TYPE_SUSPENDED
    assert any("Redid" in e for e in tray._web.evals)


# ── find & replace (bulk bridge command) ──


def test_bulk_find_replace_replaces_in_notes(tray, fake_mw, monkeypatch):
    col = fake_mw.col
    cid = col._test_cids["apple"]
    monkeypatch.setattr(
        actions, "_get_find_replace_spec",
        lambda parent, c, nids: ("apple", "quince", None, False, False),
    )
    tray._on_bridge_cmd(f"bulk:find_replace:{cid}")

    note = col.get_card(CardId(cid)).note()
    assert "quince pie" in note.fields[0]
    assert any("Replaced in 1 of 1 notes" in e for e in tray._web.evals)
    # An op started → the selection is cleared like other bulk actions.
    assert any("clearSelection()" in e for e in tray._web.evals)


def test_bulk_find_replace_cancelled_keeps_selection(tray, fake_mw, monkeypatch):
    col = fake_mw.col
    cid = col._test_cids["apple"]
    monkeypatch.setattr(actions, "_get_find_replace_spec", lambda *a: None)
    tray._web.reset_log()
    tray._on_bridge_cmd(f"bulk:find_replace:{cid}")

    note = col.get_card(CardId(cid)).note()
    assert "apple pie" in note.fields[0]  # untouched
    assert not any("clearSelection()" in e for e in tray._web.evals)


def test_find_replace_scoped_to_one_field(tray, fake_mw, monkeypatch):
    """A field-scoped replace leaves other fields alone ("crust" lives in
    Back; scoping to Front must not touch it)."""
    col = fake_mw.col
    cid = col._test_cids["apple"]
    monkeypatch.setattr(
        actions, "_get_find_replace_spec",
        lambda parent, c, nids: ("crust", "base", "Front", False, False),
    )
    tray._on_bridge_cmd(f"bulk:find_replace:{cid}")

    note = col.get_card(CardId(cid)).note()
    assert note.fields[1] == "crust"
    assert any("Replaced in 0 of 1 notes" in e for e in tray._web.evals)


def test_find_replace_spans_all_selected_notes(tray, fake_mw, monkeypatch):
    col = fake_mw.col
    cids = col._test_cids
    monkeypatch.setattr(
        actions, "_get_find_replace_spec",
        lambda parent, c, nids: ("a", "@", None, False, False),
    )
    tray._on_bridge_cmd(f"bulk:find_replace:{cids['apple']},{cids['banana']}")

    apple = col.get_card(CardId(cids["apple"])).note()
    banana = col.get_card(CardId(cids["banana"])).note()
    assert "@" in apple.fields[0] and "@" in banana.fields[0]
    assert any("of 2 notes" in e for e in tray._web.evals)
