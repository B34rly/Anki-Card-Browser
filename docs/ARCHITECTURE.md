# Architecture

> Anki Card Browser add-on — a visual card viewer accessible from the main toolbar.

## Overview

The add-on adds a **"Cards"** button to Anki's top toolbar. Clicking it opens the
Card Browser, which displays all cards in your decks as a visual grid organized by
the deck hierarchy, with lazy loading, card-state indicators, filtering/sorting,
and both view and edit modes.

The browser can open in one of two **host modes** (set by the `mode` config key),
both wrapping the same `CardBrowserWidget`:

- **Embedded** (default) — the widget is placed into Anki's main window layout and
  Anki's own content (`mw.web` / `mw.bottomWeb`) is hidden. Clicking any other
  toolbar button returns to Anki.
- **Window** — the widget lives in a standalone floating `QMainWindow`.

## File Map

```
card-browser/
├── __init__.py          Entry point — adds the "Cards" toolbar button; clears caches on collection load
├── viewer.py            CardBrowserWidget (layout, toolbar, filters, mode, auto-refresh) + window/embedded hosts
├── deck_tree.py         Sidebar deck tree (QTreeWidget) — navigation, filtering, context menu
├── decks.py             Pure data helpers — deck tree queries
├── deck_ops.py          Prompt-driven deck mutations (add/rename/delete/add-cards), shared by sidebar + tray
├── card_tray.py         CardTray widget (AnkiWebView) — bridge dispatch, section assembly, targeted refresh
├── card_state.py        Card state classification — new/learn/review, countdown, colours, filter/sort
├── card_data.py         Data access — bulk SQL, content/tag search, IO notetype detection, IO HTML parsing
├── card_rendering.py    HTML builders — card frames, IO overlays, note groups, deck-path labels
├── note_grouping.py     Note-level grouping + state summaries for notes display mode
├── tray_styles.py       CSS for the webview (string constant)
├── tray_js.py           JavaScript for the webview (string constant)
└── docs/
    ├── ARCHITECTURE.md  This file
    └── CONTRIBUTING.md  Code walkthrough for contributors
```

## Module Responsibilities

### `__init__.py` (entry point)
Registers a `gui_hooks.top_toolbar_did_init_links` callback that inserts a "Cards"
link into Anki's toolbar (calling `open_card_browser()` from `viewer.py`), and a
`gui_hooks.collection_did_load` callback that clears module-level caches so per-
collection state (IO notetype lookups) never leaks across profile switches.

### `viewer.py` (widget + hosts)

**`CardBrowserWidget`** — the core `QWidget`, used by both host modes:
- **Left panel**: top-level deck `QComboBox`, subdeck-search `QLineEdit`, the
  view/edit toggle and a refresh button, and a `DeckTree` sidebar.
- **Right panel**: a two-row filter toolbar, a collapsible advanced filter panel,
  and a `CardTray` webview.
- Connected via a `QSplitter`.
- Reads config (`display_mode`, `default_edit_mode`) on construction, normalising
  unknown values to the documented defaults.

It wires signals between components: clicking a sidebar deck scrolls the tray;
scrolling the tray highlights the sidebar; creating/deleting subdecks refreshes both.

**Filter toolbar (Row 1):** content search (`QLineEdit`, 300 ms debounce) and state
filter chips (`New` | `Learning` | `Due` | `Upcoming` | `Suspended`).

**Filter toolbar (Row 2):** "Filters" toggle (opens the advanced panel), an active-
filter summary label, the sort dropdown (10 modes) and an asc/desc direction toggle.

**Advanced filter panel** (`QFrame`): tag dropdown, flag dropdown (only flags in
use), and min/max ranges for ease (%), interval (days), lapses and reviews, plus a
"Clear all filters" button.

**Hosts:**
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

**Auto-refresh** (see *Refresh Strategy* below).

### `deck_tree.py` (sidebar)
**`DeckTree`** — a `QWidget` wrapping a `QTreeWidget`.
- Populates from an Anki `DeckTreeNode`; emits `deck_selected(deck_id, full_name)`.
- Text filtering shows only matching branches.
- Context menu (edit mode): "Add card", "Add child subdeck", "Add sibling subdeck"
  (siblings only for non-root decks), "Rename deck", "Delete deck".

### `decks.py` (data helpers)
Stateless functions over `mw.col.decks`:
- `get_top_level_decks()` — `[(deck_id, name), ...]` for the combo box.
- `find_deck_node(deck_id)` — finds a `DeckTreeNode` by ID (DFS).

### `deck_ops.py` (shared deck mutations)
Prompt-driven flows used by both the sidebar context menu and the tray's
header "+" menus, so the dialogs and validation exist once:
`open_add_cards` (via Anki's dialog manager), `prompt_new_subdeck`,
`prompt_rename_deck`, `confirm_delete_deck`. Each returns True when the
collection changed so the caller can refresh.

### `card_tray.py` (tray widget)
**`CardTray`** — a `QWidget` containing an `AnkiWebView`.
- **`set_deck_tree(root_node, root_name)`**: renders nested deck sections with
  collapsible headers and card placeholders. Resets scroll only when the top-level
  deck actually changes; a same-deck refresh restores the section-anchored scroll
  position.
- **`set_filters(search_text, active_chips, tag_filter, sort_key, sort_reverse, criteria)`**:
  updates filter/sort state and re-renders, preserving scroll. Does not re-emit
  tag/flag lists (avoids signal loops).
- **`_compute_allowed(col, card_ids, meta, today)`**: one filter pass (content
  search → tag → state → criteria) over the whole subtree per render; returns the
  allowed cid set (or `None` when no filters are active). Each section just
  intersects its own ids against it — no per-section SQL. `_order_cids` applies
  the sort per section from the already-fetched metadata.
- **`_on_bridge_cmd(cmd)`**: dispatches `pycmd` messages from JS.
- **`_build_cards_html` / `_build_notes_html`**: lightweight `data-lazy`
  placeholders (shared `_placeholder_html` builder) for IntersectionObserver-based
  lazy loading.
- **`_build_io_group` / `_build_note_group`**: full HTML for IO and multi-card note
  groups, built on lazy load.
- **External-change tracking**: each render snapshots `cid → deck id`
  (`_known_cards`) and a `mod`-time watermark. `sync_external_changes(col)` diffs
  membership (adds / removes / moves between sections); `consume_modified(col)`
  returns the exact cards/notes whose `mod` passed the watermark. See *Refresh
  Strategy*.
- **Targeted refresh**: `_targeted_refresh_card`, `refresh_note`, `refresh_section`,
  `_refresh_header_counts`, `refresh_tree` update the DOM in place (no full
  reload) and preserve scroll. They dispatch to `replaceCard` / `replaceGroup` /
  `replaceSection` / `removeCard` / `removeGroup` in JS.
- **Collapse persistence**: collapsed deck ids are stored in the collection config
  (`cardBrowser_collapsed_decks`), saved on every toggle and reloaded at the top
  of each render, so they survive restarts (independent of Anki's own
  `deck["collapsed"]`).
- **`_render_page()`**: assembles the full HTML page (CSS vars + styles + body +
  overlay + script) with the current edit/view mode baked in, and optionally
  restores the saved scroll anchor after load.
- **Signals**: `visible_section_changed`, `subdeck_created`, `tags_updated`,
  `flags_updated`.

### `card_state.py` (state classification)
- `card_state_from_meta(meta, today)` → `"new"`, `"learn"`, `"review-due"`,
  `"review-soon"`, `"review-mid"`, `"review-later"`, or `""`. `today` is required
  (`col.sched.today`).
- `card_countdown_from_meta(meta, today)` → human-readable countdown.
- `build_state_badge(state, countdown)` → badge HTML.
- `get_state_colors()` → CSS custom-property values from Anki's theme.
- `filter_cards_by_states` / `filter_cards_by_criteria` → matching card-ID sets.
- `sort_cards(card_ids, meta, today, sort_key, reverse)` → sorted IDs (10 modes).
- `STATE_ICONS` / `STATE_PRIORITY` / `FILTER_CHIP_STATES`.

### `card_data.py` (data access)
- `get_cards_metadata(col, card_ids)` — one chunked SQL join fetching
  `id, type, queue, due, nid, mid, did, factor, ivl, lapses, reps, flags, mod, sfld`.
- `get_card_decks(col, card_ids)` — cid → deck id map (membership diffing).
- `search_cards_by_content` / `filter_cards_by_tag` / `get_tags_for_cards` /
  `get_flags_for_cards` — chunked queries (shared `_query_in_chunks` helper).
- `is_io_mid(col, mid)` — cached Image Occlusion notetype check; `clear_caches()`
  resets the cache on profile change.
- `extract_io_data(answer_html)` — regex extraction of image src + mask shapes
  (including each mask's `ordinal`, so per-mask suspension can be shown).

### `card_rendering.py` (HTML builders)
Mostly-pure rendering functions:
- `render_normal_card(col, cid)` — full card frame.
- `build_io_card_html(...)` — grouped IO card with SVG overlay; suspended ordinals
  drawn grey.
- `build_note_group_html(...)` — multi-card note block (identified by
  `data-group-lead`, the lead card id).
- `build_svg_mask` / `format_deck_path` / `build_note_fields_table` / cloze styling.

### `note_grouping.py`
- `group_cards_by_note(col, card_ids, meta=None)` — ordered `NoteGroup`s (accepts
  pre-fetched metadata to avoid a redundant query).
- `note_state_summary` / `note_summary_counts` — per-note and aggregate counts.

### `tray_styles.py` (CSS)
A single `TRAY_CSS` string. Uses CSS system colours (`Canvas`, `CanvasText`,
`GrayText`, `Highlight`) and `color-mix()` for automatic light/dark theming, plus
state-colour custom properties injected by Python.

### `tray_js.py` (JavaScript)
A single `TRAY_JS` string:
- Edit/view mode toggle, card/deck menus, header "+" dropdown.
- Overlay (expand card / note group on click, Escape to close), card preview.
- Section collapse/expand with animated height transitions.
- Scroll-spy and lazy loading (two `IntersectionObserver`s).
- Variable-width grid layout (column spans for tall cards) with image-aware relayout.
- Targeted DOM updates and scroll save/restore.

## Refresh Strategy

The browser keeps itself in sync without full page reloads wherever possible.

- **The add-on's own mutations** (suspend, review-now, delete, scheduling) call the
  backend directly and update the DOM with a targeted `eval` — they do **not** go
  through `CollectionOp`, so they don't fire `operation_did_execute`.
- **External changes** (Anki's Browser, Add Cards, undo, other add-ons) fire
  `operation_did_execute`, handled by `CardBrowserWidget._on_operation_did_execute`.
  `OpChanges` only says *that* something changed (boolean flags, no ids), so the
  tray keeps two snapshots per render to work out *what* changed:
  a **`cid → deck id` map** (membership) and a **`mod`-time watermark**
  (content; queried over the rendered tree via the indexed `cards.did` column,
  not a whole-table scan). The handler runs, in order:
  1. not visible → defer a full refresh to the next `showEvent`;
  2. `changes.deck` / `changes.notetype` → repopulate the deck dropdown and fully
     re-render (renames keep ids but change labels/templates);
  3. `CardTray.sync_external_changes()` → diff the membership map: sections that
     gained cards are rebuilt in place, both ends of a deck move are rebuilt,
     removed cards are dropped from the DOM. Falls back to one full re-render for
     bulk changes (>40), active filters, or changes touching a rendered group;
  4. `changes.card` / `changes.note` → `_refresh_modified()`: ask the watermark
     which cards/notes actually changed and `refresh_note()` each one in place —
     this works no matter where the edit came from. If nothing matches the
     watermark (undo restores old mod times) or the change is bulk-sized, fall
     back to a full re-render.
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
  `updateHeaderCounts`, `setEditMode`, `scrollToSection`, `restoreScroll`.

### JavaScript → Python (`pycmd('action:payload')`, dispatched by `_on_bridge_cmd`)

| Command | Payload | Effect |
|---|---|---|
| `scroll` | `deck_id:depth` | Stores the section-anchored scroll position (`deck_id` 0 = raw offset) |
| `visible_section` | deck_id | Emits signal → sidebar highlights deck |
| `set_collapsed` | `deck_id:0/1` | Records a section's explicit collapse state and persists it to the collection config |
| `lazy_load` | cids | Renders cards/groups and injects via `fillCards()` |
| `lazy_load_note_cards` | cids | Renders a note group's individual cards |
| `preview_card` | cid | Renders a card's answer into the overlay preview |
| `review_due_deck` | deck_id | Opens Anki's reviewer for that deck |
| `force_review_deck` | deck_id | Confirms, sets all cards due today, starts review |
| `add_card` | deck_id | Opens Anki's Add Cards dialog for that deck |
| `edit_card` | cid | Opens Anki's Browser filtered to that card; stores it for refresh |
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
**once over the whole subtree** per render (`_compute_allowed()`); each deck
section then intersects its own card ids against the allowed set and sorts them,
so the hierarchy is preserved with no per-section SQL. Sections a filter empties
are hidden; the header title shows `(filtered / total)` when any filter is active.

```
card_ids (whole subtree, once per render)
  ├── Content search   search_cards_by_content(col, cids, query)   notes.flds, HTML-stripped
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
  header bar collapses.
- **Edit mode** (default): the edit pencil (opens Anki's editor), the full card/
  group action menu (flag, tags, change deck, scheduling, delete…), and the deck
  "+" menus (add / rename / delete) are exposed.

The mode flows `CardBrowserWidget._on_mode_toggled()` → `CardTray.edit_mode`
(→ `setEditMode()` in JS) and `DeckTree.edit_mode` (gates the context menu).

## Performance

- **Lazy loading** — cards render as lightweight placeholders (state badge only);
  full HTML is built only when a placeholder scrolls within 400 px of the viewport,
  in batches of up to 20.
- **Single metadata fetch per render** — a full deck-tree render fetches card
  metadata once for the whole subtree and threads it through every section's count
  and item builders, instead of re-querying per section (which was O(N × depth)).
  Targeted refreshes fetch fresh metadata once for the affected scope (e.g. header
  count updates fetch the topmost ancestor's subtree once and reuse it for every
  header on the path).
- **Single filter pass per render** — content/tag/state/criteria filters run once
  over the whole subtree (`_compute_allowed`); sections intersect against the
  result instead of re-running search SQL per section.
- **Chunked bulk SQL** — metadata/tag/flag/search queries run over card IDs in
  500-ID chunks via a shared helper, avoiding per-card `col.get_card()` calls.
- **IO grouping** — Image Occlusion cards sharing a note render as one visual card
  with an SVG overlay, reducing DOM nodes.
- **Targeted DOM updates** — scheduling/edit/delete actions and external-change
  refreshes replace just the affected element(s), preserving scroll and avoiding
  full-page flashes.
