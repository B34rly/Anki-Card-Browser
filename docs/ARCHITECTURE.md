# Architecture

> Anki Card Browser add-on — a visual card viewer accessible from the main toolbar.

## Overview

The add-on adds a **"View"** button to Anki's top toolbar (`Decks / Add / Browse / **View** / Stats / Sync`). Clicking it opens a standalone window that displays all cards in your decks as a visual grid, organized by the deck hierarchy, with lazy loading, card state indicators, and both view and edit modes.

## File Map

```
card-browser/
├── __init__.py          Entry point — hooks into Anki's toolbar
├── viewer.py            Main window (QMainWindow) — layout, dropdown, sidebar, mode toggle
├── deck_tree.py         Sidebar deck tree (QTreeWidget) — navigation, filtering, context menu
├── decks.py             Pure data helpers — deck tree queries
├── card_tray.py         CardTray widget (QWidget) — bridge command dispatch, section assembly
├── card_state.py        Card state classification — new/learn/review, countdown, colors
├── card_data.py         Data access — bulk SQL, IO notetype detection, IO HTML parsing
├── card_rendering.py    HTML builders — card frames, IO overlays, deck path labels
├── tray_styles.py       CSS for the webview (card frames, menus, overlay, dark mode)
├── tray_js.py           JavaScript for the webview (menus, lazy loading, scroll-spy)
└── docs/
    ├── ARCHITECTURE.md  This file
    └── CONTRIBUTING.md  Code walkthrough for contributors
```

## Module Responsibilities

### `__init__.py` (entry point)
Registers a `gui_hooks.top_toolbar_did_init_links` callback that inserts a "View" link into Anki's toolbar. Calls `open_card_viewer()` from `viewer.py`.

### `viewer.py` (main window)
**`CardViewerWindow`** — A singleton `QMainWindow` with:
- **Left panel**: `QComboBox` (top-level deck selector), `QLineEdit` (subdeck search), view/edit toggle button, and a `DeckTree` sidebar.
- **Right panel**: A two-row filter toolbar, a collapsible advanced filter panel, and a `CardTray` webview showing all cards.
- Connected via a `QSplitter`.

The window wires signals between components: clicking a sidebar deck scrolls the tray; scrolling the tray highlights the sidebar; creating subdecks refreshes both.

**Filter toolbar (Row 1):** Card content search (`QLineEdit`, 300ms debounce) and state filter chips (`New` | `Learning` | `Due` | `Upcoming` | `Suspended`).

**Filter toolbar (Row 2):** "Filters" toggle button (opens the advanced panel), active filter summary label, and sort dropdown (10 sort modes).

**Advanced filter panel** (`QFrame`, toggled by the Filters button):
- Tag dropdown (auto-populated per deck)
- Flag dropdown (shows only flags in use: Red, Orange, Green, Blue, Pink, Turquoise, Purple)
- Ease range (min/max `QSpinBox`, percentage)
- Interval range (min/max, days)
- Lapse count range (min/max)
- Review count range (min/max)
- "Clear all filters" button

### `deck_tree.py` (sidebar)
**`DeckTree`** — A `QWidget` wrapping a `QTreeWidget`.
- Populates from an Anki `DeckTreeNode`.
- Emits `deck_selected(deck_id, full_name)` on click.
- Supports text filtering (shows only matching branches).
- Context menu (edit mode): "Add subdeck", "Add card".

### `decks.py` (data helpers)
Stateless functions that query `mw.col.decks`:
- `get_top_level_decks()` — returns `[(deck_id, name), ...]` for the combo box.
- `get_leaf_decks()` — returns all leaf decks (no children).
- `find_deck_node(deck_id)` — finds a `DeckTreeNode` by ID.

### `card_tray.py` (tray widget)
**`CardTray`** — A `QWidget` containing an `AnkiWebView`.
- **`set_deck_tree(root_node, root_name)`**: Renders nested deck sections with collapsible headers and card placeholders.
- **`set_filters(search_text, active_chips, tag_filter, sort_key, criteria)`**: Updates filter/sort state and re-renders. Avoids re-emitting tag/flag lists to prevent signal loops.
- **`_apply_filters(col, card_ids)`**: Chains content search → tag filter → state filter → criteria filter → sort.
- **`_on_bridge_cmd(cmd)`**: Dispatches `pycmd` messages from JS (suspend, review, add card, lazy load, etc.).
- **`_build_cards_html()`**: Creates lightweight placeholder divs with `data-lazy` attributes for IntersectionObserver-based lazy loading.
- **`_build_io_group()`**: Renders Image Occlusion card groups with SVG mask overlays on lazy load.
- **`_render_page()`**: Assembles the full HTML page with CSS variables, styles, overlay, and scripts.
- **Signals**: `visible_section_changed`, `subdeck_created`, `tags_updated`, `flags_updated`.

### `card_state.py` (state classification)
Pure functions and constants for determining a card's visual state:
- `card_state_from_meta(meta, today)` → `"new"`, `"learn"`, `"review-due"`, `"review-soon"`, `"review-mid"`, `"review-later"`, or `""`.
- `card_countdown_from_meta(meta, today)` → human-readable countdown (`"Due"`, `"3 days"`, `"2 mo"`).
- `build_state_badge(state, countdown)` → HTML for the colored badge in the card corner.
- `get_state_colors()` → CSS custom property values sourced from Anki's theme.
- `filter_cards_by_states(meta, today, active_chips)` → set of card IDs matching active state filter chips.
- `filter_cards_by_criteria(meta, criteria)` → set of card IDs matching advanced criteria (flag, ease, interval, lapses, reviews).
- `sort_cards(card_ids, meta, today, sort_key)` → sorted card IDs. Supports 10 sort modes: deck, due, state, sort_field, ease, interval, lapses, reps, created, modified.
- `STATE_ICONS` / `STATE_PRIORITY` / `FILTER_CHIP_STATES` — SVG icon strings, sort-priority map, chip→state mapping.

### `card_data.py` (data access)
- `get_cards_metadata(col, card_ids)` — Bulk SQL fetch of card type/queue/due/nid/mid/factor/ivl/lapses/reps/flags/mod/sfld in 500-card chunks.
- `search_cards_by_content(col, card_ids, query)` — Full-text search against note fields (HTML-stripped, case-insensitive).
- `get_tags_for_cards(col, card_ids)` — Sorted distinct tags from the given cards' notes.
- `filter_cards_by_tag(col, card_ids, tag)` — Subset of cards whose note has a specific tag.
- `get_flags_for_cards(col, card_ids)` — Sorted distinct non-zero flag values present in the cards.
- `is_io_mid(col, mid)` — Cached check: is this model an Image Occlusion notetype?
- `extract_io_data(answer_html)` — Regex extraction of image src and mask shapes from IO answer HTML.
- `ACTIVE_ORDINAL_RE` — Compiled regex for finding the active cloze ordinal.

### `card_rendering.py` (HTML builders)
Pure rendering functions (no Anki collection access except in `render_normal_card`):
- `render_normal_card(col, cid)` — Full card frame HTML with answer, menu, badge.
- `build_io_card_html(img_src, masks, card_ids, ...)` — Grouped IO card with SVG overlay.
- `build_svg_mask(mask, suspended)` — Single SVG shape element (rect/ellipse/polygon).
- `format_deck_path(full_path)` — Truncated breadcrumb label for deck headers.

### `tray_styles.py` (CSS)
A single `TRAY_CSS` string constant containing all webview styles. Uses `color-mix()` and CSS system colors (`Canvas`, `CanvasText`) for automatic light/dark mode support.

### `tray_js.py` (JavaScript)
A single `TRAY_JS` string constant containing all client-side behavior:
- Edit mode toggle
- Card/deck dropdown menus and context menus
- Overlay (expand card on click, close on Escape)
- Deck section collapse/expand with animated height transitions
- Scroll-spy via `IntersectionObserver` (reports visible section to Python)
- Lazy loading via `IntersectionObserver` (batches card IDs, requests renders via `pycmd`)

## Data Flow

```
User clicks "View" in toolbar
    │
    ▼
__init__.py → open_card_viewer() → CardViewerWindow (singleton)
    │
    ├── QComboBox populated from decks.get_top_level_decks()
    │       │
    │       ▼ (user selects deck)
    │   decks.find_deck_node(deck_id)
    │       │
    │       ├──► DeckTree.populate(node)     [sidebar]
    │       └──► CardTray.set_deck_tree(node) [main panel]
    │               │
    │               ├── Bulk SQL: card_data.get_cards_metadata()
    │               ├── Build placeholder HTML with card_state badges
    │               ├── Assemble full HTML page (CSS + body + overlay + JS)
    │               └── Push to AnkiWebView via stdHtml()
    │
    ▼ (in the webview)
IntersectionObserver detects visible placeholders
    │
    ▼
pycmd('lazy_load:cid1,cid2,...')
    │
    ▼
CardTray._on_lazy_load()
    ├── card_rendering.render_normal_card() for regular cards
    └── CardTray._build_io_group() → card_rendering.build_io_card_html() for IO
    │
    ▼
JS fillCards() replaces placeholders with rendered HTML
```

## Communication Patterns

### Python → JavaScript
- `stdHtml(html)` — Full page render (on deck change or after card actions).
- `eval(js)` — Inject lazy-loaded cards via `fillCards(data)`, toggle edit mode via `setEditMode(on)`, scroll via `scrollToSection(id)`.

### JavaScript → Python
All JS→Python communication uses `pycmd('action:payload')`, dispatched by `CardTray._on_bridge_cmd()`:

| Command | Payload | Effect |
|---|---|---|
| `visible_section` | deck_id | Emits signal → sidebar highlights deck |
| `toggle_section` | deck_id | Tracks collapse state (no re-render) |
| `lazy_load` | comma-separated cids | Renders cards and injects via `fillCards()` |
| `review_due_deck` | deck_id | Opens Anki reviewer for that deck |
| `force_review_deck` | deck_id | Sets all cards due today, starts review |
| `add_card` | deck_id | Opens Anki's Add Cards dialog |
| `add_subdeck` | deck_id | Prompts for name, creates subdeck |
| `suspend` / `unsuspend` | cid | Suspends/unsuspends single card |
| `suspend_group` / `unsuspend_group` | cid,cid,... | Suspends/unsuspends IO group |
| `review_now` / `review_now_group` | cid(s) | Sets card(s) due today |

## Filtering, Sorting & Search

The toolbar provides three levels of filtering, all composable:

### Filter Pipeline

```
card_ids (per deck section)
    │
    ├── Content search: search_cards_by_content(col, cids, query)
    │       Searches notes.flds (HTML-stripped, case-insensitive)
    │
    ├── Tag filter: filter_cards_by_tag(col, cids, tag)
    │       Matches a single tag from the dropdown
    │
    ├── State filter: filter_cards_by_states(meta, today, chips)
    │       Chips: New | Learning | Due | Upcoming | Suspended
    │
    ├── Criteria filter: filter_cards_by_criteria(meta, criteria)
    │       Advanced: flag, ease range, interval range,
    │       lapse count range, review count range
    │
    └── Sort: sort_cards(cids, meta, today, sort_key)
            10 modes: deck, due, state, sort_field, ease,
            interval, lapses, reps, created, modified
```

Filters are applied **per deck section** in `_apply_filters()`, preserving the deck hierarchy. Empty sections are hidden. The header title shows `(filtered / total cards)` when any filter is active.

### UI Layout

```
Row 1: [🔍 Search content…]  [New] [Learning] [Due] [Upcoming] [Suspended]
Row 2: [⚙ Filters ▾] active filter summary…           [Sort: Deck order ▾]

┌─ Filter Panel (toggled) ─────────────────────┐
│  Tag:      [All tags              ▾]         │
│  Flag:     [Any flag              ▾]         │
│  Ease:     [Min] – [Max]  (percentage)       │
│  Interval: [Min] – [Max]  (days)             │
│  Lapses:   [Min] – [Max]                     │
│  Reviews:  [Min] – [Max]                     │
│                             [Clear all filters]│
└──────────────────────────────────────────────┘
```

### Signal Flow for Filters

```
UI control changed
    → viewer._apply_filters()
        → builds criteria dict from panel widgets
        → updates summary label
        → calls tray.set_filters(search, chips, tag, sort, criteria)
            → tray._render_deck_tree(emit_tags=False)
                → per-section _apply_filters(col, cids))
                    → search → tag → state → criteria → sort
                → rebuild HTML → push to webview

Deck changed (new deck selected)
    → tray.set_deck_tree(node, name)
        → tray._render_deck_tree(emit_tags=True)
            → emits tags_updated(list) → viewer repopulates tag combo
            → emits flags_updated(list) → viewer repopulates flag combo
```

### Available Sort Modes

| Sort Key | Column(s) Used | Order |
|---|---|---|
| `deck` | (original) | Default deck order |
| `due` | `cards.due` | Ascending; new cards last |
| `state` | `STATE_PRIORITY` | Most urgent first |
| `sort_field` | `notes.sfld` | Alphabetical A→Z |
| `ease` | `cards.factor` | Low → high (struggling first) |
| `interval` | `cards.ivl` | Short → long (youngest first) |
| `lapses` | `cards.lapses` | Most failed first |
| `reps` | `cards.reps` | Most reviewed first |
| `created` | `cards.id` | Newest first |
| `modified` | `cards.mod` | Recently changed first |

## View / Edit Modes

The window has a toggle button (eye/pencil icon):
- **View mode** (default): Card menus and the "+" add-card buttons are hidden via CSS (`body.view-mode`).
- **Edit mode**: Card 3-dot menus appear on hover. Deck header right-click context menus are enabled. "+" buttons become visible.

The mode state flows: `viewer._on_mode_toggled()` → sets `CardTray.edit_mode` (which calls `setEditMode()` in JS) and `DeckTree.edit_mode` (which gates the context menu).

## Performance

- **Lazy loading**: Cards render as lightweight placeholders (~100 bytes each). Full card HTML is only generated when placeholders scroll into view (400px margin). Batches of up to 20 cards are loaded per frame.
- **Bulk SQL**: `get_cards_metadata()` fetches type/queue/due/factor/ivl/lapses/reps/flags/mod/sfld for all cards in one query (chunked at 500), avoiding N individual `col.get_card()` calls during initial render.
- **IO grouping**: Image Occlusion cards sharing the same note are grouped into a single visual card with an SVG overlay, reducing DOM nodes.
- **CSS `content-visibility: auto`**: Card frames use content-visibility for additional browser-level rendering optimization.
