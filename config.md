## Card Browser Configuration

### `mode`

Controls how the Card Browser opens when you click **Cards** in the toolbar.

- **`"embedded"`** (default) — The browser replaces Anki's main content area,
  appearing inline like the Decks or Review screens. Click any other toolbar
  button (Decks, Add, Browse, etc.) to leave the browser.

- **`"window"`** — The browser opens in a separate floating window, allowing
  you to use it side-by-side with Anki's main window.

Restart Anki after changing this setting.

### `display_mode`

Controls how cards are grouped and displayed in the browser.

- **`"cards"`** (default) — Each card is displayed individually. This is the
  standard view and works well for most users.

- **`"notes"`** — Cards are grouped by their parent note. Single-card notes
  appear the same as cards mode. Multi-card notes show a compact field table
  with per-card state breakdowns and an expandable card list. Image Occlusion
  notes are unaffected. Section headers show both note and card counts.

Restart Anki after changing this setting.

### `default_edit_mode`

Controls whether the browser opens in **Edit** mode (`true`, the default) or
**View** mode (`false`). You can always flip between the two at runtime with the
view/edit toggle button next to the subdeck search box.

- **View mode** — A clean, read-only layout. Per-card edit buttons, the card
  action menu, and the deck "+" add buttons are hidden.
- **Edit mode** — Exposes per-card actions (edit, flag, tag, suspend, review,
  delete, …) and deck management controls (add card, add/rename/delete subdeck).

Restart Anki after changing this setting.
