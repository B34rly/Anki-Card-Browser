"""Level-3 DOM tests for the state-sync batch (ROADMAP §4 findings 1/2/6/9):
targeted DOM updates must keep the live selection and the detail overlay
coherent — no stale selection entries, no torn note groups, no overlay
reopened by a refresh that raced the close animation.
"""
from __future__ import annotations

from webview_harness import DomPage, js_str


def _select_unit(page, cid: int) -> None:
    page.run_js(
        f"toggleSelect(document.querySelector('[data-cid=\"{cid}\"]')); true"
    )


def _replay_evals(page, tray) -> None:
    """Replay the tray's queued eval() calls into the live page."""
    for js in tray._web.evals:
        page.run_js(js + "; true")
    tray._web.evals.clear()


def test_remove_card_purges_selection(qapp, tray, fake_mw):
    """Regression: removeCard left the id in _selected — the bar kept a wrong
    count, plain clicks stayed in toggle mode, and a later drag moved cards
    that were no longer on the page."""
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="a")  # eager render: apple, banana, date
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        for key in ("apple", "banana"):
            _select_unit(page, cids[key])
        assert page.run_js("_selected.size") == 2

        page.run_js(f"removeCard({cids['apple']}); true")
        assert page.run_js("_selected.size") == 1
        assert page.run_js(
            "document.getElementById('selection-count').textContent"
        ) == "1 selected"

        page.run_js(f"removeCard({cids['banana']}); true")
        assert page.run_js("_selected.size") == 0
        assert not page.run_js(
            "document.getElementById('selection-bar').classList.contains('open')"
        )
    finally:
        page.close()


def test_remove_inner_lead_card_keeps_group_frame(qapp, tray, fake_mw):
    """Regression: the shared unit lookup preferred data-group-lead, so
    removing the *inner* card that leads its note group tore out the whole
    group frame (the surviving cards vanished until the next render)."""
    group_html = (
        '<div class="note-group" data-group-lead="901">'
        '<div class="note-cards-body open">'
        '<div class="card-frame" data-cid="901"></div>'
        '<div class="card-frame" data-cid="902"></div>'
        "</div></div>"
    )
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js(
            "document.querySelector('.deck-cards')"
            f".insertAdjacentHTML('beforeend', {js_str(group_html)}); true"
        )
        page.run_js("removeCard(901); true")
        assert page.run_js("!!document.querySelector('[data-group-lead=\"901\"]')")
        assert not page.run_js("!!document.querySelector('[data-cid=\"901\"]')")
        assert page.run_js("!!document.querySelector('[data-cid=\"902\"]')")
        # group ops still remove the whole frame
        page.run_js("removeGroup(901); true")
        assert not page.run_js("!!document.querySelector('[data-group-lead=\"901\"]')")
    finally:
        page.close()


def test_section_rebuild_keeps_selection(qapp, tray, fake_mw):
    """Regression: replaceSection swapped in Python-built HTML that knows
    nothing of the live selection, silently dropping the highlight while the
    selection stayed active."""
    col = fake_mw.col
    cids = col._test_cids
    alpha_did = col.decks.id_for_name("Parent::Alpha")
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.pump_bridge(tray)  # lazy fills land; cherry becomes a real frame
        _select_unit(page, cids["cherry"])
        assert page.run_js("_selected.size") == 1

        tray._web.evals.clear()
        tray.refresh_section(alpha_did)
        _replay_evals(page, tray)

        assert page.run_js(
            f"document.querySelector('[data-cid=\"{cids['cherry']}\"]')"
            ".classList.contains('selected')"
        )
        assert page.run_js("_selected.size") == 1
    finally:
        page.close()


def test_lazy_fill_keeps_selection(qapp, tray, fake_mw):
    """A selected unit that collapsed to a placeholder (its data-lazy key is
    the unit id) comes back selected when the placeholder fills."""
    cids = fake_mw.col._test_cids
    page = DomPage(tray._web.page_html, connected=True)  # all placeholders
    try:
        page.wait_loaded()
        page.run_js(f"_selected.add('{cids['apple']}'); updateSelectionBar(); true")

        tray._web.evals.clear()
        tray._on_bridge_cmd(f"lazy_load:{cids['apple']}")
        _replay_evals(page, tray)

        assert page.run_js(
            f"document.querySelector('[data-cid=\"{cids['apple']}\"]')"
            ".classList.contains('selected')"
        )
    finally:
        page.close()


def test_overlay_refresh_during_close_is_dropped(qapp, tray, fake_mw):
    """[RACE] Regression: a detail refresh landing during the close animation
    reopened an overlay Python already believed was closed — it then never
    refreshed or closed again. Refresh pushes only apply to the unit shown;
    user-initiated opens always win."""
    cids = fake_mw.col._test_cids
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js(f"showCardDetail('<p>x</p>', {cids['apple']}, false); true")
        assert page.run_js(
            "document.getElementById('overlay').classList.contains('open')"
        )

        # while open, a refresh for the shown unit still applies
        page.run_js(f"showCardDetail('<p>q</p>', {cids['apple']}, true); true")
        assert page.run_js(
            "document.getElementById('overlay-card-content').textContent"
        ) == "q"

        # a refresh racing the close animation is dropped
        page.run_js("closeOverlay(); true")
        page.run_js(f"showCardDetail('<p>y</p>', {cids['apple']}, true); true")
        assert page.run_js("_overlayId === null")
        assert not page.run_js(
            "document.getElementById('overlay').classList.contains('visible')"
        )

        # a fresh user-initiated open still works
        page.run_js(f"showCardDetail('<p>z</p>', {cids['banana']}, false); true")
        assert page.run_js(
            "document.getElementById('overlay').classList.contains('open')"
        )
        assert page.run_js(f"_overlayId === {cids['banana']}")
    finally:
        page.close()
