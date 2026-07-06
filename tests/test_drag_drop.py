"""Drag-and-drop tests: bridge-level move + DOM drag event wiring."""
from __future__ import annotations

from webview_harness import DomPage


def test_move_between_sections_is_targeted(tray, fake_mw):
    """A drag between two subdeck sections must not reload the page: the
    moved unit is dropped from the DOM and only the receiving section is
    rebuilt."""
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")

    pages_before = len(tray._web.pages)
    tray._web.evals.clear()
    tray._on_bridge_cmd(f"move_cards:{beta_did}:{cids['cherry']}")  # Alpha → Beta

    assert col.get_card(cids["cherry"]).did == beta_did
    assert len(tray._web.pages) == pages_before, "page must not reload"
    assert any(e.startswith(f"removeCard({cids['cherry']})") for e in tray._web.evals)
    assert any(e.startswith(f"replaceSection({beta_did}") for e in tray._web.evals)
    # the rebuilt target section contains the moved card
    section = next(e for e in tray._web.evals if e.startswith(f"replaceSection({beta_did}"))
    assert str(cids["cherry"]) in section
    # membership snapshot follows our own move (external diff must not re-fire)
    assert tray._tracker.known_cards[cids["cherry"]] == beta_did


def test_move_touching_root_area_falls_back_to_full_render(tray, fake_mw):
    """Cards in the tree root's own area aren't inside a rebuildable section,
    so moving one falls back to a full (scroll-preserving) re-render."""
    col = fake_mw.col
    cids = fake_mw.col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")

    pages_before = len(tray._web.pages)
    tray._on_bridge_cmd(f"move_cards:{beta_did}:{cids['apple']}")  # root → Beta

    assert col.get_card(cids["apple"]).did == beta_did
    assert len(tray._web.pages) == pages_before + 1, "expected one full render"


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
