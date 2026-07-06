"""Level-3 DOM tests: the real tray page in a real (offscreen) web engine.

These exercise the JS side of lazy loading end-to-end, including the
bridge-race regression that left search results blank.
"""
from __future__ import annotations

import pytest

from conftest import addon_module
from webview_harness import DomPage

builder_mod = addon_module("tray.builder")


@pytest.fixture
def filtered_page_html(tray, fake_mw, monkeypatch):
    """Page HTML for a search render forced onto the lazy-placeholder path."""
    monkeypatch.setattr(builder_mod, "EAGER_RENDER_LIMIT", 0)
    tray.set_filters(search_text="banana")
    return tray._web.page_html


def test_lazy_load_round_trip_fills_placeholder(qapp, tray, fake_mw, filtered_page_html):
    page = DomPage(filtered_page_html, connected=True)
    try:
        page.wait_loaded()
        assert page.run_js("document.querySelectorAll('.card-placeholder[data-lazy]').length") == 1
        page.pump_bridge(tray)
        assert page.run_js("document.querySelectorAll('.card-placeholder[data-lazy]').length") == 0
        assert page.run_js("document.body.textContent.indexOf('banana bread') >= 0")
    finally:
        page.close()


def test_lazy_load_survives_late_bridge(qapp, tray, fake_mw, filtered_page_html):
    """Regression: pycmd connects *after* the IntersectionObserver flush.

    Before the fix, _flushLazy dropped the batch keys when pycmd wasn't
    callable yet, and the placeholders stayed blank forever."""
    page = DomPage(filtered_page_html, connected=False)
    try:
        page.wait_loaded()
        # Observer has fired and tried to flush while disconnected.
        page.connect_bridge()
        page.pump_bridge(tray)
        assert page.run_js("document.querySelectorAll('.card-placeholder[data-lazy]').length") == 0
        assert page.run_js("document.body.textContent.indexOf('banana bread') >= 0")
    finally:
        page.close()


def test_eager_search_page_needs_no_bridge(qapp, tray, fake_mw):
    """Search mode: results are fully rendered even if the bridge never
    connects — nothing left to lazy-load."""
    tray.set_filters(search_text="banana")
    page = DomPage(tray._web.page_html, connected=False)
    try:
        page.wait_loaded()
        assert page.run_js("document.querySelectorAll('.card-placeholder[data-lazy]').length") == 0
        assert page.run_js("document.body.textContent.indexOf('banana bread') >= 0")
    finally:
        page.close()
