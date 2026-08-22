"""Saved searches and search history, persisted in the collection config.

One toolbar button opens a menu of saved searches; picking one applies it,
"Save current search…" names and stores the box's text, and a Remove
submenu deletes entries. Storage is a {name: query} dict in the collection
config, so it syncs with the profile like the collapse state does.

Search history is a most-recent-first list of committed queries (Enter /
focus-out with text in the box). It feeds the search box's completer and a
Recent section in the same menu.
"""
from __future__ import annotations

from aqt import mw
from aqt.qt import QInputDialog, QMenu

_SAVED_SEARCH_KEY = "cardBrowser_saved_searches"
_HISTORY_KEY = "cardBrowser_search_history"
_HISTORY_MAX = 12
_MENU_RECENT_MAX = 6


def load_history(col) -> list[str]:
    """Recent queries, most recent first (empty on bad/missing config)."""
    try:
        saved = col.get_config(_HISTORY_KEY, [])
        if isinstance(saved, list):
            return [q.strip() for q in saved if isinstance(q, str) and q.strip()]
    except Exception:
        pass
    return []


def push_history(col, query: str) -> list[str]:
    """Record a committed *query* (moved to the front, deduped, trimmed)."""
    query = query.strip()
    history = load_history(col)
    if not query:
        return history
    history = [query] + [q for q in history if q.lower() != query.lower()]
    history = history[:_HISTORY_MAX]
    try:
        col.set_config(_HISTORY_KEY, history)
    except Exception:
        pass
    return history


def load_saved_searches(col) -> dict[str, str]:
    """Saved {name: query}, sorted by name (empty on bad/missing config)."""
    try:
        saved = col.get_config(_SAVED_SEARCH_KEY, {})
        if not isinstance(saved, dict):
            return {}
        return dict(sorted(saved.items(), key=lambda kv: kv[0].lower()))
    except Exception:
        return {}


def _store(col, saved: dict[str, str]) -> None:
    col.set_config(_SAVED_SEARCH_KEY, saved)


def open_saved_search_menu(widget, anchor_btn) -> None:
    """Build and show the saved-searches menu under *anchor_btn*.

    *widget* is the CardBrowserWidget (provides _card_search + _apply_filters).
    """
    col = mw.col
    if col is None:
        return
    saved = load_saved_searches(col)
    menu = QMenu(widget)

    def apply_query(query: str) -> None:
        widget._card_search.setText(query)
        widget._apply_filters()  # immediate — don't wait out the debounce

    for name, query in saved.items():
        act = menu.addAction(name)
        act.setToolTip(query)
        act.triggered.connect(lambda _=False, q=query: apply_query(q))
    if saved:
        menu.addSeparator()

    # Recent committed queries that aren't already saved under a name.
    saved_queries = {q.lower() for q in saved.values()}
    recent = [
        q for q in load_history(col) if q.lower() not in saved_queries
    ][:_MENU_RECENT_MAX]
    if recent:
        menu.addSection("Recent")
        for query in recent:
            act = menu.addAction(query)
            act.triggered.connect(lambda _=False, q=query: apply_query(q))
        menu.addSeparator()

    save_act = menu.addAction("Save current search…")
    save_act.setEnabled(bool(widget._card_search.text().strip()))
    save_act.triggered.connect(lambda: _save_current(widget, col))

    if saved:
        remove_menu = menu.addMenu("Remove")
        for name in saved:
            act = remove_menu.addAction(name)
            act.triggered.connect(lambda _=False, n=name: _remove(col, n))

    menu.exec(anchor_btn.mapToGlobal(anchor_btn.rect().bottomLeft()))


def _save_current(widget, col) -> None:
    query = widget._card_search.text().strip()
    if not query:
        return
    name, ok = QInputDialog.getText(
        widget, "Save Search", "Name for this search:", text=query[:40]
    )
    name = name.strip()
    if not ok or not name:
        return
    saved = load_saved_searches(col)
    saved[name] = query
    _store(col, saved)


def _remove(col, name: str) -> None:
    saved = load_saved_searches(col)
    saved.pop(name, None)
    _store(col, saved)
