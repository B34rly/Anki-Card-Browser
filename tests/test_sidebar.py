"""Sidebar deck tree: collapse persistence and name-filter behaviour.

The sidebar's expansion state is persisted per collection (key
cardBrowser_sidebar_collapsed, separate from the tray's set) and restored on
every populate; the name filter's match-expansion is temporary.
"""
from __future__ import annotations

from conftest import addon_module, deck_node

_CFG_KEY = "cardBrowser_sidebar_collapsed"


def _make_tree(fake_mw):
    sidebar = addon_module("decks.sidebar")
    w = sidebar.DeckTree()
    w.populate(deck_node(fake_mw.col, "Parent"), "Parent")
    return w


def _saved(col) -> set[int]:
    return set(col.get_config(_CFG_KEY, []))


def test_collapse_persists_across_populate(qapp, fake_mw):
    col = fake_mw.col
    col.decks.id("Parent::Alpha::Deep")  # give Alpha a child worth collapsing
    alpha_did = col.decks.id_for_name("Parent::Alpha")

    w = _make_tree(fake_mw)
    item = w._find_item(alpha_did)
    assert item.isExpanded()  # default: everything open

    item.setExpanded(False)  # user collapse → persisted
    assert alpha_did in _saved(col)

    w2 = _make_tree(fake_mw)  # fresh widget = reopen/restart
    assert not w2._find_item(alpha_did).isExpanded()

    w2._find_item(alpha_did).setExpanded(True)  # user expand → un-persisted
    assert alpha_did not in _saved(col)


def test_populate_does_not_write_state(qapp, fake_mw):
    """Programmatic expansion during populate must not touch the config."""
    col = fake_mw.col
    col.decks.id("Parent::Alpha::Deep")
    alpha_did = col.decks.id_for_name("Parent::Alpha")
    col.set_config(_CFG_KEY, [alpha_did])

    w = _make_tree(fake_mw)
    assert not w._find_item(alpha_did).isExpanded()
    assert _saved(col) == {alpha_did}  # unchanged by the restore pass


def test_filter_expansion_is_temporary(qapp, fake_mw):
    col = fake_mw.col
    col.decks.id("Parent::Alpha::Deep")
    alpha_did = col.decks.id_for_name("Parent::Alpha")

    w = _make_tree(fake_mw)
    w._find_item(alpha_did).setExpanded(False)
    assert alpha_did in _saved(col)

    w.filter("deep")  # match inside Alpha → visually expanded
    assert w._find_item(alpha_did).isExpanded()
    assert alpha_did in _saved(col)  # ...but not persisted

    w.filter("")  # clearing restores the saved state, not expand-all
    assert not w._find_item(alpha_did).isExpanded()
    alpha_item = w._find_item(alpha_did)
    assert not alpha_item.isHidden()
