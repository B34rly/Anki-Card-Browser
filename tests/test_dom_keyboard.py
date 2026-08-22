"""Level-3 DOM tests: keyboard grid navigation (web/js/75_keyboard.js).

Drives real keydown events against the tray's rendered page in an offscreen
web engine: the focus ring, Enter/Space, single-key actions through the bulk
bridge path, and the `?` shortcut cheat-sheet.
"""
from __future__ import annotations

import json

from webview_harness import DomPage


def _press(page, key, **mods):
    opts = {"key": key, "bubbles": True, "cancelable": True}
    opts.update(mods)
    page.run_js(
        f"document.dispatchEvent(new KeyboardEvent('keydown', {json.dumps(opts)})); true"
    )


def _focus_id(page):
    return page.run_js("_kbFocusId")


def test_dom_arrows_move_focus_ring(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        assert page.run_js("document.querySelectorAll('.kb-focus').length") == 0

        _press(page, "ArrowRight")
        assert page.run_js("document.querySelectorAll('.kb-focus').length") == 1
        first = _focus_id(page)
        assert first

        _press(page, "ArrowRight")
        second = _focus_id(page)
        assert second != first
        assert page.run_js("document.querySelectorAll('.kb-focus').length") == 1

        _press(page, "ArrowLeft")
        assert _focus_id(page) == first

        _press(page, "Escape")
        assert page.run_js("document.querySelectorAll('.kb-focus').length") == 0
    finally:
        page.close()


def test_dom_enter_opens_focused_detail(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        _press(page, "ArrowRight")
        focused = _focus_id(page)
        page.drain_pycmds()
        _press(page, "Enter")
        assert f"card_detail:{focused}" in page.drain_pycmds()
    finally:
        page.close()


def test_dom_space_toggles_selection(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        _press(page, "ArrowRight")
        focused = _focus_id(page)
        _press(page, " ")
        assert page.run_js("_selected.size") == 1
        assert page.run_js(f"_selected.has('{focused}')")
        _press(page, " ")
        assert page.run_js("_selected.size") == 0
    finally:
        page.close()


def test_dom_action_key_routes_through_bulk(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        _press(page, "ArrowRight")
        focused = _focus_id(page)
        page.drain_pycmds()
        _press(page, "s")
        assert f"bulk:suspend:{focused}" in page.drain_pycmds()
        _press(page, "3")
        assert f"bulk:flag_3:{focused}" in page.drain_pycmds()
    finally:
        page.close()


def test_dom_action_key_prefers_active_selection(qapp, tray, fake_mw):
    """With a selection active, action keys act on the whole selection (the
    focused unit is just the toggle cue), mirroring the selection bar."""
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(true); true")
        _press(page, "ArrowRight")
        _press(page, " ")
        _press(page, "ArrowRight")
        _press(page, " ")
        assert page.run_js("_selected.size") == 2
        page.drain_pycmds()
        _press(page, "s")
        cmds = [c for c in page.drain_pycmds() if c.startswith("bulk:suspend:")]
        assert len(cmds) == 1
        assert len(cmds[0].split(":", 2)[2].split(",")) == 2
    finally:
        page.close()


def test_dom_action_keys_ignored_in_view_mode(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js("setEditMode(false); true")
        _press(page, "ArrowRight")
        assert _focus_id(page)  # navigation still works read-only
        page.drain_pycmds()
        _press(page, "s")
        _press(page, "Delete")
        assert not [c for c in page.drain_pycmds() if c.startswith("bulk:")]
    finally:
        page.close()


def test_dom_help_sheet_toggles(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        _press(page, "?", shiftKey=True)
        assert page.run_js(
            "document.getElementById('kb-help').classList.contains('open')"
        )
        # While the sheet is open other keys are swallowed…
        _press(page, "ArrowRight")
        assert page.run_js("document.querySelectorAll('.kb-focus').length") == 0
        # …and Escape closes it.
        _press(page, "Escape")
        assert not page.run_js(
            "document.getElementById('kb-help').classList.contains('open')"
        )
    finally:
        page.close()


def test_dom_keys_ignored_while_typing(qapp, tray, fake_mw):
    page = DomPage(tray._web.page_html, connected=True)
    try:
        page.wait_loaded()
        page.run_js(
            "var i = document.createElement('input');"
            "document.body.appendChild(i); i.focus(); true"
        )
        _press(page, "ArrowRight")
        assert page.run_js("document.querySelectorAll('.kb-focus').length") == 0
    finally:
        page.close()
