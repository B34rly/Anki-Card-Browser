# Card Browser for Anki

A visual card browser add-on for Anki that lets you see all your cards at a glance — organized by deck, displayed as a scrollable grid with full support for Image Occlusion notes.

## Features

- **Visual card grid** — Cards are rendered in a responsive, masonry-style column layout so you can scan your collection quickly.
- **Deck tree sidebar** — A collapsible tree view mirrors your subdeck hierarchy. Click any subdeck to scroll straight to its section.
- **Scroll-spy sync** — As you scroll through cards, the sidebar automatically highlights the deck you're looking at.
- **Image Occlusion support** — IO notes are grouped into a single card with all mask shapes overlaid on the original image. Suspended masks are shown in grey.
- **View / Edit mode** — Toggle between a clean read-only view and an edit mode that exposes card actions and deck management controls.
- **Card actions** (edit mode) — Suspend / unsuspend, review now, via a per-card dropdown menu.
- **Deck actions** (edit mode) — Review due cards, force-review all cards, add subdecks, and add cards directly from the browser.
- **Expand overlay** — Click any card to see it full-size in a centered overlay (press Escape to close).
- **Light & dark mode** — Fully palette-aware styling for both Qt widgets and the web view, matching Anki's native appearance.

## Installation

Copy or symlink this folder into your Anki add-ons directory:

```
~/.local/share/Anki2/addons21/card-browser
```

Restart Anki. A **View** button will appear in the top toolbar.

## Usage

1. Click **View** in Anki's top toolbar to open the Card Browser window.
2. Select a top-level deck from the dropdown.
3. Browse cards in the grid. Click a subdeck in the sidebar to jump to it.
4. Toggle **Edit mode** in the toolbar to access card and deck actions.

## File Overview

| File | Purpose |
|------|---------|
| `__init__.py` | Registers the toolbar button via Anki's hook system |
| `viewer.py` | Main `QMainWindow` — layout, splitter, toolbar, mode toggle |
| `deck_tree.py` | `QTreeWidget`-based sidebar for navigating subdecks |
| `card_tray.py` | `AnkiWebView` that renders the card grid, IO grouping, menus, and overlay |
| `decks.py` | Helper functions for querying the deck tree from Anki's collection |

## Requirements

- Anki ≥ 24.x (Qt6 / PyQt6)
