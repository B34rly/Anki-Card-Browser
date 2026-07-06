# Roadmap & Improvement Plan

Full-pass assessment (2026-07-06) after the package refactor, multiselect,
localized drag-drop, and detail-overlay work. Organised as: missing features,
UX, UI, code risks, and structural improvements. Effort tags: [S]mall (≤½ day),
[M]edium (1–2 days), [L]arge.

---

## 1 · Missing features

### Browse-parity gaps (owner directive: close, but not 100% of editing)

- **Inline field editing in the detail overlay** [M] — the single biggest gap.
  "Edit" currently bounces to Anki's Browser, which is exactly the context
  switch this add-on exists to avoid. Contenteditable fields (or plain
  textareas) in the detail overlay + `col.update_note` via the existing
  refresh pipeline would cover ~90 % of real edits. Images/LaTeX stay in
  Anki's editor.
- **Saved searches** [S] — persist named queries (collection config, like the
  collapse set); a star button next to the search box + a dropdown of saved
  ones. The search plumbing already exists.
- **Column/table view** [L] — a compact list mode for triage (sortable columns:
  sort field, deck, due, ease, lapses…). Grid is spatial; a table is faster for
  mass operations. Toggle lives next to the sort dropdown; selection/bulk bar
  is shared. Consider after inline editing — it's the other half of "replace
  Browse for daily use".
- **Find & Replace across selection** [M] — with multiselect done this is the
  natural next bulk action (`col.find_and_replace`), and Anki's Browse has it.
- **Review history in the detail overlay** [S] — Anki's Card Info shows the
  revlog; we already have the stats grid. One `revlog` query + a small table
  ("when · rating · interval · ease · time taken"). High value for the "cards
  as objects you inspect" story.
- **Notetype filter** [S] — a dropdown next to the tag filter (the metadata
  fetch already carries `mid`).
- **Select all** [S] — Ctrl+A selects all rendered units in view (respects
  filters); "N selected" already generalises.
- **Drag onto the sidebar** [M] — the HTML5 drag is a native Qt drag carrying
  `text/plain` cids, so `DeckTree` can accept drops directly
  (`dragEnterEvent`/`dropEvent` on the QTreeWidget → the existing
  `move_cards` path). This was earlier ruled convoluted, but the drag-source
  work made it cheap. The sidebar is the *natural* drop target for cross-tree
  moves.

### Modernisation features (the "cards as notes" vision)

- **Keyboard-first grid navigation** [M] — arrows move a focus ring across
  units, Enter opens detail, Space toggles selection, `s`/`b`/`1–7` act on the
  focused unit, `/` focuses search. Power users live in Browse because of
  keyboard speed; this is how the grid competes.
- **Quick add-card slot** [S] — an "+ Add card" ghost frame at the end of each
  deck section (edit mode) opening Add Cards pre-targeted at that deck.
- **Density control** [S] — compact/comfortable/spacious (CSS var for gap +
  base font, persisted).
- **Search history** [S] — last N queries in a dropdown under the search box.

## 2 · UX improvements

- **Action feedback (toasts)** [S] — every mutation is currently silent. A
  small in-page toast ("2 cards suspended", "Moved to *Biology::Cell*") makes
  bulk operations trustworthy. Pairs with the CollectionOp migration below
  (Anki then shows its own toasts + undo).
- **Visible undo** [M] — an Undo button/shortcut in the browser (calls
  `mw.undo()`); the existing external-change pipeline already repaints after
  undo. Best delivered via the CollectionOp migration (§5) so labels are right.
- **Empty & loading states** [S] — empty decks show a friendly "No cards —
  add one" CTA; placeholders get a shimmer instead of a static badge.
- **Active filters as removable chips** [S] — replace the text summary in
  row 2 with chips (`Tag: baking ✕`, `Ease ≤ 200 % ✕`); one click removes one
  filter. Much clearer than the current summary string + buried panel.
- **Search result count near the box** [S] — "17 matches" inline; the title
  carries it today but it's at the other end of the screen.
- **Collapse/expand all** [S] — one button in the toolbar.
- **Bottom padding when the selection bar is open** [S] — the bar currently
  overlaps the last card row.
- **Persist last deck + scroll across restarts** [S] — save to collection
  config on teardown; restore on open. The section-anchor scroll format
  already survives re-renders, so it serialises cleanly.
- **Clickable tags** [S] — tag pills (cards + detail overlay) set the tag
  filter on click.
- **Config dialog** [M] — display mode, default edit mode, density, eager
  limit; today they're raw JSON (`config.md`). Anki's addon-config hook is
  enough (`mw.addonManager.setConfigAction`).
- **Shortcut overlay** [S] — `?` shows a cheat-sheet once keyboard nav lands.

## 3 · UI improvements

- **Pin the overlay chrome** [S] — nav arrows and the close button scroll away
  with long content because `#overlay-card` is the scroll container.
  Restructure to header + scrollable body + fixed arrows.
- **Normalise card content typography** [S] — note templates bring arbitrary
  font sizes; clamp inside `.card-content` (e.g. `font-size: clamp(...)` or a
  max) so the grid keeps rhythm regardless of template CSS.
- **Consistent icon set** [S] — ✎ ⋮ ✕ ▸ are mixed Unicode glyphs; swap for a
  small inline-SVG set (the state badges already do this properly).
- **Deck-header progress strip** [S] — a 2 px due/total bar under each header
  gives an instant read of deck health; the counts already computed.
- **Lazy-fill fade-in** [S] — filled cards pop in abruptly; a 120 ms opacity
  transition on `fillCards` softens the grid while staying cheap.
- **Dark-mode audit** [S] — `color-mix` with system colours is mostly right;
  verify the selection glow, drop-target highlight, and detail stat tiles have
  enough contrast in dark themes (one screenshot pass with
  `prefers-color-scheme: dark` in the DOM harness).
- **Scrollbar styling** [S] — the webview scrollbar is stock Chromium and
  visually loud next to the styled content.

## 4 · Code risks — reloading / staleness / correctness

(From a dedicated audit pass; see also the accepted-issues list in
HANDOFF.md.)

- **Tag/flag dropdowns go stale after our own edits** [S fix] — `emit_tags`
  fires only on deck change, so adding a tag via the menu/bulk bar doesn't
  appear in the filter dropdown until the deck is switched. Fix: re-emit after
  tag mutations.
- **Two refresh pipelines to maintain** — our own mutations refresh via
  targeted calls; external changes via tracker/watermark. Every new mutation
  must remember its refresh (this is where past bugs came from). See §5 —
  the CollectionOp migration collapses the two into one.
- **Eager renders on every debounce tick** — a filtered result set near the
  120-card cap re-renders fully per keystroke pause (~120 ×
  `get_card`+template render). Acceptable now; revisit with a
  content-diffing or keep-DOM approach if typing ever feels sticky on big
  collections.
- **Whole-tree placeholder DOM at scale** — a 50 k-card collection mounts
  50 k placeholder divs. Fine to ~5–10 k; beyond that, section bodies should
  mount lazily (render children on expand/first scroll-into-view).
  [L, only when someone actually hits it]
- **Anki-version coupling** — `TrayWebView` relies on `AnkiWebView`
  internals (`allow_drops`, eval queueing) and `decks.get(default=False)`
  behaviour; a version bump can break silently. Add a CI job that runs the
  suite against the latest `anki`/`aqt` pip release monthly.
- **Window+embedded double-instantiation** — switching the `mode` config
  between opens leaves both hosts alive, each with a widget holding
  `operation_did_execute` hooks → duplicated refresh work. Cheap guard: close
  the other host inside `open_card_browser()`.

### Findings from the dedicated refresh/state audit (2026-07-06)

> **Status update:** the CollectionOp migration (§5) shipped 2026-07-06 and
> resolved findings 3, 4 and 5 by construction (tests in
> tests/test_op_pipeline.py). Findings 1, 2, 6, 7, 8, 9 remain — they are
> the residual state-sync batch.

Ordered by user-visible impact; all verified against the code. Most are [S]
fixes and should ship as one "state-sync batch" before new features.

1. **Selection not cleared/purged on drag-moves and menu deletes** — the
   drag path (`apply_local_move`) never evals `clearSelection()`, and JS
   `removeCard` never purges the id from `_selected`. After moving/deleting
   selected cards the bar count is wrong, plain clicks stay in
   toggle-selection mode, and a later single-card drag silently moves the
   whole stale selection. *Fix:* purge ids inside JS `removeCard` +
   `updateSelectionBar()`; eval `clearSelection()` in `apply_local_move`.
2. **`_unitEl` matches `data-group-lead` before `data-cid`** — deleting or
   moving the *inner* card that happens to be its note group's lead removes
   the whole group frame from the DOM (surviving cards vanish until the next
   render). *Fix:* targeted ops on inner cards must scope the lookup
   (`.note-cards-body [data-cid=…]` first), or pass an explicit
   unit-kind from Python.
3. **Partial-group mutations leave `note_groups`/`io_groups` stale** —
   change-deck/delete of one inner group card keeps the old membership, so a
   later `refresh_note` resurrects the departed card inside the old group and
   bulk/drag lead-expansion still includes it. The external-change path
   already guards this ("change touches a rendered group → full render");
   our own mutation path must apply the same guard. *Fix:* in `_move_cids` /
   inner-card delete, if moved/deleted cids intersect `grouped_cids()`
   without covering a whole group → full render (mirrors `sync_external_changes`).
4. **External edits never refresh the open detail overlay** — editing or
   deleting the shown card from Anki's Browser updates the grid but leaves
   the overlay stale/showing a deleted card. *Fix:* call
   `_refresh_open_detail` from `refresh_note` and the spot-removal path
   (close-if-gone already exists).
5. **"Force review all" refreshes nothing** — direct `set_due_date` with no
   hook and no targeted refresh; the window-mode browser (or the embedded one
   after backing out of review without answering) shows fully stale badges.
   *Fix:* `refresh_tree()` before `moveToState("review")`.
6. **`replaceSection` strips `.selected`** — targeted section rebuilds lose
   the visible highlight while the selection stays live. *Fix:* re-apply like
   `_swapUnit` does (and in `fillCards`).
7. **Search-debounce double render** — clicking a chip (or "Clear all
   filters") while the 300 ms timer is pending renders the identical page
   twice, with a visible flash and lost in-flight lazy fills. *Fix:*
   `self._search_timer.stop()` at the top of `_apply_filters`. One line.
8. **Section rebuilds collapse loaded cards to placeholders** — a targeted
   `replaceSection` (external add, drag target) swaps tall loaded cards for
   short placeholders, throwing the viewport when it happens above/around
   the reading position. *Fix:* render rebuilt sections eagerly when the
   section is small (`len(all_cids) <= EAGER_RENDER_LIMIT`), independent of
   filters — placeholder collapse then only affects genuinely huge sections.
9. **[RACE] Escape vs in-flight detail re-push** — a detail refresh landing
   during the close animation reopens an overlay Python believes is closed
   (no further refreshes). *Fix:* re-pushes call
   `showCardDetail(html, id, /*isRefresh=*/true)` and JS drops refresh
   pushes when the overlay is closed or closing.

## 5 · Structural improvements

- **Migrate mutations to `CollectionOp`** [DONE 2026-07-06] — today our
  own writes (suspend/flag/move/delete/tags) bypass Anki's op pipeline, so:
  no undo toasts, no automatic undo-status updates, and a *second* refresh
  pipeline exists just for our own actions. All the hard machinery to react
  to op-driven changes already works (tracker diff + watermark + targeted
  refresh — it handles external ops today). Moving our writes onto
  `CollectionOp` would: (1) give native undo entries/toasts for free, (2)
  delete the per-action targeted-refresh calls — every change, ours or not,
  flows through one pipeline, (3) remove a whole class of "forgot to refresh
  after new action X" bugs. Do it action-by-action behind the existing
  bridge handlers; the tests pin behaviour.
- **CI** [S] — GitHub Actions: `pytest tests/ -q` (offscreen works headless),
  `pyflakes`/`ruff`, `node --check web/js/*.js`. The suite is already
  CI-shaped (hard-exit handles the WebEngine teardown).
- **Release packaging** [S] — a `make dist` that zips into `.ankiaddon`
  (excluding tests/docs/HANDOFF), README screenshots for the AnkiWeb page,
  delete HANDOFF.md before publishing.
- **Typing** [M] — the collaborators (`PageBuilder`, `ChangeTracker`,
  `FilterState`) have clean seams now; add real type hints + mypy on core/
  and tray/ gradually.

## Suggested sequencing

1. **State-sync batch** [~1 session, do first]: the nine audit findings
   above — they are exactly the "weird reloading" class, most are small,
   and several were introduced by the new multiselect/localized-move
   features interacting with older machinery. Add regression tests per fix
   (the level-2/level-3 harness covers all of them).
2. **Quick wins batch** [~1 session]: toasts, tag-dropdown staleness fix,
   selection-bar padding, collapse/expand all, filter chips, revlog in
   detail, select-all, saved searches, overlay chrome pinning.
3. **Inline field editing** — the flagship feature.
4. **CollectionOp migration** — pays down the dual-pipeline risk before more
   mutating features pile on (and would have prevented findings 3–5 above
   by construction).
5. **Keyboard navigation + shortcut overlay.**
6. **Sidebar drag-drop + notetype filter + quick-add slots.**
7. **Table view** — last, it's the biggest and benefits from everything above.
