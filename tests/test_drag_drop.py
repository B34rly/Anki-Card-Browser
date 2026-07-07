"""Drag-and-drop tests: bridge-level move + DOM drag event wiring."""
from __future__ import annotations

from webview_harness import DomPage


def test_move_between_sections_relocates_the_unit(tray, fake_mw):
    """A drag between two subdeck sections must be silent: neither section
    rebuilds (a rebuild re-mounts every card, which flashes) — the moved
    unit's DOM node relocates instead."""
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")

    pages_before = len(tray._web.pages)
    tray._web.evals.clear()
    tray._on_bridge_cmd(f"move_cards:{beta_did}:{cids['cherry']}")  # Alpha → Beta

    assert col.get_card(cids["cherry"]).did == beta_did
    assert len(tray._web.pages) == pages_before, "page must not reload"
    assert not any(e.startswith("replaceSection(") for e in tray._web.evals), \
        "sections must not rebuild for a plain move"
    moves = [e for e in tray._web.evals if e.startswith("moveUnit(")]
    assert len(moves) == 1
    assert moves[0].startswith(f'moveUnit({cids["cherry"]}, "card", {beta_did}, ')
    # membership snapshot adopted the move (no re-fire on the next op)
    assert tray._tracker.known_cards[cids["cherry"]] == beta_did
    # our own move clears any active selection
    assert "clearSelection()" in tray._web.evals


def test_whole_group_move_relocates_the_group(tray, fake_mw, monkeypatch):
    """A note group moving whole (the only way drags move groups) keeps its
    membership intact and travels as one unit — no full render."""
    from conftest import deck_node

    col = fake_mw.col
    nt = col.models.by_name("Basic (and reversed card)")
    note = col.new_note(nt)
    note["Front"] = "pair front"
    note["Back"] = "pair back"
    col.add_note(note, col.decks.id("Parent::Alpha"))

    tray.display_mode = "notes"
    tray.set_deck_tree(deck_node(col, "Parent"), "Parent")
    lead = note.card_ids()[0]
    assert lead in tray._builder.note_groups

    beta_did = col.decks.id_for_name("Parent::Beta")
    pages_before = len(tray._web.pages)
    tray._web.evals.clear()
    tray._on_bridge_cmd(f"move_cards:{beta_did}:{lead}")  # drag the group

    assert all(col.get_card(c).did == beta_did for c in note.card_ids())
    assert len(tray._web.pages) == pages_before, "page must not reload"
    moves = [e for e in tray._web.evals if e.startswith("moveUnit(")]
    assert len(moves) == 1
    assert moves[0].startswith(f'moveUnit({lead}, "group", {beta_did}, ')
    # the group maps stayed valid — membership didn't change
    assert tray._builder.note_groups[lead] == list(note.card_ids())


def test_move_into_root_area_falls_back_to_full_render(tray, fake_mw):
    """The tree root's own card area isn't an addressable section, so a move
    INTO it falls back to a full (scroll-preserving) re-render. Moves out of
    it are silent like any other — the element just relocates."""
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    parent_did = col.decks.id_for_name("Parent")

    pages_before = len(tray._web.pages)
    tray._on_bridge_cmd(f"move_cards:{parent_did}:{cids['elder']}")  # Beta → root

    assert col.get_card(cids["elder"]).did == parent_did
    assert len(tray._web.pages) == pages_before + 1, "expected one full render"


def test_move_out_of_root_area_is_silent(tray, fake_mw):
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")

    pages_before = len(tray._web.pages)
    tray._web.evals.clear()
    tray._on_bridge_cmd(f"move_cards:{beta_did}:{cids['apple']}")  # root → Beta

    assert col.get_card(cids["apple"]).did == beta_did
    assert len(tray._web.pages) == pages_before, "page must not reload"
    assert any(e.startswith(f'moveUnit({cids["apple"]}, ') for e in tray._web.evals)


def test_move_under_filters_falls_back_to_full_render(tray, fake_mw):
    """Under filters the target section may be missing from the DOM entirely,
    so a filtered move re-renders (which re-applies the filters)."""
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")
    tray.set_filters(search_text="cherry")

    pages_before = len(tray._web.pages)
    tray._on_bridge_cmd(f"move_cards:{beta_did}:{cids['cherry']}")

    assert col.get_card(cids["cherry"]).did == beta_did
    assert len(tray._web.pages) == pages_before + 1, "expected one full render"


def test_move_cards_to_missing_deck_is_noop(tray, fake_mw):
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    before = col.get_card(cids["apple"]).did
    tray._on_bridge_cmd(f"move_cards:99999999:{cids['apple']}")
    assert col.get_card(cids["apple"]).did == before


def test_dom_move_relocates_element_between_sections(qapp, tray, fake_mw):
    """Live-DOM round trip: after a move the card's element sits inside the
    target section — exactly one node for the cid, nothing rebuilt."""
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.pump_bridge(tray)  # lazy fills settle; cherry is a real frame
        tray._web.evals.clear()

        tray._on_bridge_cmd(f"move_cards:{beta_did}:{cids['cherry']}")
        for js in tray._web.evals:
            page.run_js(js + "; true")
        tray._web.evals.clear()

        sel = f"[data-cid=\"{cids['cherry']}\"], [data-lazy=\"{cids['cherry']}\"]"
        assert page.run_js(f"document.querySelectorAll('{sel}').length") == 1
        assert page.run_js(
            f"document.querySelector('{sel}')"
            ".closest('.deck-section').getAttribute('data-deck-id')"
        ) == str(beta_did)
    finally:
        page.close()


def test_dom_drag_card_to_header_sends_move(qapp, tray, fake_mw):
    """Simulated HTML5 drag: dragstart on a card, dragover+drop on a header."""
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="banana")  # eager render → draggable frame
    tray.edit_mode = True
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        # Alpha has no hits for "banana" so its header isn't in this page;
        # use the root header (drop target for the top-level deck).
        assert page.run_js(
            f"""
            (function() {{
                var card = document.querySelector('[data-cid="{cids['banana']}"]');
                var hdr = document.querySelector('.root-header');
                var dt = new DataTransfer();
                card.dispatchEvent(new DragEvent('dragstart',
                    {{bubbles: true, dataTransfer: dt}}));
                hdr.dispatchEvent(new DragEvent('dragover',
                    {{bubbles: true, dataTransfer: dt}}));
                var marked = hdr.classList.contains('drop-target');
                hdr.dispatchEvent(new DragEvent('drop',
                    {{bubbles: true, dataTransfer: dt}}));
                card.dispatchEvent(new DragEvent('dragend', {{bubbles: true}}));
                return marked;
            }})()
            """
        )
        cmds = page.drain_pycmds()
        parent_did = fake_mw.col.decks.id_for_name("Parent")
        assert f"move_cards:{parent_did}:{cids['banana']}" in cmds
    finally:
        page.close()


def test_dom_view_mode_blocks_drag(qapp, tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="banana")
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(false); true")
        assert page.run_js(
            f"""
            (function() {{
                var card = document.querySelector('[data-cid="{cids['banana']}"]');
                var dt = new DataTransfer();
                var ev = new DragEvent('dragstart', {{bubbles: true, cancelable: true, dataTransfer: dt}});
                card.dispatchEvent(ev);
                return ev.defaultPrevented;  /* drag refused in view mode */
            }})()
            """
        )
    finally:
        page.close()
