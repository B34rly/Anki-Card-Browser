"""In-page toast feedback (replaced Anki's native tooltip window, which
looked foreign floating over the styled grid)."""
from __future__ import annotations

from webview_harness import DomPage


def test_action_success_shows_toast(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"suspend:{cids['apple']}")
    assert 'showToast("Suspended 1 card")' in tray._web.evals


def test_move_toast_names_the_target_deck(tray, fake_mw):
    col = fake_mw.col
    cids = col._test_cids
    beta_did = col.decks.id_for_name("Parent::Beta")
    tray._web.reset_log()
    tray._on_bridge_cmd(f"move_cards:{beta_did}:{cids['cherry']}")
    assert 'showToast("Moved 1 card to Parent::Beta")' in tray._web.evals


def test_dom_toast_appears_with_message(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js('showToast("2 cards suspended"); true')
        assert page.run_js(
            "document.getElementById('toast').classList.contains('visible')"
        )
        assert page.run_js(
            "document.getElementById('toast').textContent"
        ) == "2 cards suspended"
    finally:
        page.close()
