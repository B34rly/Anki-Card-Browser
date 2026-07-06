# Card Browser — Pre-Release Checklist

Working notes for the push to public release. **Delete this file before the repo
goes public** (it's a scratch doc, not shipped documentation).

---

## Status snapshot

- Branch: `main`. **Nothing is committed** — all work is in the working tree
  (two sessions' worth: the card-actions/bug-fix batch, plus this session's
  external-sync rework, cleanups, and doc refresh).
- All modules compile (`python3 -m py_compile *.py`), pyflakes-clean, and the
  embedded JS passes `node --check`. Python↔JS bridge names cross-checked.
- **Not GUI-tested** — this environment can't drive the Anki UI. Run the smoke
  tests below in live Anki before shipping. Recommended: run Anki from a
  terminal so tracebacks are visible.

---

## What changed this session (all uncommitted)

### External-change sync rework (the "edits don't show up" pain point)
The old design could only pinpoint edits made through *our* edit button (it
tracked the Browser instance it had opened). Replaced with two per-render
snapshots in `CardTray`:

- **`_known_cards`: cid → deck id.** `sync_external_changes()` diffs it against
  the live collection on every external op: adds spot-rebuild the receiving
  section, deck **moves rebuild both ends**, removals drop DOM nodes. Falls back
  to one full (scroll-preserving) re-render for bulk changes (>40), active
  filters, or changes touching a rendered IO/note group.
- **`_mod_watermark`: epoch-seconds.** `consume_modified()` queries
  `cards`/`notes` for `mod >= watermark`, so `_refresh_modified()` (viewer)
  refreshes exactly the notes an op touched — regardless of where the edit came
  from (Browser, Add Cards, other add-ons). Undo restores old mod times and
  matches nothing → full re-render fallback. Caps: >200 candidate notes or >25
  in-tree notes → full re-render.
- `changes.deck`/`changes.notetype` → repopulate the deck dropdown (renames keep
  ids but change labels) + full render. **`sync_did_finish` → full refresh**
  (synced changes carry remote mod times; the watermark can't see them).
- The whole op handler is wrapped in try/except → full refresh, so a targeted-
  refresh edge case can never strand a stale view or break the hook chain.

### Profile-close teardown (new)
Module-level `profile_will_close` hook in `viewer.py` closes the window host and
tears down the embedded widget (`EmbeddedBrowser.teardown()`), so no stale
collection state survives a profile switch. Host singletons + their hooks remain
and no-op until reopened.

### Fixes
- `AddCards` now opened via `aqt.dialogs.open("AddCards", mw)` (both the tray
  "+" menu and the sidebar context menu) instead of direct instantiation —
  single-instance semantics + tracked on profile close.
- `replaceGroup`/`removeGroup` in JS fall back to the `[data-lazy]` placeholder,
  so acting on a not-yet-loaded note group works.
- Deleting/moving a card that renders *inside* a group no longer nukes or
  strands the group (group-membership check forces a clean re-render).
- Initial edit/view mode is baked into the page (`_initialEditMode`) instead of
  eval'd after load — no flash of the wrong controls; also removes a redundant
  post-render eval.
- Deck add/rename/delete from the "+" menu rendered the tray **twice** (once in
  the tray, once via the viewer signal); now renders once.
- Group flag indicator: IO and note groups now show the flag dot when all their
  cards share one flag (flagging a group previously gave no visual feedback).
- Stale lazy-load requests for vanished cards are skipped instead of raising in
  the bridge handler.

### Performance
- Filter pass (search SQL included) runs **once per render** over the subtree
  (`_compute_allowed`); sections intersect against it. Previously: once for the
  title + once per section.
- `_refresh_header_counts` fetches metadata **once** (topmost ancestor's subtree
  is a superset) instead of per ancestor; `refresh_section` reuses it and no
  longer re-sends counts its own HTML already contains.
- Header counts are no longer recomputed for the whole tree on every external op
  — only when membership actually changed.
- `get_cards_metadata` now includes `did`; new lightweight `get_card_decks`.

### Cleanups
- Removed `_pending_edit_cid`/`_edit_browser`/`_edited_note_id` (superseded by
  the watermark), the dead unknown-action fallback in `_on_bridge_cmd`, and a
  duplicate CSS rule.
- Deduped: placeholder builders (`_placeholder_html`/`_group_placeholder`),
  filter-panel range rows (`_add_range_row`), criteria/summary builders, SVG
  icon loading (`_svg_icon`), `_has_filters` property.
- `card_rendering.py` imports hoisted to module level.
- Docs rewritten to match (README, ARCHITECTURE, CONTRIBUTING, config.md) —
  including previously wrong claims (scroll payload, profile teardown,
  "pending Add-Cards target").

### Multi-agent review round (fixes applied after the above)
An 8-angle review over the full working-tree diff surfaced these; all fixed:
- **Collapse-state corruption risk**: `scrollToSection` re-used the
  *toggle* command to mean "expand"; a race with a re-render could invert and
  persist the wrong state. All collapse reporting now sends the explicit end
  state (`set_collapsed:<did>:<0|1>`), never a toggle.
- **Bulk edits under filters**: up to 25 consecutive full renders (one per
  note) — now one render when >1 note needs refreshing with filters active.
- **Watermark cost**: `consume_modified` did two whole-table `mod` scans per
  external op; now restricted to the rendered tree via the indexed
  `cards.did` (with a global existence probe only to detect the undo case,
  and a >900-deck fallback). Returns `(cards, nids, changed_anywhere)`.
- **External delete regression**: an empty watermark sweep after a spot-applied
  deletion triggered a needless full render (`structural_handled` now guards).
- **Membership diff cost**: `sync_external_changes` now reads the cid→did map
  straight off the `did` index (`get_deck_cards`) instead of cids-then-chunked
  id lookups.
- **Per-card waste**: `refresh_note` replaced units via a helper that also
  refreshed counts+title *per card*; split `_replace_unit` out — counts and
  title now update once per note. Per-note `card_ids_of_note`/`get_card`/
  `get_note` loops replaced with bulk helpers (`get_note_cards`, metadata).
- **Placeholder styling**: buried cards/groups now get the `buried` class in
  placeholders (loaded cards already dimmed).
- **Dedup**: deck add/rename/delete/add-cards dialogs unified in new
  `deck_ops.py` (was copy-pasted in `deck_tree.py` and `card_tray.py`);
  JS replace/remove now share `_unitEl`/`_swapUnit`; group-flag consensus in
  one `group_flag()` helper; card-frame class lists in one `frame_classes()`;
  `_build_io_group` reuses `note_state_summary`; `_anchorSection` stops at the
  first section below the viewport top instead of measuring all.
- **Accepted / not fixed** (known, low impact): an external add is rendered by
  the spot section-rebuild and then once more by the note refresh (bounded,
  idempotent); an in-tree undo can stay stale if another in-tree change lands
  in the same watermark window (converges on the next op or manual refresh);
  flag colours are intentionally Anki's fixed palette.

### Bug fix: search hits hidden by collapsed sections (owner-reported)
"When searching for a card, it does not get rendered when present." Cause: a
match inside a collapsed (possibly persisted-collapsed) section sat in a
height-0 `.deck-body`; the lazy-load IntersectionObserver never fired, so the
title counted the hit but nothing was visible. Fix (`_build_section`): while
any filter is active, sections render **force-expanded** (persisted collapse
state untouched — it applies again when filters clear), and sections with no
hits anywhere in their subtree are hidden entirely instead of rendering as
empty shells.

---

## Smoke-test checklist (run in live Anki before committing)

Previous session's fixes:
1. **Bottom bar**: edit/add a card with the browser open → no "Get Shared /
   Create Deck / Import File" toolbar flash.
2. **Scroll**: scroll deep into a subdeck, hit manual refresh → same heading.
3. **Plus-menu**: open `+` on an empty subdeck and the bottom-most deck →
   options clickable, on-screen.
4. **Collapse persistence**: collapse decks, restart Anki → still collapsed;
   home deck list unaffected.

This session's changes:
5. **External edit**: open Anki's Browser *yourself* (toolbar), edit a note
   that's visible in the card browser → card refreshes in place, no stale
   content, scroll intact.
6. **External move**: in the Browser, change a visible card's deck to another
   subdeck of the same tree → it disappears from the old section and appears in
   the new one.
7. **External suspend/flag**: suspend and flag a visible card from the Browser →
   dimming/dot appear without a manual refresh.
8. **Add Cards**: add via Anki's normal Add (not our button) → appears in its
   section; the AddCards dialog opens focused if already open (no duplicates).
9. **Undo**: edit a note externally, then Ctrl+Z in the main window → browser
   shows the restored content (via full-refresh fallback).
10. **Sync**: sync with a change from another device → browser refreshes.
11. **Profile switch**: switch profiles with the browser open → no traceback;
    reopening shows the new profile's decks.
12. **Edit mode default**: browser opens in Edit mode; toggle to View → menus
    and "+" hidden; no wrong-mode flash on refresh.
13. **Group flag**: flag an IO group / note group → dot appears on the group.
14. **Notes mode** (`display_mode: "notes"`): repeat 5–7 with a multi-card note.
15. **Sidebar jump**: collapse a deep subdeck, click it in the sidebar → it
    expands and scrolls; refresh → it stays expanded (explicit-state sync).
16. **Deck menus**: add/rename/delete a subdeck from BOTH the sidebar
    right-click menu and a header "+" menu (flows now share `deck_ops.py`).
17. **Search vs collapse**: collapse a subdeck, search for text on a card
    inside it → the section opens and the card renders; sections without hits
    disappear; clear the search → the section is collapsed again (and the
    others restore their previous state).

## After smoke-testing

1. **Commit** (branch off `main` first if you want review): suggested split —
   feature batch / bug fixes / sync rework + cleanups / docs.
2. **Delete this file.**
3. Optional next features (owner's Browse-parity directive, unbuilt): search-
   syntax bar + saved searches; inline field editing; multi-select + bulk
   actions; column/table view.

## Verify / build commands

```
python3 -m py_compile *.py     # syntax
python3 -m pyflakes *.py       # lint (installed)
```

Install path (already the working dir): `~/.local/share/Anki2/addons21/card-browser`.
Restart Anki to load code changes; the **Cards** toolbar button opens the browser.
