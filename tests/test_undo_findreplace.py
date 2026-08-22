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


