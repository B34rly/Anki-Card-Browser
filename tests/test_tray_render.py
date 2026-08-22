"""CardTray rendering + bridge tests against a real collection (FakeWebView).

These prove the level-2 pattern: real Collection, real CardTray, fake webview.
"""
from __future__ import annotations

import json
import re

from conftest import addon_module, deck_node

card_state = addon_module("core.card_state")


def _placeholder_keys(html: str) -> list[int]:
    return [int(k) for k in re.findall(r'data-lazy="(\d+)"', html)]


def test_initial_render_has_placeholder_per_card(tray, fake_mw):
    cids = fake_mw.col._test_cids
    keys = _placeholder_keys(tray._web.page_html)
    assert sorted(keys) == sorted(cids.values())


def test_lazy_load_fills_cards(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"lazy_load:{cids['apple']},{cids['banana']}")
    fills = tray._web.evals_matching("fillCards(")
    assert len(fills) == 1
    payload = json.loads(fills[0][len("fillCards("):-1])
    assert set(payload) == {str(cids["apple"]), str(cids["banana"])}
    assert "apple pie" in payload[str(cids["apple"])]
    assert f'data-cid="{cids["banana"]}"' in payload[str(cids["banana"])]


def test_search_renders_matches_eagerly(tray, fake_mw):
    """Small filtered result sets render full card HTML up front (search
    mode) — no placeholders left to lazy-load, so nothing can stay blank."""
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="banana")
    html = tray._web.page_html
    assert _placeholder_keys(html) == []
    assert f'data-cid="{cids["banana"]}"' in html
    assert "banana bread" in html
    # Non-matching cards and sections without hits are dropped entirely
    assert f'data-cid="{cids["apple"]}"' not in html
    assert "Alpha" not in html


def test_search_above_eager_limit_keeps_placeholders(tray, fake_mw, monkeypatch):
    """Above the eager limit, filtered renders fall back to lazy placeholders
    and the lazy round-trip still fills them."""
    builder_mod = addon_module("tray.builder")
    monkeypatch.setattr(builder_mod, "EAGER_RENDER_LIMIT", 0)
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="banana")
    assert _placeholder_keys(tray._web.page_html) == [cids["banana"]]

    tray._web.reset_log()
    tray._on_bridge_cmd(f"lazy_load:{cids['banana']}")
    fills = tray._web.evals_matching("fillCards(")
    assert len(fills) == 1
    assert "banana bread" in fills[0]


def test_section_rebuild_stays_eager_for_small_sections(tray, fake_mw):
    """Regression: a targeted section rebuild inherited the page's lazy
    decision, collapsing already-loaded cards back into short placeholders
    and throwing the viewport. Small sections rebuild with full card HTML."""
    col = fake_mw.col
    cids = col._test_cids
    alpha_did = col.decks.id_for_name("Parent::Alpha")
    tray._web.reset_log()
    tray.refresh_section(alpha_did)
    sections = tray._web.evals_matching(f"replaceSection({alpha_did}")
    assert len(sections) == 1
    assert "data-lazy" not in sections[0]
    assert "cherry cake" in sections[0]
    assert f'data-cid=\\"{cids["cherry"]}\\"' in sections[0]  # JSON-escaped


def test_section_rebuild_above_limit_keeps_placeholders(tray, fake_mw, monkeypatch):
    """Genuinely huge sections still rebuild lazily."""
    builder_mod = addon_module("tray.builder")
    monkeypatch.setattr(builder_mod, "EAGER_RENDER_LIMIT", 0)
    alpha_did = fake_mw.col.decks.id_for_name("Parent::Alpha")
    tray._web.reset_log()
    tray.refresh_section(alpha_did)
    sections = tray._web.evals_matching(f"replaceSection({alpha_did}")
    assert len(sections) == 1
    assert "data-lazy" in sections[0]


def _rendered_cids(html: str) -> set[int]:
    return {int(c) for c in re.findall(r'data-cid="(\d+)"', html)}


def test_state_chip_filter(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray.set_filters(active_chips={"due"})
    assert _rendered_cids(tray._web.page_html) == {cids["banana"]}

    tray.set_filters(active_chips={"new"})
    assert _rendered_cids(tray._web.page_html) == {cids["apple"], cids["elder"]}


def test_anki_search_syntax(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray.set_filters(search_text="tag:baking")
    assert _rendered_cids(tray._web.page_html) == {cids["banana"], cids["date"]}

    tray.set_filters(search_text="is:suspended")
    assert _rendered_cids(tray._web.page_html) == {cids["date"]}

    # A colon query that Anki can't parse falls back to substring search
    tray.set_filters(search_text="notakey:banana")
    assert _rendered_cids(tray._web.page_html) == set()


def test_suspend_action_updates_card(tray, fake_mw):
    cids = fake_mw.col._test_cids
    tray._web.reset_log()
    tray._on_bridge_cmd(f"suspend:{cids['apple']}")
    card = fake_mw.col.get_card(cids["apple"])
    assert card.queue == -1  # QUEUE_TYPE_SUSPENDED
    assert tray._web.evals_matching("replaceCard(")


def test_set_all_collapsed_persists_and_rerenders(tray, fake_mw):
    col = fake_mw.col
    alpha = col.decks.id_for_name("Parent::Alpha")
    beta = col.decks.id_for_name("Parent::Beta")

    pages_before = len(tray._web.pages)
    tray.set_all_collapsed(True)
    saved = set(col.get_config("cardBrowser_collapsed_decks", []))
    assert {alpha, beta} <= saved
    assert len(tray._web.pages) == pages_before + 1

    tray.set_all_collapsed(False)
    saved = set(col.get_config("cardBrowser_collapsed_decks", []))
    assert not ({alpha, beta} & saved)


def test_tag_mutation_refreshes_dropdown_options(tray, fake_mw, monkeypatch):
    """Regression: tags were emitted only on deck change, so a tag added via
    the menu never appeared in the filter dropdown until deck switch."""
    col = fake_mw.col
    cids = col._test_cids
    emitted: list[list] = []
    tray.tags_updated.connect(emitted.append)
    monkeypatch.setattr(
        addon_module("tray.actions").QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("freshtag", True)),
    )

    tray._on_bridge_cmd(f"add_tag:{cids['apple']}")

    assert emitted and "freshtag" in emitted[-1]


def test_filter_tag_bridge_emits_signal(tray, fake_mw):
    got: list[str] = []
    tray.tag_filter_requested.connect(got.append)
    tray._on_bridge_cmd("filter_tag:baking")
    assert got == ["baking"]


def test_collapse_state_persists(tray, fake_mw):
    alpha_did = fake_mw.col.decks.id_for_name("Parent::Alpha")
    tray._on_bridge_cmd(f"set_collapsed:{alpha_did}:1")
    saved = fake_mw.col.get_config("cardBrowser_collapsed_decks", [])
    assert alpha_did in saved
    tray._on_bridge_cmd(f"set_collapsed:{alpha_did}:0")
    saved = fake_mw.col.get_config("cardBrowser_collapsed_decks", [])
    assert alpha_did not in saved


# ── match_count_updated ──


def test_match_count_updated_on_filtered_render(tray, fake_mw):
    seen = []
    tray.match_count_updated.connect(lambda v, t, a: seen.append((v, t, a)))

    tray.set_filters(search_text="banana")
    assert seen[-1] == (1, 5, True)


def test_match_count_updated_on_cleared_filters(tray, fake_mw):
    seen = []
    tray.set_filters(search_text="banana")  # filtered first, before connecting
    tray.match_count_updated.connect(lambda v, t, a: seen.append((v, t, a)))

    tray.set_filters()  # clears every filter
    assert seen[-1] == (5, 5, False)


# ── notetypes_updated ──


def test_notetypes_updated_emitted_on_deck_tree_render(tray, fake_mw):
    seen = []
    tray.notetypes_updated.connect(seen.append)

    tray.set_deck_tree(deck_node(fake_mw.col, "Parent"), "Parent")

    assert len(seen) == 1
    pairs = seen[0]
    assert len(pairs) == 1
    _mid, name = pairs[0]
    assert name == "Basic"


# ── bridge: focus_search / clear_filters ──


def test_focus_search_bridge_emits_signal(tray, fake_mw):
    seen = []
    tray.search_focus_requested.connect(lambda: seen.append(True))
    tray._on_bridge_cmd("focus_search:1")
    assert seen == [True]


def test_clear_filters_bridge_emits_signal(tray, fake_mw):
    seen = []
    tray.clear_filters_requested.connect(lambda: seen.append(True))
    tray._on_bridge_cmd("clear_filters:1")
    assert seen == [True]


# ── page baking: _searchTerm and the empty state ──


def test_page_bakes_search_term_for_substring_search(tray, fake_mw):
    tray.set_filters(search_text="banana")
    assert 'var _searchTerm = "banana"' in tray._web.page_html


def test_page_bakes_blank_search_term_for_anki_query(tray, fake_mw):
    tray.set_filters(search_text="tag:baking")
    assert 'var _searchTerm = ""' in tray._web.page_html


def test_zero_match_search_renders_empty_state(tray, fake_mw):
    tray.set_filters(search_text="zzznothing")
    html = tray._web.page_html
    assert 'class="empty-state"' in html
    assert "zzznothing" in html  # the (escaped) query is echoed in the message


def test_normal_match_search_has_no_empty_state(tray, fake_mw):
    tray.set_filters(search_text="banana")
    # The page's <style> block always defines the .empty-state CSS rule;
    # only the rendered <div class="empty-state"> marks a zero-match page.
    assert '<div class="empty-state">' not in tray._web.page_html
