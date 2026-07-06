# Contributing Guide

A walkthrough of the codebase to help new contributors get oriented quickly.
See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full module-by-module design —
this file stays high-level and points there for specifics.

## Quick Start

1. Clone this repo into your Anki add-ons directory:
   ```
   ~/.local/share/Anki2/addons21/card-browser/
   ```
2. Restart Anki — the **Cards** button appears in the top toolbar.
3. Edit any `.py`, `.css`, or `.js` file, then restart Anki (or use the Debug
   Console → `mw.addonManager.restartAddons()`) to see changes. The CSS/JS are
   cached per-process (`tray/assets.py`), so they need a restart too, not just
   a page refresh.

There are no external dependencies and no build step. The webview's CSS and JS
live as plain files under `web/` (`web/tray.css`, `web/js/*.js`) rather than
Python string constants, so they're editable with normal tooling and
syntax-checkable with `node --check web/js/<file>.js`.

## How the Add-on Loads

Anki discovers add-ons by looking for `__init__.py` in each subdirectory of
`addons21/`. Our `__init__.py` does two small things: hook the toolbar to add the
"Cards" button, and clear caches when a collection loads. Everything else is
imported lazily when that button is clicked.

```python
# __init__.py
from .core.card_data import clear_caches
from .viewer import open_card_browser

gui_hooks.top_toolbar_did_init_links.append(on_top_toolbar_did_init_links)
gui_hooks.collection_did_load.append(lambda col: clear_caches())
```

## Package Tour

The code is split into packages by layer; each has its own module docstring
worth reading first, and a full breakdown in ARCHITECTURE.md's *Module
Responsibilities*.

- **`core/`** — collection data and domain logic. No Qt, no HTML: `card_data.py`
  (SQL/search/IO parsing), `card_state.py` (state classification, sort/filter),
  `note_grouping.py` (note-level grouping). Safe to reason about without a
  webview in the picture.
- **`rendering/`** — pure HTML builders, split by shape: `frames.py` (base card
  chrome + the multiselect bar), `io_cards.py` (Image Occlusion), `notes.py`
  (field tables / note groups), `detail.py` (the inspector overlay). Import the
  package (`from ..rendering import …`), not the submodules directly.
- **`decks/`** — the deck side: `data.py` (pure queries), `ops.py` (prompt-driven
  mutations shared by the sidebar and the tray's header menus), `sidebar.py`
  (the `DeckTree` widget).
- **`tray/`** — the card tray webview and the Python↔JS bridge. `tray.py` owns
  the widget and bridge dispatch; `render.py` / `refresh.py` are its two mixins
  (full renders vs. targeted updates); `builder.py` turns collection data into
  HTML; `details.py` builds the detail-overlay data; `actions.py` holds the
  mutations; `filters.py`, `sync.py`, `assets.py`, `webview.py` are focused
  helpers. Start with `tray/tray.py`'s module docstring — it documents the
  shared state contract used across the package.
- **`viewer/`** — the outer widget and its two host modes: `widget.py`
  (`CardBrowserWidget`), `filter_bar.py` (advanced filter panel), `hosts.py`
  (window/embedded hosts + `open_card_browser()`), `style.py` (Qt stylesheet +
  icons).
- **`web/`** — `tray.css` plus `web/js/*.js`. The JS files are numbered and
  concatenated in name order into one script by `tray/assets.py`, so they're
  really one program split across files for readability — function
  declarations hoist across the boundary, so ordering only matters for
  top-level statements (event listener registration, initial calls).

### Where to make changes

| I want to...                          | Edit this                          |
|----------------------------------------|-------------------------------------|
| Change card visual styling             | `web/tray.css`                      |
| Change webview interactions/behavior   | `web/js/*.js`                       |
| Change card state logic or colors      | `core/card_state.py`                |
| Change how cards are rendered as HTML  | `rendering/frames.py` / `io_cards.py` / `notes.py` |
| Change the detail overlay              | `rendering/detail.py`, `tray/details.py` |
| Change note grouping / summaries       | `core/note_grouping.py`             |
| Change SQL queries or IO parsing       | `core/card_data.py`                 |
| Change bridge dispatch / full renders  | `tray/tray.py`, `tray/render.py`    |
| Change targeted refresh / drag-drop / bulk-move logic | `tray/refresh.py`    |
| Change scheduling/tag/deck mutations   | `tray/actions.py`                   |
| Change filter/sort behavior            | `tray/filters.py`                   |
| Change external-change detection       | `tray/sync.py`                      |
| Change the window layout / toolbar / hosts | `viewer/widget.py`, `viewer/hosts.py` |
| Change the advanced filter panel       | `viewer/filter_bar.py`              |
| Change the sidebar tree                | `decks/sidebar.py`                  |
| Change deck data queries               | `decks/data.py`                     |
| Change deck add/rename/delete dialogs  | `decks/ops.py`                      |

## Common Tasks

### Adding a new card action

1. Add a button to the shared menu builder in `rendering/frames.py`
   (`build_card_menu` — used by single cards, IO groups, and note groups alike)
   and/or the detail overlay's `build_detail_actions` in `rendering/detail.py`.
2. Add a JS handler (usually in `web/js/10_mode_menus.js`) that calls
   `pycmd('your_action:payload')` — reuse `cardAction`/`selectionAction` where
   possible so it works from the card menu, the detail overlay, and the
   multiselect bar for free.
3. Handle it in `tray/tray.py`'s `_on_bridge_cmd()` / `_BRIDGE` table, or add it
   to `CARD_ACTIONS` in `tray/actions.py` if it's a plain scheduling action, and
   do a targeted DOM update where possible so scroll is preserved (see
   ARCHITECTURE.md's *Refresh Strategy*).

### Adding a new deck action

1. Add a button/menu item to the deck header HTML in `tray/builder.py`
   (`build_section` / `build_root_header`).
2. `deckAction` / `plusAction` in `web/js/30_sections.js` already forward
   `pycmd`.
3. Handle it in `tray/tray.py`'s `_on_bridge_cmd()`.

### Adding a new card state

1. Add the state string to `card_state_from_meta()` in `core/card_state.py`.
2. Add it to `STATE_PRIORITY`.
3. Add CSS (`.card-frame.state-xxx` and `.state-xxx .card-state-badge`) in
   `web/tray.css`.
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
- **Escape untrusted text** — user/template text (tags, field names, deck
  paths, …) is escaped Python-side (`html.escape`, aliased `_esc`) before it's
  ever embedded into HTML sent to the webview.
- **Rendering stays pure** — `rendering/` builders take plain data and return
  HTML strings; they never touch `mw`, the webview, or the collection beyond a
  `col` handle passed in for one lookup. Collection access and grouping logic
  live in `core/` and `tray/builder.py` / `tray/details.py`.
