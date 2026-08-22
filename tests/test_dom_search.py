"""Level-3 DOM test: search-term highlighting (web/js/45_search.js).

Loads the tray's real rendered page in an offscreen web engine and checks the
live DOM, mirroring tests/test_multiselect.py's DOM patterns.
"""
from __future__ import annotations

from webview_harness import DomPage


def test_dom_highlights_substring_search_matches(qapp, tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="banana")  # small result set -> eager render
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        hits = page.run_js("document.querySelectorAll('mark.search-hit').length")
        assert hits >= 1
        mark_text = page.run_js(
            "document.querySelector('mark.search-hit').textContent.toLowerCase()"
        )
        assert mark_text == "banana"
        # The mark wraps the match in place — surrounding card text (and the
        # rest of the field) is unchanged, not stripped or re-parsed.
        content = page.run_js(
            f"document.querySelector('[data-cid=\"{cids['banana']}\"] .card-content').textContent"
        )
        assert "banana bread" in content
    finally:
        page.close()


def test_dom_no_highlighting_for_anki_query(qapp, tray, fake_mw):
    """Anki-syntax queries (tag:/is:/…) are expressions, not literal matched
    text — _searchTerm is baked blank for them, so nothing gets marked."""
    tray.set_filters(search_text="tag:baking")
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        hits = page.run_js("document.querySelectorAll('mark.search-hit').length")
        assert hits == 0
    finally:
        page.close()
