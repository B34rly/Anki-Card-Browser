# Card Browser for Anki

A visual card browser add-on for Anki that lets you see all your cards at a glance — organized by deck, displayed as a responsive grid, with full support for Image Occlusion notes.

## Features

- **Visual card grid** — Cards render in a responsive grid. Tall cards automatically span extra columns so wide content (images, tables) gets the room it needs.
- **Deck tree sidebar** — A collapsible tree mirrors your subdeck hierarchy. Click any subdeck to scroll straight to its section. Collapsed sections are remembered across restarts.
- **Scroll-spy sync** — As you scroll through cards, the sidebar highlights the deck you're looking at; scroll position is preserved across filtering and refreshes.
- **Always in sync** — Changes made elsewhere (Anki's Browser, Add Cards, undo, sync, other add-ons) appear automatically: the affected cards refresh in place, without a full reload or losing your scroll position.
- **Cards or notes display** — View each card individually, or group cards by their parent note with a compact field table and per-card state breakdown (`display_mode` config).
- **Image Occlusion support** — IO notes are grouped into a single card with all mask shapes overlaid on the original image. Suspended occlusions are greyed.
- **Filter, search & sort** — Live content search, state filter chips (New / Learning / Due / Upcoming / Suspended), an advanced panel (tag, flag, ease / interval / lapse / review ranges), and 10 sort modes.
- **Card state indicators** — Each card shows a coloured state badge and countdown; deck headers show live `N / L / U / D` counts.
- **View / Edit mode** — Toggle between a clean read-only view and an edit mode that exposes card and deck actions. Opens in Edit mode by default (configurable).
- **Card inspector** — Click any card for a full detail overlay: Q/A toggle, action bar, stats grid, review history, and ←/→ navigation between cards. Escape closes; chrome stays pinned while long content scrolls.
- **Inline editing** — Edit note fields right in the inspector (✎ Edit): every field is directly editable, Ctrl+Enter saves through Anki's undo system, and the grid refreshes in place. The `edit_target` config decides whether the card-frame pencils also edit inline or open Anki's Browser.
- **Card actions** (edit mode) — A per-card/group 3-dot menu with flag (1–7 + clear), add / remove tag, change deck, set due date, suspend / unsuspend, bury / unbury, forget, reposition, review now, and delete. Every action shows an in-page toast and is undoable with Ctrl+Z. Flagged cards show a coloured dot; buried cards are dimmed.
- **Multiselect & bulk actions** — Ctrl/Cmd-click (or Ctrl+A for all, Shift-click for ranges) selects cards; a bottom bar applies flags, suspend, bury, change deck, tags, or delete to the whole selection.
- **Drag & drop** — Drag cards (or whole selections and note groups) onto any deck header to move them — the card slides into its new section with no page flash.
- **Deck actions** (edit mode) — Review due cards, force-review all (with confirmation), add cards, add child / sibling subdecks, rename decks, and delete empty decks. Available from both the sidebar right-click menu and each deck header's **+** menu. Collapse/expand-all buttons in the toolbar.
- **Saved searches & filter chips** — Star a query to save it by name; active advanced filters show as removable chips. Tag pills on cards are click-to-filter.
- **Embedded or windowed** — Open inline in Anki's main window (default) or as a separate floating window (`mode` config).
- **Light & dark mode** — Fully palette-aware styling for both the Qt widgets and the web view.

## Installation

Copy or symlink this folder into your Anki add-ons directory:

```
~/.local/share/Anki2/addons21/card-browser
```

Restart Anki. A **Cards** button appears in the top toolbar.

## Usage

1. Click **Cards** in Anki's top toolbar to open the Card Browser.
2. Select a top-level deck from the dropdown.
3. Browse cards in the grid. Click a subdeck in the sidebar to jump to it, or use the search / filter / sort toolbar to narrow what's shown.
4. Use the view/edit toggle (next to the subdeck search) to switch between View and Edit mode.

## Configuration

Open **Tools → Add-ons → Card Browser → Config**. See [`config.md`](config.md) for details.

| Key | Default | Effect |
|-----|---------|--------|
| `mode` | `"embedded"` | `"embedded"` (inline in the main window) or `"window"` (separate floating window). Restart to apply. |
| `display_mode` | `"cards"` | `"cards"` (each card) or `"notes"` (group cards by note). Restart to apply. |
| `default_edit_mode` | `true` | Open in Edit mode (`true`) or View mode (`false`). Restart to apply. |
| `edit_target` | `"browser"` | Where the card-frame ✎ pencils go: `"browser"` (Anki's Browser) or `"inline"` (the overlay's field editor). The inspector's own Edit button is always inline. Restart to apply. |

## File Overview

| Path | Purpose |
|------|---------|
| `__init__.py` | Registers the **Cards** toolbar button and a collection-load cache reset |
| `core/` | Collection data + domain logic (metadata SQL, card states, note grouping) — no Qt, no HTML |
| `rendering/` | Pure HTML builders (card frames, IO overlays, note groups, detail overlay, inline editor) |
| `decks/` | Deck tree data, deck mutations, and the sidebar widget |
| `tray/` | The card tray: webview, Python↔JS bridge, rendering/refresh pipeline, actions, filters |
| `viewer/` | The outer widget: toolbar, filter bar, saved searches, window/embedded hosts |
| `web/` | `tray.css` + numbered `js/` chunks concatenated into the page script |
| `tests/` | Three-level pytest suite (pure logic → fake-webview widget → real-DOM WebEngine) |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a deeper tour and [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for a contributor walkthrough.

## Requirements

- Anki ≥ 24.x (Qt6 / PyQt6). Developed and tested against Anki 25.09.
- No external dependencies — only `anki` / `aqt` / PyQt.
