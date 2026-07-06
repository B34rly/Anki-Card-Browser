# Contributing Guide

A walkthrough of the codebase to help new contributors get oriented quickly.
See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the high-level design.

## Quick Start

1. Clone this repo into your Anki add-ons directory:
   ```
   ~/.local/share/Anki2/addons21/card-browser/
   ```
2. Restart Anki — the **Cards** button appears in the top toolbar.
3. Edit any `.py` file, then restart Anki (or use the Debug Console →
   `mw.addonManager.restartAddons()`) to see changes.

There are no external dependencies and no build step — the CSS and JS live as
plain string constants in `tray_styles.py` and `tray_js.py`.

## How the Add-on Loads

Anki discovers add-ons by looking for `__init__.py` in each subdirectory of
`addons21/`. Our `__init__.py` does two small things: hook the toolbar to add the
"Cards" button, and clear caches when a collection loads. Everything else is
imported lazily when that button is clicked.

```python
# __init__.py
gui_hooks.top_toolbar_did_init_links.append(on_top_toolbar_did_init_links)
gui_hooks.collection_did_load.append(lambda col: clear_caches())
```

## Module Guide

### Where to make changes

| I want to...                          | Edit this file         |
|---------------------------------------|------------------------|
| Change card visual styling            | `tray_styles.py`       |
| Change webview interactions/behavior  | `tray_js.py`           |
| Change card state logic or colors     | `card_state.py`        |
| Change how cards are rendered as HTML | `card_rendering.py`    |
| Change note grouping / summaries      | `note_grouping.py`     |
| Change SQL queries or IO parsing      | `card_data.py`         |
| Change bridge command handling / refresh | `card_tray.py`      |
| Change the window layout / toolbar / hosts | `viewer.py`        |
| Change the sidebar tree               | `deck_tree.py`         |
| Change deck data queries              | `decks.py`             |
| Change deck add/rename/delete dialogs | `deck_ops.py`          |

### `tray_styles.py` — CSS

A single `TRAY_CSS` string. Uses CSS system colors (`Canvas`, `CanvasText`,
`GrayText`, `Highlight`), `color-mix()` for opacity variants, and CSS custom
properties (`--state-new-color`, …) set by Python from Anki's theme.

Key classes: `.card-frame` (+ `.suspended`, `.state-*`), `.card-state-badge`,
`.deck-header` / `.deck-body` / `.deck-cards` (the grid), `.card-actions`,
`.card-menu`, `.note-group` / `.note-fields-table`, `.header-plus-btn` /
`.plus-menu`, `#overlay`, and `body.view-mode` (hides edit-only elements).

### `tray_js.py` — JavaScript

A single `TRAY_JS` string. Key systems:

- **Edit mode**: `setEditMode(on)` toggles the `view-mode` class on `<body>`.
- **Menus**: `toggleMenu`, `cardAction`, `editCard`, `deleteCard`, the deck header
  `togglePlusMenu` / `plusAction`.
- **Overlay**: `expandCard` / `expandNoteGroup` (with a per-card preview dropdown),
  `closeOverlay` (Escape closes). User-supplied text inserted into `innerHTML` is
  run through `escapeHtml`.
- **Sections**: `toggleSection` (animated collapse/expand) and
  `scrollToSection` (auto-expands ancestors) both report the explicit end
  state via `set_collapsed:<deckId>:<0|1>` — never a toggle, so a replay or a
  race with a re-render can't invert the persisted state.
- **Scroll-spy**: an `IntersectionObserver` reports the topmost visible section via
  `pycmd('visible_section:id')`. `window._spyObserve` re-registers rebuilt headers.
- **Lazy loading**: a second `IntersectionObserver` (400 px margin) batches
  `data-lazy` keys and requests renders via `pycmd('lazy_load:…')`; `fillCards`
  swaps placeholders for full HTML.
- **Grid layout**: `layoutGrid` measures cards and assigns row/column spans so tall
  content spans extra columns; it re-runs after images load and on resize.
- **Targeted updates**: `replaceCard` / `removeCard` (by `data-cid`, falling back
  to the `data-lazy` placeholder), `replaceGroup` / `removeGroup` (note groups,
  by `data-group-lead`, same fallback), `replaceSection`, `updateHeaderCounts`.
- **Scroll**: a throttled listener reports a *section-anchored* position via
  `pycmd('scroll:deckId:depth')` (the deck section at the viewport top plus the
  pixel depth into it — raw offsets don't survive re-renders because cards
  lazy-load at variable heights); `restoreScroll(deckId, depth)` re-measures the
  section's live position after a full render. `deckId` 0 = raw-offset fallback.

### `card_state.py` — State Classification

Determines a card's visual state from its queue, type, and due date:

```
Queue/Type              → State          → Badge Color
──────────────────────────────────────────────────────
Suspended/Buried        → ""             → (none, dimmed frame)
New queue or type       → "new"          → Blue
Learning/Relearning     → "learn"        → Red
Review, due ≤ 0 days    → "review-due"   → Green (solid)
Review, due 1-3 days    → "review-soon"  → Green 70% (dotted)
Review, due 4-14 days   → "review-mid"   → Green 50% (dotted)
Review, due 15+ days    → "review-later" → Green 30% (dotted)
```

`card_state_from_meta(meta, today)` requires `today` (`col.sched.today`).
`get_state_colors()` reads Anki's theme colors and produces CSS variables.
`STATE_PRIORITY` picks the dominant state when summarising a group of cards.

### `card_data.py` — Data Access

- **`get_cards_metadata(col, card_ids)`**: one SQL join on `cards`/`notes` fetching
  `id, type, queue, due, nid, mid, did, factor, ivl, lapses, reps, flags, mod, sfld`,
  keyed by card id. Chunked at 500 ids via `_query_in_chunks` (shared by the search
  / tag / flag queries too).
- **`get_card_decks(col, card_ids)` / `get_deck_cards(col, deck_ids)` /
  `get_note_cards(col, note_ids)`**: lightweight bulk maps (cid → did by card
  or by deck, nid → cids) for membership diffing and note refreshes.
- **`is_io_mid(col, mid)`**: cached check for the Image Occlusion notetype;
  `clear_caches()` resets it on collection load.
- **`extract_io_data(answer_html)`**: regex-parses the `<img>` src and each
  `<div class="cloze…">` mask (shape, geometry, and `ordinal`), returning
  `(img_src, [mask_dict, …])`.

### `card_rendering.py` — HTML Builders

- **`render_normal_card(col, cid)`**: a `.card-frame` with the answer HTML, state
  badge, tag strip, and action buttons.
- **`build_io_card_html(...)`**: a grouped IO card — an `<img>` with SVG mask
  overlays; suspended ordinals are greyed.
- **`build_note_group_html(...)`**: a multi-card note block identified by
  `data-group-lead` (the lead card id, unique per render — so it never collides
  with its expanded lead card's `data-cid`, and stays distinct even when one
  note's cards span two deck sections).
- **`build_svg_mask` / `format_deck_path` / `build_note_fields_table`** and cloze
  marker styling.

### `note_grouping.py` — Notes Mode

- `group_cards_by_note(col, card_ids, meta=None)` returns ordered `NoteGroup`s
  (accepts pre-fetched metadata to avoid re-querying).
- `note_state_summary` / `note_summary_counts` compute per-note and aggregate
  state counts for badges and headers.

### `card_tray.py` — Tray Widget

`CardTray` owns the `AnkiWebView` and all Python↔JS communication.

- **Bridge dispatch** (`_on_bridge_cmd`): routes `pycmd` messages (see the table in
  ARCHITECTURE.md). Scheduling/delete actions mutate the backend and update the DOM
  in place.
- **Rendering**: `set_deck_tree` → `_render_deck_tree` fetches whole-subtree
  metadata once, runs the filter pass once (`_compute_allowed`), and threads both
  through `_build_section` → `_state_counts_html` / `_build_items_html`.
  `_render_page` pushes the full page with the edit/view mode baked in and
  restores the scroll anchor.
- **Lazy load**: `_build_*_html` emit placeholders; `_on_lazy_load` /
  `_build_io_group` / `_build_note_group` render full content on demand.
- **External-change tracking**: each render snapshots `cid → deck id`
  (`_known_cards`) plus a `mod`-time watermark; `sync_external_changes` diffs
  membership and `consume_modified` pinpoints edited cards/notes (see *Refresh
  Strategy* in ARCHITECTURE.md).
- **Targeted refresh**: `_targeted_refresh_card` (single card / IO group / note
  group), `refresh_note` (an edited note's card(s), all render shapes),
  `refresh_section`, `_refresh_header_counts`, `refresh_tree` — all preserve
  scroll.

### `viewer.py` — Widget + Hosts

`CardBrowserWidget` is the core widget; `CardBrowserWindow` and `EmbeddedBrowser`
host it. Key signal connections:

```
QComboBox.currentIndexChanged   → _on_deck_changed()  → DeckTree.populate() + CardTray.set_deck_tree()
DeckTree.deck_selected          → CardTray.scroll_to_deck()
CardTray.visible_section_changed → DeckTree.highlight_deck()
CardTray.subdeck_created        → _refresh_current_deck()
CardTray.tags_updated / flags_updated → repopulate tag/flag combos
QToolButton.toggled             → CardTray.edit_mode + DeckTree.edit_mode
QLineEdit.textChanged           → DeckTree.filter() / debounced _apply_filters()
gui_hooks.operation_did_execute → _on_operation_did_execute() (see Refresh Strategy)
gui_hooks.sync_did_finish       → full refresh (watermark can't see synced changes)
gui_hooks.profile_will_close    → module-level teardown of both hosts
```

### `deck_tree.py` — Sidebar Tree

`QTreeWidget` with `deck_id` / `full_name` stored in `UserRole` data. Click emits
`deck_selected`; search hides non-matching branches; the edit-mode context menu
offers add / rename / delete actions; `highlight_deck(id)` selects/scrolls without emitting.

### `decks.py` — Deck Queries

`get_top_level_decks()` (combo children) and `find_deck_node(deck_id)` (DFS),
both wrapping `col.decks.deck_tree()`.

## Common Tasks

### Adding a new card action

1. Add a button in `card_rendering.py` (`render_normal_card` /
   `build_io_card_html` / `build_note_group_html`).
2. Add a JS handler in `tray_js.py` that calls `pycmd('your_action:payload')`.
3. Handle it in `card_tray.py` `_on_bridge_cmd()`, doing a targeted DOM update
   where possible so scroll is preserved.

### Adding a new deck action

1. Add a button / menu item in the deck header HTML in `_build_section()`.
2. `deckAction` / `plusAction` in `tray_js.py` already forward `pycmd`.
3. Handle it in `_on_bridge_cmd()`.

### Adding a new card state

1. Add the state string to `card_state_from_meta()`.
2. Add it to `STATE_PRIORITY`.
3. Add CSS (`.card-frame.state-xxx` and `.state-xxx .card-state-badge`).
4. Add color variables in `get_state_colors()`.

## Conventions

- **No external dependencies** — only Anki / aqt / PyQt.
- **System colors over hardcoded** — CSS uses `Canvas` / `CanvasText` / `color-mix()`.
- **Anki IDs are 64-bit** — use `object` (not `int`) in Qt signals to avoid C++ overflow.
- **Bulk over individual** — prefer chunked SQL over repeated `col.get_card()`; fetch
  metadata once per render and thread it through.
- **Lazy over eager** — cards render as placeholders first, full content on scroll.
- **Targeted over full** — update the DOM in place to preserve scroll; reserve full
  `stdHtml` renders for deck/filter changes.
- **Escape untrusted text** — escape any user/template text inserted into HTML, on
  both the Python (`html.escape`) and JS (`escapeHtml`) sides.
