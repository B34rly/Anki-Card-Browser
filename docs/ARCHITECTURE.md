# Architecture

> Anki Card Browser add-on — a visual card viewer accessible from the main toolbar.

## Overview

The add-on adds a **"Cards"** button to Anki's top toolbar. Clicking it opens the
Card Browser, which displays all cards in your decks as a visual grid organized by
the deck hierarchy, with lazy loading, card-state indicators, filtering/sorting,
multiselect bulk actions, and both view and edit modes.

The browser can open in one of two **host modes** (set by the `mode` config key),
both wrapping the same `CardBrowserWidget`:

- **Embedded** (default) — the widget is placed into Anki's main window layout and
  Anki's own content (`mw.web` / `mw.bottomWeb`) is hidden. Clicking any other
  toolbar button returns to Anki.
- **Window** — the widget lives in a standalone floating `QMainWindow`.

## File Map

```
card-browser/
├── __init__.py             Entry point — adds the "Cards" toolbar button; clears caches on collection load
├── core/                   Collection data + domain logic — no Qt, no HTML
│   ├── card_data.py          Bulk SQL, content/tag/search queries, IO notetype detection, IO HTML parsing
│   ├── card_state.py         Card state classification — new/learn/review, countdown, colours, filter/sort
│   └── note_grouping.py      Note-level grouping + state summaries for notes display mode
├── rendering/              Pure HTML builders — no Qt, no collection mutation
│   ├── frames.py              Card frame chrome, flag/tag/menu HTML, deck-path labels, build_selection_bar
│   ├── io_cards.py            Image Occlusion SVG masks + the grouped IO card
│   ├── notes.py               Note field tables, cloze styling, multi-card note groups
│   ├── detail.py              Detail-overlay markup: Q/A toggle, action bar, chrome + stats
│   └── __init__.py            Re-exports the public builder surface (`from ..rendering import …`)
├── decks/                  The deck side of the browser
│   ├── data.py                Pure data helpers over col.decks — deck tree queries
│   ├── ops.py                 Prompt-driven deck mutations (add/rename/delete/add-cards), shared by sidebar + tray
│   └── sidebar.py             DeckTree widget (QTreeWidget) — navigation, filtering, context menu
├── tray/                   The card tray: webview + Python↔JS bridge
│   ├── tray.py                 CardTray widget — state contract, bridge dispatch table, detail orchestration
│   ├── render.py               RenderMixin — full renders, section rebuilds, header counts, lazy-load serving
│   ├── refresh.py              RefreshMixin — targeted refreshes, refresh_note, sync_external_changes, _refresh_modified
│   ├── builder.py              PageBuilder + RenderContext + EAGER_RENDER_LIMIT + IO-group helpers
│   ├── details.py              Detail-overlay HTML assembly (single card / IO group / note group)
│   ├── actions.py              Card mutations + prompt dialogs (scheduling, tags, change-deck, delete)
│   ├── filters.py              FilterState + compute_allowed / order_cids
│   ├── sync.py                 ChangeTracker — membership snapshot + mod-time watermark
│   ├── assets.py               Loads web/tray.css and the concatenated web/js/*.js
│   └── webview.py              TrayWebView — drag-source gating
├── viewer/                 The outer widget + host modes
│   ├── widget.py               CardBrowserWidget (layout, toolbar, filters, mode, auto-refresh)
│   ├── filter_bar.py           Advanced filter panel + criteria builders + active-filter chips
│   ├── searches.py             Saved searches (☆ menu) — named queries in the collection config
│   ├── hosts.py                CardBrowserWindow / EmbeddedBrowser + open_card_browser()
│   └── style.py                Qt stylesheet + toolbar SVG icons
├── web/                    CSS + JS for the webview
│   ├── tray.css                Styles
│   └── js/                     10_mode_menus.js … 90_toast.js — concatenated in name order into one script
├── docs/
│   ├── ARCHITECTURE.md      This file
│   └── CONTRIBUTING.md      Code walkthrough for contributors
└── tests/                  Three-level pytest suite (181 tests, see Testing below)
```

## Module Responsibilities

### `__init__.py` (entry point)
Registers a `gui_hooks.top_toolbar_did_init_links` callback that inserts a "Cards"
link into Anki's toolbar (calling `open_card_browser()` from `viewer/hosts.py`), and a
`gui_hooks.collection_did_load` callback that clears module-level caches so per-
collection state (IO notetype lookups) never leaks across profile switches.

### `core/` — collection data & domain logic

No Qt, no HTML — plain functions over `col` and dicts, so they're cheap to
unit-test directly.

**`card_state.py`** (state classification)
- `card_state_from_meta(meta, today)` → `"new"`, `"learn"`, `"review-due"`,
  `"review-soon"`, `"review-mid"`, `"review-later"`, or `""`. `today` is required
  (`col.sched.today`).
- `card_countdown_from_meta(meta, today)` → human-readable countdown.
- `build_state_badge(state, countdown)` → badge HTML.
- `get_state_colors()` → CSS custom-property values from Anki's theme.
- `group_flag(flag_values)` → the flag shared by every card in a group, or 0 when
  they disagree (used by IO/note-group rendering and the detail overlay).
- `filter_cards_by_states` / `filter_cards_by_criteria` → matching card-ID sets.
- `sort_cards(card_ids, meta, today, sort_key, reverse)` → sorted IDs (10 modes).
- `STATE_ICONS` / `STATE_PRIORITY` / `FILTER_CHIP_STATES`.

**`card_data.py`** (data access)
- `get_cards_metadata(col, card_ids)` — one chunked SQL join fetching
  `id, type, queue, due, nid, mid, did, factor, ivl, lapses, reps, flags, mod, sfld`.
- `get_card_decks(col, card_ids)` / `get_deck_cards(col, deck_ids)` — cid → deck id
  maps, keyed by card id or by deck id respectively (membership diffing walks the
  indexed `cards.did` column via the latter, so it's far cheaper than looking the
  same cards up by id).
- `get_note_cards(col, note_ids)` — nid → [cids] (one chunked query, not one call
  per note); used to resolve which rendered units a note-level edit touched.
- `search_cards_by_content` / `search_cards_with_anki_query` / `filter_cards_by_tag`
  / `get_tags_for_cards` / `get_flags_for_cards` — chunked queries (shared
  `_query_in_chunks` helper).
- `is_io_mid(col, mid)` — cached Image Occlusion notetype check; `clear_caches()`
  resets the cache on profile change.
- `get_note_fields(col, nid)` / `get_card_template_names(col, nid)` — field-name/
  value pairs and per-card template names, used by the note field table and the
  detail overlay's type line.
- `extract_io_data(answer_html)` — regex extraction of image src + mask shapes
  (including each mask's `ordinal`, so per-mask suspension can be shown).

**`note_grouping.py`**
- `group_cards_by_note(col, card_ids, meta=None)` — ordered `NoteGroup`s (accepts
  pre-fetched metadata to avoid a redundant query).
- `note_state_summary` / `note_summary_counts` — per-note and aggregate counts.

### `rendering/` — pure HTML builders

Split by shape (frames = base card chrome, io_cards = Image Occlusion, notes =
field tables/note groups, detail = the inspector overlay); `rendering/__init__.py`
re-exports the full public surface so consumers just `from ..rendering import
<builder>`.

**`frames.py`**
- `render_normal_card(col, cid)` — full single-card frame.
- `frame_classes` / `build_tag_strip` / `build_flag_indicator` / `build_flag_row` /
  `build_card_menu` — shared chrome used by cards, IO groups and note groups alike.
- `format_deck_path(full_path)` — truncated, leaf-bolded deck-path label.
- `build_selection_bar()` — the fixed bulk-action bar shown during multiselect
  (static page chrome; buttons call `selectionAction()` in JS rather than baking
  in id lists). See *Multiselect*.
- `FLAG_COLORS`.

**`io_cards.py`**
- `build_svg_mask(mask, suspended)` — one SVG shape (rect/ellipse/polygon).
- `build_io_container(img_src, masks, suspended_ordinals)` — image + SVG overlay,
  shared by the grouped IO card and the IO detail view.
- `build_io_card_html(...)` — the full grouped IO card.

**`notes.py`**
- `build_note_fields_table(fields)` — field table with cloze markers styled.
- `build_note_card_count(summary)` — compact per-note state-count span.
- `build_note_group_html(...)` — multi-card note block (identified by
  `data-group-lead`, the lead card id).

**`detail.py`**
- `build_qa_content(question_html, answer_html)` — the Q/A side-toggle block.
- `build_detail_actions(...)` — the overlay's horizontal action bar.
- `build_detail_html(...)` — assembles header, actions, content and stats into the
  full overlay body (the prev/next nav arrows live in the static overlay shell
  built by `tray/render.py::_render_page`, not in this per-detail HTML).
- `build_revlog_table(rows)` — the single-card detail's review-history table
  (last 8 revlog rows, newest first).
- `build_editable_fields(...)` — the detail's in-place field editor: a
  `#detail-fields` section of contenteditable blocks, one per field. In a
  card detail it is the Q/A toggle's third tab (`build_qa_content`'s
  `fields_html`, edit mode only) so the rendered card and its raw fields
  never show at once; in a note detail it is the content itself. Typing
  marks it dirty (revealing the Revert/Save bar); Save/Revert wire to
  `saveNoteEdit()`/`revertNoteEdit()`.

### `decks/` — deck tree queries, mutations, sidebar

**`data.py`** — stateless functions over `mw.col.decks`:
`get_top_level_decks()` (`[(deck_id, name), ...]` for the combo box) and
`find_deck_node(deck_id)` (DFS lookup of a `DeckTreeNode`).

**`ops.py`** — prompt-driven flows shared by the sidebar context menu and the
tray's header "+" menus, so the dialogs and validation exist once:
`open_add_cards` (via Anki's dialog manager), `prompt_new_subdeck`,
`prompt_rename_deck`, `confirm_delete_deck`. Each returns True when the
collection changed so the caller can refresh.

**`sidebar.py`** — **`DeckTree`**, a `QWidget` wrapping a `QTreeWidget`.
- Populates from an Anki `DeckTreeNode`; emits `deck_selected(deck_id, full_name)`.
- Text filtering shows only matching branches.
- Context menu (edit mode): "Add card", "Add child subdeck", "Add sibling subdeck"
  (siblings only for non-root decks), "Rename deck", "Delete deck".

### `tray/` — the card tray widget

**`tray.py`** — **`CardTray`**, deliberately thin: it owns the widget/webview, the
state shared by its two implementation halves (`render.RenderMixin` builds and
pushes page content; `refresh.RefreshMixin` applies targeted updates), and the
bridge dispatch that routes JS `pycmd` messages to them. HTML construction lives
in `builder.py`/`details.py`; collection mutations in `actions.py`; external-change
snapshots in `sync.py`. State contract (owned here, used by both mixins):
`_web` (`TrayWebView`), `_builder` (`PageBuilder`), `_filters` (`FilterState`),
`_tracker` (`ChangeTracker`), `_collapsed_decks`, `_tree_root`/`_tree_name`,
`_scroll_anchor`, `_eager`, `_edit_mode`, `_open_detail`.
- **`_on_bridge_cmd(cmd)`**: dispatches `pycmd` messages via the `_BRIDGE` table
  (deck/card/detail/multiselect handlers); per-card/flag actions not in the table
  (any `CARD_ACTIONS` name, or `flag_N`) are matched separately and routed to
  `_on_card_action`.
- **Card-level handlers**: `_on_card_action` (single unit), `_on_bulk_action`
  (multiselect bar — see *Multiselect*), `_on_move_cards`
  (drag-and-drop — see *Drag & Drop*), `_on_delete_card`.
- **Detail overlay orchestration**: `_push_card_detail` / `_push_note_detail`
  build and `eval` the overlay; `_refresh_open_detail` re-pushes it after an
  action changes its unit (closing it if the unit vanished);
  `_close_detail_if_deleted` closes it when its unit was just deleted.
- **In-place field editing**: every card/note detail carries an editable
  `#detail-fields` section (see *Detail Overlay*), so there is no separate
  edit push. `_on_edit_card` (the explicit ✎ buttons on card frames) obeys
  the `edit_target` config: `"inline"` opens the unit's detail and evals
  `focusDetailFields()`; `"browser"` — and IO notes always (occlusion JSON
  fields) — opens Anki's Browser. `_on_save_note` parses the
  `save_note:<json>` payload, refuses (and toasts) if the field count no
  longer matches the note's notetype, then runs `update_note` as a
  `CollectionOp` whose success callback toasts "Saved" and re-pushes the
  same detail with the saved content.
- **`_on_filter_tag`**: relays a clicked tag pill's `filter_tag:<tag>` payload
  to `tag_filter_requested`, which the viewer's toolbar uses to set the tag
  filter combo.
- **`set_all_collapsed(collapsed)`**: collapses or expands every section of
  the current tree at once (persisted, like individual toggles); other trees'
  saved state is untouched.
- **Collapse persistence**: collapsed deck ids are stored in the collection config
  (`cardBrowser_collapsed_decks`), saved on every toggle and reloaded at the top
  of each render, so they survive restarts (independent of Anki's own
  `deck["collapsed"]`).
- **Signals**: `visible_section_changed`, `subdeck_created`, `tags_updated`,
  `flags_updated`, `tag_filter_requested`.

**`render.py`** — **`RenderMixin`**: full-page rendering and section/count updates.
- **`set_deck_tree` / `_render_deck_tree`**: fetches whole-subtree card metadata
  once, snapshots it for change tracking, runs the filter pass once
  (`compute_allowed`), decides the eager-render mode, then builds the root's own
  cards plus every child section and pushes the page. Resets scroll only when the
  top-level deck actually changes; a same-deck refresh restores the
  section-anchored scroll position.
- **`_render_page()`**: assembles the full HTML page (CSS vars + styles + body +
  overlay + selection bar + script) with the current edit/view mode baked in, and
  optionally restores the saved scroll anchor after load.
- **`refresh_section(deck_id)`**: rebuilds one deck section in place and updates
  ancestor header counts; renders eagerly (full card HTML, not placeholders)
  when the section is small enough (≤ `EAGER_RENDER_LIMIT`) even on an
  otherwise-lazy page, so a targeted rebuild can't collapse already-loaded
  cards into placeholders and throw the viewport; falls back to a full render
  if the section is now entirely filtered out.
- **Header counts and title**: `_refresh_header_counts`, `_refresh_all_header_counts`,
  `_update_title` fetch metadata once per call and thread it through every
  affected header.
- **Tree lookups**: `_tree_deck_ids`, `_find_node_context`, `_ancestor_deck_ids`.
- **Lazy-load / preview serving**: `_on_lazy_load`, `_on_lazy_load_note_cards`,
  `_on_preview_card`, `scroll_to_deck`.

**`refresh.py`** — **`RefreshMixin`**: targeted, scroll-preserving page updates —
our own mutations and external ones — replacing only the affected DOM instead of
reloading, falling back to a full render whenever a targeted update can't be
proven correct.
- **`_replace_unit` / `_targeted_refresh_card`**: surgically replace one rendered
  unit (IO/note groups rebuild as groups via `PageBuilder.unit_html`); under
  active filters the whole section is rebuilt instead, since visibility may have
  changed.
- **`refresh_note(col, nid, cids)`**: re-renders every on-screen shape a note's
  cards render as (cards can span sections, producing several groups and/or
  standalone cards), then updates counts/title once.
- **`_refresh_modified(col, structural_handled=False)`**: resolves the notes an
  op's mod-time watermark says changed (`consume_modified`) and
  `refresh_note()`s each one — works no matter where the edit came from. Falls
  back to a full render for bulk changes, or when nothing matches the
  watermark (undo restores old mod times).
- **`sync_external_changes(col)`**: diffs the tree's cid→deck map against the
  render snapshot and spot-applies membership changes — additions, removals,
  and moves, including our own (see *Refresh Strategy*).
- **`consume_modified` / `refresh_tree`**: thin wrappers — `consume_modified`
  scopes `ChangeTracker.consume_modified` to the rendered tree; `refresh_tree`
  triggers a full (scroll-preserving) re-render of the current tree.

**`builder.py`** — **`PageBuilder`**: owns the per-render group maps (`io_groups`,
`note_groups`: lead cid → member cids) and turns collection data into the tray's
HTML; never touches the webview.
- `expand_group_cids(cids)` — expands lead cids to full group membership (used by
  drag-drop and multiselect bulk actions).
- `unit_html(col, cid)` — the single full-HTML dispatch shared by lazy loading,
  eager rendering and targeted replaces, so a card renders identically no matter
  which path built it.
- `build_io_group` / `build_note_group` — full HTML for IO and multi-card note
  groups.
- Lazy placeholders: `_placeholder_html` (shared frame), `_card_placeholder`,
  `_group_placeholder`.
- `build_items` → `_build_cards_items` / `_build_notes_items` — one deck's own
  cards, dispatched by display mode; placeholders normally, or full HTML up front
  when `RenderContext.eager` is set (see *Performance*).
- `build_section(ctx, node, full_path, depth)` — recursive collapsible deck
  section: own cards + child sections, collapse state, header counts, the "+"
  menu and Review/Force-review buttons. Under active filters, empties are hidden
  entirely and the rest forced open (a match inside a collapsed section would
  otherwise sit invisible in a height-0 body and never lazy-load).
- `build_root_header` / `state_counts_html` / `title_text`.
- A `RenderContext` dataclass bundles everything one render pass needs (`col`,
  `meta`, `today`, `filters`, `allowed`, `eager`, `collapsed`), computed once by
  the caller, so section building stays a pure function of its inputs.
  `EAGER_RENDER_LIMIT = 120` (see *Performance*).
- Shared IO helpers used by both card building and the detail overlay:
  `extract_group_io`, `io_suspended_ordinals`, `cards_state_summary`.

**`details.py`** — `build_card_detail` / `build_io_detail` / `build_note_detail`:
assemble collection data (stats, due-date text, template names, tags) into
`rendering.detail`'s HTML builders; `build_card_detail` also attaches the
single card's review-history table (last 8 revlog rows). Card and note
details embed `build_editable_fields` (the in-place editor); the note
detail's read-only fields table renders only for view mode (`view-only`).
Pure builders — `CardTray` decides when to push them into the overlay.

**`actions.py`** — card mutations behind the tray's menus, detail overlay, and
drag-drop; nothing here touches the webview.
- `CARD_ACTIONS` — the bridge action names routed to `apply_scheduling_action`.
- `apply_scheduling_action` — flags, suspend/unsuspend/bury/unbury/forget,
  review-now; `set_due` and `reposition` prompt first.
- `prompt_tag_action` — prompts then bulk-adds/removes a tag, returning
  nid → [cids] for every affected note (tags show on every card of a note).
- `prompt_change_deck`, `resolve_normal_deck` (refuses filtered/dyn decks as move
  targets), `move_cards`, `confirm_delete`.

**`filters.py`** — `FilterState` dataclass (`.active` when any filter is set) and
the per-render filter pass: `compute_allowed` (content search → tag → state →
criteria, once over the whole subtree) and `order_cids` (per-section sort).

**`sync.py`** — **`ChangeTracker`**: the two per-render snapshots that answer
"what exactly changed" when Anki's `OpChanges` only says *that* something did.
- `known_cards` (cid → deck id) and `mod_watermark`, set by `snapshot()`.
- `diff_membership(current)` → `(added, removed, moved, previous)` — also
  adopts *current* as the new `known_cards` snapshot, so it doubles as the
  record step: our own moves/adds/removes fold in exactly like an external
  change would, and the next diff won't re-report them.
- `consume_modified(col, tree_deck_ids)` — in-tree cards/notes modified since the
  last sweep (scoped via the indexed `cards.did` column), then advances the
  watermark.

**`assets.py`** — `tray_css()` / `tray_js()`, `lru_cache`'d reads of `web/tray.css`
and the concatenated, sorted `web/js/*.js` files. The JS lives as real files
(editable with proper tooling, syntax-checkable with `node --check`) rather than
Python string constants; because it's all one script, function declarations
hoist across file boundaries and only the few top-level statements (listener
registration, initial calls) are order-sensitive.

**`webview.py`** — **`TrayWebView`**, an `AnkiWebView` that accepts drops only
from in-app drag sources (see *Drag & Drop*).

### `viewer/` — the outer widget + host modes

**`widget.py`** — **`CardBrowserWidget`**, the core `QWidget`, used by both host
modes:
- **Left panel**: top-level deck `QComboBox`, subdeck-search `QLineEdit`, the
  view/edit toggle and a refresh button, and a `DeckTree` sidebar.
- **Right panel**: a two-row filter toolbar, a collapsible advanced filter panel
  (built by `filter_bar.py`), and a `CardTray` webview.
- Connected via a `QSplitter`.
- Reads config (`display_mode`, `default_edit_mode`, `edit_target`) on
  construction, normalising unknown values to the documented defaults;
  `edit_target` is passed straight through to `CardTray`.

It wires signals between components: clicking a sidebar deck scrolls the tray;
scrolling the tray highlights the sidebar; creating/deleting subdecks refreshes both.

**Filter toolbar (Row 1):** content search (`QLineEdit`, 300 ms debounce), a
saved-searches button (☆, `viewer/searches.py`), and state filter chips
(`New` | `Learning` | `Due` | `Upcoming` | `Suspended`). A direct filter change
(chip click, sort change, "Clear all filters") stops a pending debounce timer
first, so a search-then-click can't render the page twice. Clicking a tag pill
on a card (`tagClicked` in JS → `filter_tag` bridge command →
`tag_filter_requested` signal) sets the tag combo the same way.

**Filter toolbar (Row 2):** "Filters" toggle (opens the advanced panel),
collapse-all / expand-all buttons (⊟/⊞, call `tray.set_all_collapsed`), the
active advanced filters as removable chips (`filter_bar.py::update_filter_chips`
— each chip clears just its own filter; replaced the old summary label), the
sort dropdown (10 modes) and an asc/desc direction toggle.

**Auto-refresh** (see *Refresh Strategy* below).

**`filter_bar.py`** — `FLAG_NAMES`; `build_filter_panel` (tag/flag combos plus
min/max ranges for ease (%), interval (days), lapses and reviews, and a "Clear all
filters" button); `build_criteria` (gathers spinbox values into the criteria dict
— ease is entered as % but filtered in permille, hence ×10); `update_filter_chips`
(rebuilds the removable-chip row from the active tag filter + criteria — each
chip's click silently resets just its own control, then re-applies filters once).

**`searches.py`** — Saved searches: named content-search queries persisted as a
`{name: query}` dict in the collection config (`cardBrowser_saved_searches`,
syncs with the profile). `open_saved_search_menu` builds the ☆ button's menu
(apply / "Save current search…" / Remove submenu); `load_saved_searches`
returns them name-sorted.

**`hosts.py`**
- **`CardBrowserWindow`** — singleton `QMainWindow` wrapping the widget; cleans up
  on close.
- **`EmbeddedBrowser`** — singleton that shows/hides the widget inside `mw`'s layout.
  It hides `mw.web` and `mw.bottomWeb` while active and **re-asserts** that on the
  `deck_browser_did_render` / `overview_did_refresh` hooks (so an op-triggered
  re-render of Anki's own screen can't pop it back on top of the widget).
  `mw.bottomWeb` must be hidden with `setVisible(False)` — its `hide()` merely
  collapses the height to 1 px, and Anki re-expands it asynchronously after every
  render, which flashed the bottom toolbar back over the browser.
- A module-level `profile_will_close` hook closes the window host and tears down
  the embedded widget, so no state from the old collection survives a profile
  switch. The host singletons and their hooks remain; they no-op until reopened.
- **`open_card_browser()`** picks the host from the `mode` config key.

**`style.py`** — `_QSS` (the Qt stylesheet for native widgets, palette-aware for
light/dark), the toolbar SVG icon templates, and `_svg_icon()`.

### `web/` — CSS + JS

**`tray.css`** — Uses CSS system colours (`Canvas`, `CanvasText`, `GrayText`,
`Highlight`) and `color-mix()` for automatic light/dark theming, plus
state-colour custom properties injected by Python. Key classes: `.card-frame`
(+ `.suspended`, `.state-*`, `.selected`), `.card-state-badge`, `.deck-header` /
`.deck-body` / `.deck-cards` (the grid), `.card-actions`, `.card-menu`,
`.note-group` / `.note-fields-table`, `.header-plus-btn` / `.plus-menu`,
`#overlay` / `#overlay-card`, `#selection-bar`, and `body.view-mode` (hides
edit-only elements).

**`js/`** — numbered files, concatenated in name order by `assets.tray_js()` into
one script (see `assets.py` above):
- **`10_mode_menus.js`** — edit/view mode toggle (`setEditMode`), card/deck 3-dot
  menus (`toggleMenu`, `cardAction`, `editCard`, `deleteCard`).
- **`20_overlay.js`** — detail overlay: `expandCard` / `expandNoteGroup` open it
  (unless the click was a selection gesture — see *Multiselect*), `showCardDetail`
  swaps or directionally slides in the new content, `overlayNav` steps through
  rendered units, `closeOverlay` (Escape when nothing is selected), the note-group
  card-preview dropdown and per-card expand/collapse.
- **`30_sections.js`** — header "+" dropdown, animated section collapse/expand,
  scroll-spy (`IntersectionObserver` reporting the topmost visible section).
- **`40_lazy.js`** — a second `IntersectionObserver` (400 px margin) batches
  `data-lazy` keys and requests renders via `pycmd('lazy_load:…')`; a bridge-race
  retry and a periodic rescue sweep keep placeholders from sticking; `fillCards` /
  `fillNoteCards` inject the results.
- **`50_grid.js`** — variable-width grid layout: measures cards and assigns
  row/column spans so tall content spans extra columns; re-runs after images load
  and on resize.
- **`60_dnd.js`** — drag & drop: delegated listeners so units rebuilt by targeted
  refreshes keep working; dragging a selected unit drags the whole selection (see
  *Multiselect*); external drags are refused so a drop can never navigate the page.
- **`70_select.js`** — multiselect: `toggleSelect`, `_selectRangeTo` (shift-click
  range), `clearSelection`, `updateSelectionBar`, `selectionAction` (sends
  `bulk:<action>:<ids>`). See *Multiselect*.
- **`80_updates.js`** — targeted DOM updates: `_cardEl`/`_groupEl` give
  `replaceCard`/`removeCard` and `replaceGroup`/`removeGroup` separate,
  card-shaped vs. group-shaped lookups, so a card op can't tear out a whole
  note group whose lead shares the cid; removing a unit purges it from the
  JS selection set and updates the selection bar; `replaceSection` re-applies
  the live selection to the rebuilt subtree (`_reapplySelection`, see
  `70_select.js`); `moveUnit` relocates a unit's element into another
  section's card container (silent cross-section moves — see *Drag & Drop*);
  plus `updateHeaderCounts` and section-anchored scroll save/restore.
- **`90_toast.js`** — `showToast`: transient in-page action feedback
  (bottom-center pill, auto-hides), evaled from op success callbacks.

## Refresh Strategy

The browser keeps itself in sync without full page reloads wherever possible.

- **One op-driven pipeline serves every mutation.** The add-on's own mutations
  (suspend, review-now, delete, scheduling, bulk actions, drag-drop moves) all
  run through `CollectionOp` (`tray/actions.py::_start_op`) — exactly like
  edits from Anki's own Browser, Add Cards, undo, or other add-ons — so both
  fire `operation_did_execute` and there's no separate "our own mutations"
  path to keep in sync. As a bonus, our own ops get native undo entries for
  free; success feedback is an in-page toast (`showToast`, evaled from the
  op's success callback — see `web/js/90_toast.js`) rather than Anki's native
  tooltip window, which looks foreign over the styled grid. Two handlers are
  registered on the hook, split by what changed:
  - `CardBrowserWidget._on_operation_did_execute` (`viewer/widget.py`) handles
    `changes.deck` / `changes.notetype` — repopulates the deck dropdown and
    fully re-renders (renames keep ids but change labels/templates).
  - `CardTray._on_operation_did_execute` (`tray/tray.py`) handles everything
    else (`changes.card` / `changes.note` / `changes.study_queues`).
    `OpChanges` only says *that* something changed (boolean flags, no ids), so
    the tray keeps two snapshots per render to work out *what*
    changed (`tray/sync.py::ChangeTracker`): a **`cid → deck id` map** (membership)
    and a **`mod`-time watermark** (content; queried over the rendered tree via the
    indexed `cards.did` column, not a whole-table scan). It runs, in order:
    1. not visible → defer a full refresh to the next `showEvent`;
    2. `sync_external_changes()` → diff the membership map: sections that
       gained new cards are rebuilt in place, moved units have their rendered
       element *relocated* into the target section (`moveUnit`, anchored at
       the render-order position — no rebuild, no flash), removed cards are
       dropped from the DOM. Falls back to one full re-render for bulk
       changes (>40), active filters, removals touching a rendered group or
       partial-group moves (a group moving whole travels as one unit), or
       adds/move targets in the root deck's own card area;
    3. unless membership was already fully re-rendered, `changes.card` /
       `changes.note` → `_refresh_modified()`: ask the watermark which
       cards/notes actually changed and `refresh_note()` each one in place —
       this works no matter where the edit came from. If nothing matches the
       watermark (undo restores old mod times) or the change is bulk-sized,
       fall back to a full re-render;
    4. `_refresh_open_detail()` re-pushes the open detail overlay so it can't
       go stale from an action that changed its unit, closing it if the unit
       vanished — it leaves an open inline edit form (`_open_detail = ("edit",
       cid)`) alone rather than clobbering unsaved DOM-only text;
    5. `_emit_filter_options()` (`tray/render.py::RenderMixin`) re-fetches tags
       and/or flags over the tree (whichever the op touched) and emits
       `tags_updated` / `flags_updated`, so the toolbar's tag/flag dropdowns
       pick up a tag or flag added via a menu/bulk action immediately, instead
       of only on the next deck change.
    The whole handler is wrapped so any targeted-refresh edge case converges to a
    full (scroll-preserving) re-render instead of leaving a stale view.
- **Sync** (`sync_did_finish`) → full refresh. Synced changes carry their original
  remote mod times, so the watermark can't see them.
- **Embedded mode** additionally re-hides Anki's content on
  `deck_browser_did_render` / `overview_did_refresh` so an op-driven re-render of
  Anki's own screen can't cover the widget.

All targeted refreshes preserve scroll position exactly. Full re-renders restore a
**section-anchored** scroll position: raw pixel offsets are meaningless across a
re-render (cards lazy-load at variable heights), so JS reports the deck section at
the viewport top plus the pixel depth into it (`scroll:<deckId>:<depth>`), and
`restoreScroll` re-measures that section's live position after the render. Only an
actual top-level deck change resets to the top.

## Communication Patterns

### Python → JavaScript
- `stdHtml(html)` — full page render (deck change, filter change). Queued JS evals
  run after the DOM is ready.
- `eval(js)` — targeted updates: `fillCards`, `fillNoteCards`, `fillCardPreview`,
  `replaceCard`, `replaceGroup`, `replaceSection`, `removeCard`, `removeGroup`,
  `moveUnit`, `updateHeaderCounts`, `setEditMode`, `scrollToSection`,
  `restoreScroll`, `showCardDetail`, `closeOverlay`, `clearSelection`,
  `showToast`.

### JavaScript → Python (`pycmd('action:payload')`, dispatched by `_on_bridge_cmd`)

| Command | Payload | Effect |
|---|---|---|
| `scroll` | `deck_id:depth` | Stores the section-anchored scroll position (`deck_id` 0 = raw offset) |
| `visible_section` | deck_id | Emits signal → sidebar highlights deck |
| `filter_tag` | tag | A clicked tag pill → emits `tag_filter_requested` → viewer sets the tag filter combo |
| `set_collapsed` | `deck_id:0/1` | Records a section's explicit collapse state and persists it to the collection config |
| `lazy_load` | cids | Renders cards/groups and injects via `fillCards()` |
| `lazy_load_note_cards` | cids | Renders a note group's individual cards |
| `preview_card` | cid | Renders a card's answer into the overlay preview |
| `card_detail` | cid | Builds the detail overlay for a card / IO group (dispatches to the note-group detail instead when `cid` is a group lead); answers with `showCardDetail(html, id, isRefresh)` |
| `note_detail` | lead cid | Builds the detail overlay for a note group (fields, card-preview select, stats) |
| `detail_closed` | `1` | JS closed the overlay — stop pushing detail refreshes |
| `save_note` | `<json {nid, unit, fields}>` | Inline editor Save: validates the field count against the note's current notetype, then runs `update_note` as an op; success toasts "Saved" and swaps back to the read view |
| `move_cards` | `deck_id:cids` | Drag-and-drop: moves the unit(s) to the deck (group leads expand to their members; dragging a selected unit moves the whole selection) — see *Drag & Drop* |
| `bulk` | `action:lead cids` | Multiselect bar: applies *action* to the selection (leads expand to group members) — see *Multiselect* |
| `review_due_deck` | deck_id | Opens Anki's reviewer for that deck |
| `force_review_deck` | deck_id | Confirms, sets all cards due today, starts review |
| `add_card` | deck_id | Opens Anki's Add Cards dialog for that deck |
| `edit_card` | cid | Explicit ✎ buttons on card frames. Obeys `edit_target`: `"browser"` (default) opens Anki's Browser filtered to that card; `"inline"` pushes the inline field editor into the overlay instead (IO notes always go to the Browser) |
| `add_subdeck` / `add_sibling_subdeck` | deck_id | Prompts for a name, creates the subdeck |
| `rename_deck` | deck_id | Prompts for a new name, renames the deck and its subdecks |
| `delete_deck` | deck_id | Deletes an empty deck (after confirmation) |
| `suspend` / `unsuspend` / `review_now` / `bury` / `unbury` / `forget` | cids | Scheduling/state action on the card(s) + targeted refresh |
| `flag_0` … `flag_7` | cids | Set the flag on the card(s) (`flag_0` clears) + targeted refresh |
| `set_due` / `reposition` | cids | Prompt, then set due date / reposition new card(s) |
| `add_tag` / `remove_tag` | cids | Prompt, then add/remove a tag on the note(s); refreshes each note |
| `change_deck` | cids | Prompt for a deck and move the card(s); re-renders the tree |
| `delete_card` | cids | Deletes card(s)/note (after confirmation) and removes from the DOM |

## Filtering, Sorting & Search

The toolbar provides three composable levels of filtering. The filter pass runs
**once over the whole subtree** per render (`tray/filters.py::compute_allowed`);
each deck section then intersects its own card ids against the allowed set and
sorts them (`order_cids`), so the hierarchy is preserved with no per-section SQL.
Sections a filter empties are hidden; the header title shows `(filtered / total)`
when any filter is active.

The content search understands two query forms: plain text is a
case-insensitive substring match over the note fields (HTML-stripped), while a
query using a known search keyword directly before a `:` (`tag:leech`,
`is:due`, `flag:1`, `prop:ivl>=10`, … — fixed allowlist in
`core.card_data._ANKI_SEARCH_KEYWORD_RE`, so `12:30` or `http://…` stay literal)
runs through **Anki's own search syntax** via `col.find_cards`, scoped to the
subtree. A keyword query Anki can't parse falls back to the substring match.

```
card_ids (whole subtree, once per render)
  ├── Content search   search_cards_with_anki_query / search_cards_by_content
  ├── Tag filter       filter_cards_by_tag(col, cids, tag)
  ├── State filter     filter_cards_by_states(meta, today, chips)  New | Learning | Due | Upcoming | Suspended
  └── Criteria filter  filter_cards_by_criteria(meta, criteria)    flag, ease/interval/lapse/review ranges
card_ids (per deck section)
  └── Sort             sort_cards(cids, meta, today, key, reverse)  10 modes
```

### Available Sort Modes

| Sort Key | Column(s) | Order (ascending) |
|---|---|---|
| `deck` | (original) | Default deck order |
| `due` | `cards.due` | Soonest due first; new cards last |
| `state` | `STATE_PRIORITY` | Most urgent first |
| `sort_field` | `notes.sfld` | Alphabetical A→Z |
| `ease` | `cards.factor` | Low → high (struggling first) |
| `interval` | `cards.ivl` | Short → long |
| `lapses` | `cards.lapses` | Most failed first |
| `reps` | `cards.reps` | Most reviewed first |
| `created` | `cards.id` | Newest first |
| `modified` | `cards.mod` | Recently changed first |

The asc/desc toggle reverses any mode.

## Display Modes

`display_mode` selects how the tray builds each section:
- **`cards`** — every card is its own frame.
- **`notes`** — cards are grouped by note. Single-card notes look like cards mode;
  multi-card notes render as a note group (`data-group-lead`) with a field table, an
  aggregate state badge, and an expandable per-card list. IO notes always render as
  a single grouped card. Section/title headers show both note and card counts.

## View / Edit Modes

Toggled by the eye/pencil button (defaults to **Edit**, set by `default_edit_mode`):
- **View mode** (read-only): the per-card edit pencil, the 3-dot action menu, and
  the deck "+" buttons are hidden via CSS (`body.view-mode`); `cardAction`/
  `deleteCard` also early-return when not in edit mode. The otherwise-empty root
  header bar collapses. Multiselect and drag-drop are edit-mode-only gestures.
- **Edit mode** (default): the edit pencil (Anki's Browser or the inline field
  editor, per `edit_target`), the full card/group action menu (flag, tags,
  change deck, scheduling, delete…), the deck "+" menus (add / rename /
  delete), multiselect and drag-drop are all exposed.

The mode flows `CardBrowserWidget._on_mode_toggled()` (`viewer/widget.py`) →
`CardTray.edit_mode` (→ `setEditMode()` in JS, which also clears any active
selection) and `DeckTree.edit_mode` (`decks/sidebar.py`, gates the context menu).

## Detail Overlay

Clicking any card or group opens a full inspector overlay instead of a plain
enlarged view. JS sends `card_detail` / `note_detail`; Python builds the whole
overlay body (`tray/details.py` + `rendering/detail.py::build_detail_html`) and
answers with `showCardDetail(html, id, isRefresh)` — op-driven re-pushes carry
`isRefresh=true`, and JS drops one whose id no longer matches the shown
overlay, so a refresh racing the close animation can't reopen it. The overlay
card is sized `min(920px, 92vw)` — noticeably larger than the inline card
frames — so field tables and stats have room without wrapping awkwardly. The
overlay's chrome — the close button and the prev/next nav arrows — is static
shell HTML written once by `tray/render.py::_render_page` (`#overlay-card` is
a fixed, non-scrolling flex column; only `#overlay-card-content` inside it
scrolls), not part of the per-detail HTML, so it can't be scrolled away or
duplicated by a refresh.

- **Header** — flag dot, deck path, state badge, notetype · template line, tags.
- **Action bar** (edit mode only) — edit, flag swatches, suspend/bury, review
  now, set due, forget, reposition (new cards), add tag, change deck, delete.
  Actions go through the same bridge commands as the card menus; the tray
  tracks the open overlay (`_open_detail`) and the op pipeline's
  `_refresh_open_detail` pushes a refreshed detail after each action (marked
  `isRefresh` so a push racing the close animation is dropped, not reopened),
  so the overlay always reflects the card's current state.
- **Content** — single cards get a Question/Answer toggle; IO groups get the
  masked image; note groups get the field table plus a per-card preview select.
- **Stats grid** — due (date + countdown), interval, ease, reviews, lapses,
  created, modified (group details show card/state counts instead).
- **Review history** — single-card details append a table of the card's last
  8 revlog entries (when, kind, rating, interval, time taken), newest first
  (`rendering/detail.py::build_revlog_table`); IO/note-group details omit it.
- **Navigation** — edge arrows or ←/→ step through the rendered units in page
  order (`overlayNav`); the overlay content slides left or right in the travel
  direction (`showCardDetail` in `web/js/20_overlay.js`) instead of swapping
  instantly, so stepping through a deck reads as continuous motion rather than a
  jump-cut.

**In-place field editing** — the detail view *is* the edit surface: every
card/note detail embeds a `#detail-fields` section (`rendering/detail.py::
build_editable_fields`, edit mode only) — in a card detail as the Fields
tab of the Question/Answer toggle (one pane at a time, so render and raw
fields never duplicate each other; for cloze/templated notetypes the two
genuinely differ), in a note detail as the content itself. One
contenteditable block per field, inside the same popup as the action bar,
stats and history. Typing marks the section dirty: the Revert/Save bar
appears, and refresh pushes back off (`showCardDetail` drops `isRefresh`
pushes while dirty) so an op landing mid-edit can't wipe the DOM-only text.
Save (`saveNoteEdit()`, or Ctrl+Enter) sends `save_note:<json>`; the success
path re-pushes the same detail with the saved content. Revert re-requests
the detail; Escape steps out of the field first, then closes. The overlay's
✎ Edit button is pure client-side (`focusDetailFields()` — scrolls to and
focuses the first field). The explicit ✎ pencils on card frames (`editCard`
→ `edit_card` → `_on_edit_card`) obey the `edit_target` config: `"inline"`
opens the detail popup pre-focused on the fields, `"browser"` (default)
opens Anki's Browser. IO notes always go to the Browser — their fields hold
occlusion JSON a free-form editor would corrupt (their detail's Edit button
routes to `editCard` too).

A full re-render resets the overlay; `detail_closed` from JS clears the state.

## Multiselect

While in edit mode, Ctrl/Cmd-click toggles a card frame or note group into a
selection instead of opening the detail overlay; Shift-click selects the
contiguous range of rendered units from the last toggled one; once any unit is
selected, **plain clicks also toggle membership** rather than opening the
overlay, so the grid becomes select-first for the rest of the gesture. **Ctrl/
Cmd+A** (`selectAll()`, `web/js/70_select.js`) selects every currently
rendered unit — including not-yet-loaded lazy placeholders, since `_selId`
falls back to a placeholder's `data-lazy` key — but is ignored while the
overlay is open or a form control is focused. Selection ids are unit ids
(`data-cid`, `data-group-lead`, or `data-lazy`), tracked client-side in
`web/js/70_select.js`.

A fixed bottom bar (`rendering.build_selection_bar()`, injected once per page by
`tray/render.py::_render_page`) shows the selection count and buttons for flag
(0–7), suspend, unsuspend, bury, change-deck, add-tag, and delete, plus a close
button. Every button calls `selectionAction()`, which sends
`pycmd('bulk:<action>:<lead cids>')` — the selected units' own ids, not their
expanded members. While the bar is open, `body.selection-open` adds bottom
padding to the page so the fixed bar can't cover the last grid row.

`CardTray._on_bulk_action` (`tray/tray.py`) handles it:
- expands each lead to its full IO/note-group membership
  (`PageBuilder.expand_group_cids`);
- `change_deck` / `delete` / `add_tag` / `remove_tag` prompt (via `tray/actions.py`,
  the same helpers the single-card menus use) then apply;
- any other action (`flag_N`, suspend, unsuspend, bury, unbury, forget, …) goes
  through `actions.apply_scheduling_action`;
- every action runs its own `CollectionOp`; the refresh comes solely from the
  op pipeline (see *Refresh Strategy*) — there is no bulk-specific refresh path;
- `eval`s `clearSelection()` once an op actually started — a cancelled prompt
  leaves the selection untouched.

Dragging a unit that's part of the current selection drags the **whole
selection** (`web/js/60_dnd.js` checks `_selected` before falling back to just
the dragged unit), so a multi-select drop moves every selected unit through the
same `move_cards` bridge command as a single-card drag (see *Drag & Drop*).

Selection is cleared by: **Esc** (only when the detail overlay isn't already
open — Esc closes the overlay first if one is showing); **leaving edit mode**
(`setEditMode(false)` calls `clearSelection()`); and after a bulk action or a
drag-drop move actually starts an op. Targeted DOM updates keep the live
selection in step with whatever the op pipeline rebuilds: `replaceCard`/
`replaceGroup` (`web/js/80_updates.js`) re-apply `.selected` to the new
element when its id was selected; `replaceSection` re-applies it across the
whole rebuilt subtree (`_reapplySelection`, `web/js/70_select.js`); a
placeholder that fills in via `fillCards` (`web/js/40_lazy.js`) does the same
for its unit; and `removeCard`/`removeGroup` purge a deleted/moved-out id from
the selection and refresh the selection bar — so a targeted refresh can never
silently leave the selection stale.

## Drag & Drop

Card frames and note groups are HTML5-draggable (edit mode only). Dragging a
unit that's part of the current multiselect drags the whole selection instead
(see *Multiselect*). Deck section headers (and the root header) accept drops;
dropping sends `move_cards:<deck_id>:<lead cids>`, handled by
`CardTray._on_move_cards` (`tray/tray.py`): it expands each lead to its full
group membership (`PageBuilder.expand_group_cids`) and calls
`tray/actions.py::move_cards`, which refuses filtered (dyn) decks as targets
(`resolve_normal_deck`) and otherwise runs a `set_deck` `CollectionOp`.

The page update comes from the same op pipeline as every other mutation (see
*Refresh Strategy*): the `set_deck` op fires `operation_did_execute`, and
`sync_external_changes()` (`tray/refresh.py`) diffs the membership map and
**relocates the moved unit's DOM node** into the target section (`moveUnit`
in `web/js/80_updates.js`) — neither section rebuilds, so nothing re-mounts
or flashes, and the node keeps its lazy observer and selection state for
free. Python computes the unit's render-order position in the target
(`_apply_unit_moves`: own cids + active sort) and passes the following cids
as anchor candidates; units are applied in reverse render order so one moved
unit can anchor on another. Header counts refresh separately (count-only
evals). It falls back to one full (scroll-preserving) re-render whenever the
targeted path can't be proven correct: a bulk-sized change (>40 cards),
active filters (the target section might not even be in the DOM), a group
moving only partially or scattering to several decks (stale group maps — a
group moving whole travels as one unit), or a move *into* the tree root's
own card area (a bare card grid, not an addressable section; moves out of it
relocate like any other). `_on_move_cards` `eval`s `clearSelection()` once
the op actually starts.

The move needs no special-casing in the membership diff: `ChangeTracker
.diff_membership` adopts the live cid→deck map as its new snapshot on every
call, so our own move folds in exactly like an external change would (undo
still shows up as a diff and is spot-applied).

Two platform quirks are handled: in-page HTML5 drags re-enter the widget as
native Qt drops, so `TrayWebView.dragEnterEvent` (`tray/webview.py`) allows drops
only when the drag has an in-app source; external drags (files/text from other
apps) are additionally refused by the page's own dragover/drop handlers
(`web/js/60_dnd.js`), so a stray drop can never navigate the webview.

## Performance

- **Lazy loading** — cards render as lightweight placeholders (state badge only);
  full HTML is built only when a placeholder scrolls within 400 px of the viewport,
  in batches of up to 20. Two hardening layers keep placeholders from sticking:
  the flush retries while the `pycmd` bridge is still connecting, and a 1.5 s
  sweep re-queues any still-unfilled placeholder near the viewport (covers
  requests lost to a re-render racing the bridge).
- **Eager search rendering** — when filters are active and the whole result set
  is ≤ `EAGER_RENDER_LIMIT` (120) cards, sections render full card HTML up
  front: results appear instantly and there is no lazy round-trip to lose.
- **Single metadata fetch per render** — a full deck-tree render fetches card
  metadata once for the whole subtree and threads it through every section's count
  and item builders, instead of re-querying per section (which was O(N × depth)).
  Targeted refreshes fetch fresh metadata once for the affected scope (e.g. header
  count updates fetch the topmost ancestor's subtree once and reuse it for every
  header on the path).
- **Single filter pass per render** — content/tag/state/criteria filters run once
  over the whole subtree (`compute_allowed`); sections intersect against the
  result instead of re-running search SQL per section.
- **Chunked bulk SQL** — metadata/tag/flag/search queries run over card IDs in
  500-ID chunks via a shared helper, avoiding per-card `col.get_card()` calls.
- **IO grouping** — Image Occlusion cards sharing a note render as one visual card
  with an SVG overlay, reducing DOM nodes.
- **Targeted DOM updates** — scheduling/edit/delete actions, bulk multiselect
  actions, drag-drop moves, and external changes all funnel through the same
  op-driven pipeline (`sync_external_changes` / `_refresh_modified` in
  `tray/refresh.py`), which replaces just the affected element(s), preserving
  scroll and avoiding full-page flashes; only filtered views, bulk-sized
  changes, or changes touching the tree root or a rendered group fall back to
  a full render.

## Testing

Run from the add-on root: `python3 -m pytest tests/ -q` (needs the pip
`anki`/`aqt`/`PyQt6` packages; everything runs headless on the offscreen Qt
platform). The suite works at three levels, all against a **real temporary
Anki collection** — no mocked data layer (181 tests total):

1. **Pure logic** (`test_card_state.py`, `test_card_data.py`,
   `test_note_grouping.py`, `test_card_rendering.py`) — state classification,
   filtering/sorting, SQL helpers, HTML builders.
2. **Widget logic** (`test_tray_render.py`, `test_detail_overlay.py`,
   `test_inline_edit.py`, `test_op_pipeline.py`, `test_toast.py`,
   `test_viewer_widget.py`) — a real `CardTray` (and, for `test_viewer_widget.py`,
   a real `CardBrowserWidget`) whose `AnkiWebView` is swapped for a `FakeWebView`
   that records every `stdHtml`/`eval`, and `mw` swapped for a fake wrapping the
   real collection. Covers renders, filters, bridge commands, the inline editor,
   the op-driven refresh pipeline, toasts, and targeted refreshes end-to-end on
   the Python side.
3. **Live DOM** (`test_dom_lazy_load.py`, `test_dom_state_sync.py`,
   `test_drag_drop.py`, `test_multiselect.py`, via `webview_harness.py`) — the
   exact page HTML loaded into a real offscreen `QWebEngineView` with `pycmd`
   shimmed. Tests drive real clicks/drags, round-trip bridge traffic through
   the tray, and can grab screenshots. This level reproduces browser-only bugs
   (e.g. the lazy-load bridge race). `test_drag_drop.py` and `test_multiselect.py`
   each combine a few Python-side (mixin-level) cases with one or two of these
   DOM-driven ones, since drag/select gestures need real DOM events but their
   refresh fallout is easiest to assert from the Python side.

CI (`.github/workflows/ci.yml`) runs the full suite plus `pyflakes` and
`node --check` on every `web/js/*.js` file, on push/PR and monthly against the
latest `anki`/`aqt` release (to catch upstream API breaks early).

Host integration (embedded mode, Anki hooks, profile switches) still needs the
manual smoke tests in HANDOFF.md / live Anki.
