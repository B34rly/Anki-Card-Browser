"""The unified CollectionOp refresh pipeline.

Our own mutations run as ops and refresh through the same
operation_did_execute path as external changes (the conftest fake_mw makes
ops synchronous). These tests pin the guarantees the migration added —
each was a confirmed staleness bug beforehand (ROADMAP §4 findings 3–5).
"""
from __future__ import annotations

from conftest import addon_module, deck_node


def test_partial_group_move_forces_full_render(tray, fake_mw, monkeypatch):
    """Moving one inner card out of a rendered note group must fully
    re-render (stale group maps previously resurrected the moved card)."""
    col = fake_mw.col
    nt = col.models.by_name("Basic (and reversed card)")
    note = col.new_note(nt)
    note["Front"] = "pair front"
    note["Back"] = "pair back"
    col.add_note(note, col.decks.id("Parent::Alpha"))

    tray.display_mode = "notes"
    tray.set_deck_tree(deck_node(col, "Parent"), "Parent")
    lead, second = note.card_ids()
    assert lead in tray._builder.note_groups

    beta_did = col.decks.id_for_name("Parent::Beta")
    monkeypatch.setattr(
        addon_module("tray.actions"), "prompt_change_deck",
        lambda parent, c, ids: beta_did,
    )
    pages_before = len(tray._web.pages)
    tray._on_bridge_cmd(f"change_deck:{second}")  # one inner card only

    assert col.get_card(second).did == beta_did
    assert len(tray._web.pages) == pages_before + 1, \
        "group-touching move must fall back to a full render"
    # the fresh page shows the moved card outside the (now 1-card) group
    assert second not in tray._builder.note_groups.get(lead, [lead])


def test_force_review_refreshes_page(tray, fake_mw):
    """'Force review all' now runs as an op → badges refresh (previously
    the browser kept stale New/Upcoming states)."""
    col = fake_mw.col
    alpha_did = col.decks.id_for_name("Parent::Alpha")

    from aqt.qt import QMessageBox
    orig = QMessageBox.question
    QMessageBox.question = staticmethod(
        lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    try:
        tray._web.reset_log()
        tray._on_bridge_cmd(f"force_review_deck:{alpha_did}")
    finally:
        QMessageBox.question = orig

    assert fake_mw.moved_to == ["review"]
    # the op pipeline refreshed the affected notes in place
    assert tray._web.evals_matching("replaceCard(") or tray._web.pages


def test_external_edit_refreshes_open_detail(tray, fake_mw):
    """An external op touching the card shown in the open detail overlay
    re-pushes the detail (previously it stayed stale indefinitely)."""
    from types import SimpleNamespace

    from aqt import gui_hooks

    col = fake_mw.col
    cids = col._test_cids
    tray._on_bridge_cmd(f"card_detail:{cids['banana']}")
    assert tray._open_detail == ("card", cids["banana"])

    note = col.get_note(col._test_notes["banana"].id)
    note["Back"] = "loaf, externally edited"
    col.update_note(note)  # direct write, like another add-on would
    tray._web.reset_log()
    gui_hooks.operation_did_execute(
        SimpleNamespace(card=True, note=True, deck=False, notetype=False,
                        study_queues=False),
        None,
    )

    details = tray._web.evals_matching("showCardDetail(")
    assert len(details) == 1
    assert "externally edited" in details[0]


def test_external_delete_closes_open_detail(tray, fake_mw, monkeypatch):
    """Deleting the shown card (our op or external) closes the overlay."""
    col = fake_mw.col
    cids = col._test_cids
    monkeypatch.setattr(
        addon_module("tray.actions"), "confirm_delete", lambda p, n: True
    )
    tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
    tray._web.reset_log()
    tray._on_bridge_cmd(f"delete_card:{cids['apple']}")

    assert tray._open_detail is None
    assert tray._web.evals_matching("closeOverlay()")
