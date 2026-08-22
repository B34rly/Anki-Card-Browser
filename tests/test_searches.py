"""Search history: most-recent-first, deduped, trimmed persistence.

load_history/push_history (viewer/searches.py) operate directly on the
collection config under key cardBrowser_search_history — no widget needed,
so these run against the plain `col` fixture.
"""
from __future__ import annotations

from conftest import addon_module

searches = addon_module("viewer.searches")

_HISTORY_KEY = "cardBrowser_search_history"


# ── load_history ──


def test_load_history_empty_by_default(col):
    assert searches.load_history(col) == []


def test_load_history_tolerates_non_list_config(col):
    col.set_config(_HISTORY_KEY, "not-a-list")
    assert searches.load_history(col) == []


def test_load_history_tolerates_config_exception(col, monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(col, "get_config", _raise)
    assert searches.load_history(col) == []


def test_load_history_drops_blank_entries(col):
    col.set_config(_HISTORY_KEY, ["tag:baking", "  ", "is:due"])
    assert searches.load_history(col) == ["tag:baking", "is:due"]


# ── push_history ──


def test_push_history_adds_to_front(col):
    searches.push_history(col, "tag:baking")
    result = searches.push_history(col, "is:due")
    assert result == ["is:due", "tag:baking"]
    assert searches.load_history(col) == ["is:due", "tag:baking"]


def test_push_history_case_insensitive_dedup_moves_to_front(col):
    searches.push_history(col, "banana")
    searches.push_history(col, "tag:baking")
    result = searches.push_history(col, "BANANA")
    assert result == ["BANANA", "tag:baking"]  # re-pushed casing wins, moved up


def test_push_history_blank_push_is_ignored(col):
    searches.push_history(col, "tag:baking")
    result = searches.push_history(col, "   ")
    assert result == ["tag:baking"]
    assert searches.load_history(col) == ["tag:baking"]


def test_push_history_strips_whitespace(col):
    result = searches.push_history(col, "  tag:baking  ")
    assert result == ["tag:baking"]


def test_push_history_trims_to_twelve(col):
    for i in range(15):
        searches.push_history(col, f"query{i}")
    result = searches.load_history(col)
    assert len(result) == 12
    # Most recent 12 distinct pushes survive, most-recent-first.
    assert result == [f"query{i}" for i in range(14, 2, -1)]


def test_push_history_tolerates_bad_existing_config(col):
    col.set_config(_HISTORY_KEY, "not-a-list")
    result = searches.push_history(col, "tag:baking")
    assert result == ["tag:baking"]


def test_push_history_tolerates_store_exception(col, monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(col, "set_config", _raise)
    # Storing fails silently, but the (unpersisted) computed list is returned.
    result = searches.push_history(col, "tag:baking")
    assert result == ["tag:baking"]
    assert searches.load_history(col) == []
