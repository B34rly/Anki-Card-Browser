"""Detail-overlay tests: bridge round trip (level 2) and live DOM (level 3)."""
from __future__ import annotations

from webview_harness import DomPage


def _detail_evals(tray):
    return tray._web.evals_matching("showCardDetail(")


def test_card_detail_contents(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"card_detail:{cids['banana']}")

    evals = _detail_evals(tray)
    assert len(evals) == 1
    html = evals[0]
    # stats, content, actions and chrome all present
    for expected in (
        "banana bread", "Due", "Interval", "Ease", "Reviews", "Lapses",
        "Created", "Modified", "detail-actions", "overlayNav",
        "Suspend", "Delete card", "Basic",
    ):
        assert expected in html, f"missing {expected!r}"
    assert tray._open_detail == ("card", cids["banana"])


def test_card_action_refreshes_open_detail(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
    tray._web.reset_log()

    tray._on_bridge_cmd(f"suspend:{cids['apple']}")
    evals = _detail_evals(tray)
    assert len(evals) == 1
    assert "Unsuspend" in evals[0]  # refreshed detail reflects the new state


def test_refresh_push_is_marked_as_refresh(tray, fake_mw):
    """Op-driven re-pushes carry isRefresh=true so the JS drops them if they
    race the close animation; user-initiated opens carry false and always
    win."""
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
    assert _detail_evals(tray)[0].endswith(", false)")

    tray._web.reset_log()
    tray._on_bridge_cmd(f"suspend:{cids['apple']}")
    assert _detail_evals(tray)[0].endswith(", true)")


def test_detail_closed_clears_state(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray._on_bridge_cmd(f"card_detail:{cids['apple']}")
    tray._on_bridge_cmd("detail_closed:1")
    assert tray._open_detail is None

    # actions no longer push detail refreshes
    tray._web.reset_log()
    tray._on_bridge_cmd(f"flag_2:{cids['apple']}")
    assert not _detail_evals(tray)


def test_note_detail_for_multicard_note(tray, fake_mw, monkeypatch):
    """A two-card note in notes mode gets a note detail with a preview select."""
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
    assert lead in tray._builder.note_groups

    tray._web.reset_log()
    tray._on_bridge_cmd(f"note_detail:{lead}")
    evals = _detail_evals(tray)
    assert len(evals) == 1
    html = evals[0]
    for expected in ("front side", "overlay-card-select", "Delete note", "2 cards"):
        assert expected in html, f"missing {expected!r}"
    assert tray._open_detail == ("note", lead)


def test_dom_overlay_nav_slides_to_next_unit(qapp, tray, fake_mw):
    """Arrow navigation swaps the overlay to the neighbouring unit (the swap
    goes through the 130ms slide timer)."""
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="a")  # apple, banana, date — eager render
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js(
            f"document.querySelector('[data-cid=\"{cids['apple']}\"]').click(); true"
        )
        page.pump_bridge(tray)
        assert page.run_js(
            "document.getElementById('overlay-card-content')"
            ".textContent.indexOf('apple pie') >= 0"
        )
        page.run_js("overlayNav(1); true")
        page.pump_bridge(tray)  # routes card_detail + replays showCardDetail
        assert page.run_js(
            "document.getElementById('overlay-card-content')"
            ".textContent.indexOf('banana bread') >= 0"
        )
    finally:
        page.close()


def test_dom_click_card_opens_detail(qapp, tray, fake_mw, tmp_path):
    """Full UI flow: click a card frame → detail overlay opens with stats."""
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="banana")  # eager render, one full card
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js(
            f"document.querySelector('[data-cid=\"{cids['banana']}\"]').click(); true"
        )
        page.pump_bridge(tray)
        assert page.run_js(
            "document.getElementById('overlay').classList.contains('open')"
        )
        assert page.run_js(
            "document.querySelectorAll('#overlay-card .detail-stat').length"
        ) >= 5
        page.screenshot(str(tmp_path / "detail_overlay.png"))
        # keep a copy for manual inspection
        page.screenshot("/tmp/card_browser_detail_overlay.png")
    finally:
        page.close()
