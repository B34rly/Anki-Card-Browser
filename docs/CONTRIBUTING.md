# Contributing Guide

A walkthrough of the codebase to help new contributors get oriented quickly.

## Quick Start

1. Clone this repo into your Anki add-ons directory:
   ```
   ~/.local/share/Anki2/addons21/card-browser/
   ```
2. Restart Anki — the "View" button appears in the top toolbar.
3. Edit any `.py` file, then restart Anki (or use Anki's "Debug Console" → `mw.addonManager.restartAddons()`) to see changes.

## How the Add-on Loads

Anki discovers add-ons by looking for `__init__.py` in each subdirectory of `addons21/`. Our `__init__.py` does one thing: hook into the toolbar to add a "View" button. Everything else is imported lazily when that button is clicked.

```python
# __init__.py
gui_hooks.top_toolbar_did_init_links.append(on_top_toolbar_did_init_links)
```

## Module Guide

### Where to make changes

| I want to...                          | Edit this file         |
|---------------------------------------|------------------------|
| Change card visual styling            | `tray_styles.py`       |
| Change webview interactions/behavior  | `tray_js.py`           |
| Change card state logic or colors     | `card_state.py`        |
| Change how cards are rendered as HTML | `card_rendering.py`    |
| Change SQL queries or IO parsing      | `card_data.py`         |
| Change bridge command handling        | `card_tray.py`         |
| Change the window layout              | `viewer.py`            |
| Change the sidebar tree               | `deck_tree.py`         |
| Change deck data queries              | `decks.py`             |

### `tray_styles.py` — CSS

Contains a single `TRAY_CSS` string with all webview styles. The CSS uses:

- **CSS system colors** (`Canvas`, `CanvasText`, `GrayText`, `Highlight`) for automatic light/dark mode.
- **`color-mix()`** for opacity variations without hardcoded colors.
- **CSS custom properties** (`--state-new-color`, etc.) set dynamically by Python from Anki's theme.

Key CSS classes:
- `.card-frame` — Each card's outer container. Has hover scale, click shrink, and state border.
- `.card-frame.suspended` — Dimmed at 45% opacity.
- `.card-frame.state-new` / `.state-learn` / `.state-review-*` — Colored bottom border indicating card state.
- `.card-state-badge` — Positioned in top-left corner, shows icon + countdown text.
- `.deck-header` — Sticky section headers with collapse arrow and action buttons.
- `.deck-body` — Collapsible container wrapping a deck's cards and child decks.
- `.card-menu` — Per-card dropdown (suspend, review now).
- `.deck-ctx-menu` — Per-deck right-click menu (add subdeck, add card).
- `#overlay` — Full-screen card preview with blur backdrop.
- `.add-card-btn` — Dashed "+" button for adding cards (hidden in view mode).
- `body.view-mode` — Applied when in view mode; hides edit-only elements.

### `tray_js.py` — JavaScript

Contains a single `TRAY_JS` string with all client-side logic. Key systems:

**Edit mode**: `setEditMode(on)` toggles the `view-mode` class on `<body>`.

**Card menus**: `toggleMenu(e, id)` opens/closes per-card 3-dot menus. Only one menu open at a time. `cardAction(e, action, cid)` sends actions to Python via `pycmd`.

**Overlay**: `expandCard(el)` clones the card's `.card-content` into the overlay and animates it in. `closeOverlay()` animates out with a 280ms delay. Escape key closes it.

**Deck sections**: `toggleSection(deckId)` animates collapse/expand using explicit height transitions. `scrollToSection(deckId)` auto-expands parents and smooth-scrolls.

**Scroll-spy**: An `IntersectionObserver` watches `.deck-header` elements. When the topmost visible header changes, it sends `pycmd('visible_section:id')` so the sidebar can highlight the corresponding deck.

**Lazy loading**: Another `IntersectionObserver` (400px rootMargin) watches `.card-placeholder` elements. When they enter the viewport, their `data-lazy` key (card ID) is batched and sent to Python via `pycmd('lazy_load:cid1,cid2,...')`. Python renders the full HTML and calls `fillCards(data)` to replace placeholders.

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
Review, due 15+ days    → "review-later"  → Green 30% (dotted)
```

`get_state_colors()` reads Anki's theme colors (`STATE_NEW`, `STATE_LEARN`, `STATE_REVIEW`) and generates CSS variables with multiple alpha levels.

`STATE_PRIORITY` is used when grouping IO cards to show the most urgent state in the group badge.

### `card_data.py` — Data Access

**`get_cards_metadata(col, card_ids)`**: Runs a single SQL join on `cards` and `notes` tables to fetch `(id, type, queue, due, nid, mid)` for all requested cards. Chunks in batches of 500 to stay within SQLite's variable limit.

**`is_io_mid(col, mid)`**: Checks if a model (notetype) ID is an Image Occlusion type by looking for "image occlusion" in the model name. Results are cached in `_io_mid_cache` (module-level dict).

**`extract_io_data(answer_html)`**: Uses regex to parse Anki's IO card answer HTML:
1. Finds the `<img>` tag to get the image source.
2. Finds all `<div class="cloze...">` elements with `data-shape`, `data-left`, `data-top`, etc.
3. Returns `(img_src, [mask_dict, ...])`.

### `card_rendering.py` — HTML Builders

**`render_normal_card(col, cid)`**: Fetches a single card, gets its answer HTML, and wraps it in a `.card-frame` div with a state badge, 3-dot menu, and click handler.

**`build_io_card_html(...)`**: Builds a grouped IO card: an `<img>` with SVG overlays for each mask shape. Suspended ordinals get gray masks; active ones get red.

**`build_svg_mask(mask, suspended)`**: Converts a mask dict into an SVG shape element (`<rect>`, `<ellipse>`, or `<polygon>`).

**`format_deck_path(full_path)`**: Turns `"Top::Sub1::Sub2::Leaf"` into HTML like `<span class="deck-path">...::Sub1::Sub2::</span><span class="deck-leaf">Leaf</span>`.

### `card_tray.py` — Tray Widget

The `CardTray` class is the central orchestrator. It owns the `AnkiWebView` and handles all Python↔JS communication.

**Bridge command dispatch** (`_on_bridge_cmd`): A large if/elif chain that routes `pycmd` messages. After mutating actions (suspend, unsuspend, etc.), it re-renders the entire page by calling `set_deck_tree()` again.

**Section building** (`_build_section`): Recursively walks the deck tree, building nested HTML `<div class="deck-section">` elements with collapsible headers and card grids.

**Card placeholder building** (`_build_cards_html`): Groups IO cards by note ID, builds lightweight placeholder divs with state badges (so the user sees the state colors immediately), and registers IO group mappings for lazy loading.

**IO group building** (`_build_io_group`): Called during lazy load. Fetches the first card's answer HTML, extracts IO data, falls back to checking all cards in the group if the first one lacks data, then delegates to `build_io_card_html()`.

**Page rendering** (`_render_page`): Assembles the full HTML document: CSS custom properties → stylesheet → body → overlay → script. Pushes to the webview via `stdHtml()`.

### `viewer.py` — Main Window

**`CardViewerWindow`** is a singleton `QMainWindow`. Key signal connections:

```
QComboBox.currentIndexChanged  →  _on_deck_changed()  →  DeckTree.populate() + CardTray.set_deck_tree()
DeckTree.deck_selected         →  CardTray.scroll_to_deck()
CardTray.visible_section_changed → DeckTree.highlight_deck()
CardTray.subdeck_created       →  _refresh_current_deck()
DeckTree.subdeck_created       →  _refresh_current_deck()
QToolButton.toggled            →  CardTray.edit_mode + DeckTree.edit_mode
QLineEdit.textChanged          →  DeckTree.filter()
```

### `deck_tree.py` — Sidebar Tree

Uses `QTreeWidget` with items storing `deck_id` and `full_name` in `UserRole` data. Supports:
- Click → emits `deck_selected` signal
- Search → `filter(text)` hides non-matching branches
- Right-click (edit mode) → context menu for adding subdecks/cards
- `highlight_deck(id)` → programmatically selects and scrolls to a deck (called by scroll-spy)

### `decks.py` — Deck Queries

Three simple functions wrapping `col.decks.deck_tree()`:
- `get_top_level_decks()` — Children of the virtual root node.
- `get_leaf_decks()` — Recursive walk returning only childless decks.
- `find_deck_node(deck_id)` — DFS to find a specific node by ID.

## Common Tasks

### Adding a new card action

1. Add a button in `card_rendering.py` — either in `render_normal_card()` or `build_io_card_html()`.
2. Add JS handler in `tray_js.py` to call `pycmd('your_action:payload')`.
3. Add a handler in `card_tray.py` `_on_bridge_cmd()`.

### Adding a new deck action

1. Add a button or context-menu item in the deck header HTML in `card_tray.py` `_build_section()`.
2. Add JS in `tray_js.py` (`deckAction` already forwards `pycmd` calls).
3. Handle in `_on_bridge_cmd()`.

### Changing card appearance

- **Colors/spacing/layout**: Edit `tray_styles.py`.
- **State badge content**: Edit `card_state.py` `build_state_badge()` or `STATE_ICONS`.
- **Card frame structure**: Edit `card_rendering.py`.

### Adding a new card state

1. Add the state string to `card_state_from_meta()` in `card_state.py`.
2. Add it to `STATE_PRIORITY`.
3. Add CSS classes in `tray_styles.py` (`.card-frame.state-xxx` and `.state-xxx .card-state-badge`).
4. Add color variables in `get_state_colors()`.

## Conventions

- **No external dependencies** — only Anki/aqt/PyQt.
- **System colors over hardcoded** — CSS uses `Canvas`/`CanvasText`/`color-mix()` for theming.
- **Anki IDs are 64-bit** — use `object` type in Qt signals (not `int`) to avoid C++ overflow.
- **Bulk over individual** — prefer SQL batch queries over repeated `col.get_card()` calls.
- **Lazy over eager** — cards render as placeholders first, full content on scroll.
