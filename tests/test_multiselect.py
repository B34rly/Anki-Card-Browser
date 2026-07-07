"""Multiselect bulk actions: bridge round trips and the live selection UI."""
from __future__ import annotations

from conftest import addon_module, deck_node
from webview_harness import DomPage

QUEUE_SUSPENDED = -1


def test_bulk_suspend_refreshes_each_unit(tray, fake_mw):
    col = fake_mw.col
    cids = col._test_cids
    tray._web.reset_log()

    tray._on_bridge_cmd(f"bulk:suspend:{cids['apple']},{cids['elder']}")

    assert col.get_card(cids["apple"]).queue == QUEUE_SUSPENDED
    assert col.get_card(cids["elder"]).queue == QUEUE_SUSPENDED
    assert tray._web.evals_matching("clearSelection()")
    replaced = "".join(tray._web.evals_matching("replaceCard("))
    assert f"replaceCard({cids['apple']}" in replaced
    assert f"replaceCard({cids['elder']}" in replaced


def test_bulk_delete_removes_units(tray, fake_mw):
    col = fake_mw.col
    cids = col._test_cids
    monkey_target = addon_module("tray.actions")
    orig = monkey_target.confirm_delete
    monkey_target.confirm_delete = lambda parent, count: True
    try:
        tray._web.reset_log()
        tray._on_bridge_cmd(f"bulk:delete:{cids['apple']},{cids['cherry']}")
    finally:
        monkey_target.confirm_delete = orig

    remaining = set(col.decks.cids(deck_node(col, "Parent").deck_id, children=True))
    assert cids["apple"] not in remaining
    assert cids["cherry"] not in remaining
    evals = "".join(tray._web.evals)
    assert f"removeCard({cids['apple']})" in evals
    assert f"removeCard({cids['cherry']})" in evals
    assert "clearSelection()" in evals


def test_bulk_change_deck_moves_selection(tray, fake_mw, monkeypatch):
    col = fake_mw.col
    cids = col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")
    monkeypatch.setattr(
        addon_module("tray.actions"), "prompt_change_deck",
        lambda parent, c, ids: beta_did,
    )

    tray._on_bridge_cmd(f"bulk:change_deck:{cids['cherry']},{cids['date']}")

    assert col.get_card(cids["cherry"]).did == beta_did
    assert col.get_card(cids["date"]).did == beta_did


def test_bulk_expands_note_group_leads(tray, fake_mw):
    """In notes mode a selected group lead stands in for all its cards."""
    col = fake_mw.col
    nt = col.models.by_name("Basic (and reversed card)")
    note = col.new_note(nt)
    note["Front"] = "pair front"
    note["Back"] = "pair back"
    col.add_note(note, col.decks.id("Parent::Beta"))

    tray.display_mode = "notes"
    tray.set_deck_tree(deck_node(col, "Parent"), "Parent")
    lead = note.card_ids()[0]
    assert lead in tray._builder.note_groups

    tray._on_bridge_cmd(f"bulk:suspend:{lead}")
    for cid in note.card_ids():
        assert col.get_card(cid).queue == QUEUE_SUSPENDED


def test_dom_select_all_and_body_padding_class(qapp, tray, fake_mw):
    """Ctrl+A selects every rendered unit and the body gets the padding
    class so the bar can't cover the last row."""
    tray.set_filters(search_text="a")  # matches every sample card
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        page.run_js(
            "document.dispatchEvent(new KeyboardEvent('keydown',"
            " {key: 'a', ctrlKey: true, bubbles: true, cancelable: true})); true"
        )
        units = page.run_js("_detailUnits().length")
        assert units > 0
        assert page.run_js("_selected.size") == units
        assert page.run_js("document.body.classList.contains('selection-open')")
        page.run_js("clearSelection(); true")
        assert not page.run_js("document.body.classList.contains('selection-open')")
    finally:
        page.close()


def test_dom_tag_pill_click_requests_filter(qapp, tray, fake_mw):
    """Clicking a tag pill sends filter_tag (and doesn't open the card)."""
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="banana")  # banana has tag "baking"
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.drain_pycmds()
        assert page.run_js(
            f"document.querySelector('[data-cid=\"{cids['banana']}\"]"
            " .card-tag') !== null"
        )
        page.run_js(
            f"document.querySelector('[data-cid=\"{cids['banana']}\"]"
            " .card-tag').click(); true"
        )
        cmds = page.drain_pycmds()
        assert "filter_tag:baking" in cmds
        assert not any(c.startswith("card_detail:") for c in cmds)
    finally:
        page.close()


def test_dom_ctrl_click_selects_and_bulk_sends(qapp, tray, fake_mw):
    """Real DOM: Ctrl-click selects two cards, the bar opens, Suspend sends
    one bulk command, Escape clears."""
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="a")  # eager render: apple/banana/date match
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        for key in ("apple", "banana"):
            page.run_js(
                f"document.querySelector('[data-cid=\"{cids[key]}\"]')"
                ".dispatchEvent(new MouseEvent('click', "
                "{bubbles: true, cancelable: true, ctrlKey: true})); true"
            )
        assert page.run_js("document.querySelectorAll('.selected').length") == 2
        assert page.run_js(
            "document.getElementById('selection-bar').classList.contains('open')"
        )
        assert page.run_js(
            "document.getElementById('selection-count').textContent"
        ) == "2 selected"
        page.screenshot("/tmp/card_browser_multiselect.png")

        page.drain_pycmds()
        page.run_js(
            "document.querySelector('#selection-bar .sel-btn').click(); true"
        )
        cmds = page.drain_pycmds()
        bulk = [c for c in cmds if c.startswith("bulk:suspend:")]
        assert len(bulk) == 1
        sent = set(bulk[0].split(":", 2)[2].split(","))
        assert sent == {str(cids["apple"]), str(cids["banana"])}

        page.run_js(
            "document.dispatchEvent(new KeyboardEvent('keydown', "
            "{key: 'Escape', bubbles: true})); true"
        )
        assert page.run_js("document.querySelectorAll('.selected').length") == 0
    finally:
        page.close()
