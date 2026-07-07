"""Targeted, scroll-preserving page updates for CardTray.

RefreshMixin is one half of CardTray's implementation (the other is
render.RenderMixin). It keeps the rendered page in step with collection
changes — our own mutations and external ones — replacing only the affected
DOM instead of reloading, and falling back to a full render whenever a
targeted update can't be proven correct (the fallback conditions are the
hard-won part; see each method's comments). Shares CardTray's state contract
(see tray.py).
"""
from __future__ import annotations

import json

from anki.cards import CardId
from anki.decks import DeckId

from ..core.card_data import (
    get_card_decks,
    get_cards_metadata,
    get_deck_cards,
    get_note_cards,
)
from .filters import order_cids


class RefreshMixin:
    def refresh_tree(self) -> None:
        """Full re-render of the current tree (scroll position is preserved)."""
        if self._tree_root is not None:
            self._render_deck_tree(emit_tags=False)

    @property
    def known_cids(self):
        """Card ids currently rendered in the tree (view of the snapshot keys)."""
        return self._tracker.known_cards.keys()

    def consume_modified(self, col):
        """See ChangeTracker.consume_modified (scoped to the rendered tree)."""
        return self._tracker.consume_modified(col, self._tree_deck_ids(col))

    # ── Single-unit replacement ──

    def _replace_unit(self, col, cid: int) -> None:
        """Surgically replace one rendered unit — no count/title updates.

        Uses the builder's shared unit dispatch so IO and note groups rebuild
        as groups rather than collapsing into a single card.
        """
        try:
            html = self._builder.unit_html(col, cid)
            fn = "replaceGroup" if cid in self._builder.note_groups else "replaceCard"
            self._web.eval(f"{fn}({cid}, {json.dumps(html)})")
        except Exception:
            # The unit vanished mid-refresh; the caller's counts pass keeps
            # the page coherent and the next full render reconciles the rest.
            pass

    def _targeted_refresh_card(self, col, cid: int) -> None:
        """Re-render a single card / group in place, without a page reload.

        With active filters the card might now be excluded, so the whole
        section is rebuilt instead (still no full-page reload).
        """
        try:
            deck_id = col.get_card(CardId(cid)).did
        except Exception:
            # Card might not exist (edge case); fall back to a full re-render
            self.refresh_tree()
            return

        if self._filters.active:
            if self._tree_root is not None:
                if deck_id == self._tree_root.deck_id:
                    # Card is in the root deck's own area — not a section.
                    self._render_deck_tree(emit_tags=False)
                else:
                    self.refresh_section(deck_id)
                self._update_title(col)
            return

        self._replace_unit(col, cid)
        self._refresh_header_counts(col, deck_id)
        self._update_title(col)

    def refresh_note(self, col, nid: int, cids) -> None:
        """Re-render the on-screen card(s) for a single edited note.

        Resolves the rendered unit(s) for the note — normal cards, an IO
        group, or a note group — replaces each in place, then updates counts
        and the title once (not once per card). With active filters, rebuilds
        the affected section(s) instead. Scroll is preserved throughout.
        """
        if self._tree_root is None or not cids:
            return

        affected_decks = set(get_card_decks(col, list(cids)).values())

        if self._filters.active:
            # A filtered card may now be included/excluded; rebuild each
            # affected deck section once.
            for deck_id in affected_decks:
                if deck_id == self._tree_root.deck_id:
                    # Cards in the root deck's own area need a full re-render
                    self._render_deck_tree(emit_tags=False)
                    return
                self.refresh_section(deck_id)
            self._update_title(col)
            return

        # No filters: replace each group this note renders as (a note's cards
        # can span deck sections, producing several groups and/or standalone
        # cards), then any card not covered by a replaced group.
        note_cids = set(cids)
        covered: set[int] = set()
        for group_map in (self._builder.io_groups, self._builder.note_groups):
            for lead, members in group_map.items():
                if note_cids.intersection(members):
                    self._replace_unit(col, lead)
                    covered.update(members)
        for cid in cids:
            if cid not in covered:
                self._replace_unit(col, cid)

        for deck_id in affected_decks:
            self._refresh_header_counts(col, deck_id)
        self._update_title(col)

    def _refresh_modified(self, col, structural_handled: bool = False) -> None:
        """Refresh the notes an op touched, found via mod times.

        ``OpChanges`` says *that* something changed but not *what*; the
        tracker's mod-time watermark identifies the exact cards/notes
        regardless of where the change originated. Falls back to a full
        (scroll-preserving) re-render when the change is large or can't be
        pinpointed (undo restores old mod times, so nothing matches).
        *structural_handled* means membership changes were already
        spot-applied — an empty sweep is then expected (e.g. a deletion
        leaves no modified rows behind), not a pinpoint miss.
        """
        card_rows, nids, changed_anywhere = self.consume_modified(col)
        nid_set = set(nids)
        nid_set.update(nid for _cid, nid in card_rows)

        if not nid_set:
            if not changed_anywhere and not structural_handled:
                self.refresh_tree()
            return
        if len(nid_set) > 200:
            # Bulk change; resolving cards per note would be slower than one
            # render.
            self.refresh_tree()
            return

        known = self.known_cids
        to_refresh = [
            (nid, cids)
            for nid, cids in get_note_cards(col, list(nid_set)).items()
            if any(c in known for c in cids)
        ]

        if not to_refresh:
            return  # the change was outside the rendered tree
        if len(to_refresh) > 25 or (len(to_refresh) > 1 and self._filters.active):
            # Bulk change — or several sections to rebuild under active
            # filters, where per-note refreshes each rebuild a section (or
            # the whole tree); one render is cheaper and equally correct.
            self.refresh_tree()
            return
        for nid, cids in to_refresh:
            self.refresh_note(col, nid, cids)

    # ── Membership changes (adds / removals / moves — ours or external) ──

    def sync_external_changes(self, col) -> str:
        """Spot-apply membership changes by diffing the tree's cards.

        Compares the subtree's current cid→deck map against the snapshot from
        the last render: sections that gained new cards (adds) are rebuilt in
        place, moved units have their rendered element relocated into the
        target section (moveUnit — no rebuild, no flash), and removed cards
        are dropped from the DOM. Falls back to one full re-render (scroll
        also preserved) when that is cheaper or safer: bulk changes, active
        filters (membership must be re-derived), removals touching a rendered
        group or partial-group moves (stale group maps), or adds/move targets
        in the root deck's own card area (no standalone section to address).

        Returns what happened, so the caller can plan follow-up refreshes:
        ``"full"`` (full re-render done, everything is fresh), ``"spot"``
        (membership changes applied in place), or ``"none"`` (no membership
        change).
        """
        if self._tree_root is None:
            return "none"
        current = get_deck_cards(col, self._tree_deck_ids(col))
        added, removed, moved, previous = self._tracker.diff_membership(current)

        if not (added or removed or moved):
            return "none"

        def full() -> str:
            self._render_deck_tree(emit_tags=True)
            return "full"

        # A large external change (bulk import, sync, mass delete) is cheaper
        # and cleaner as one full re-render than hundreds of targeted edits.
        if len(added) + len(removed) + len(moved) > 40:
            return full()

        # Under active filters a changed card may belong to a section that
        # was filtered out of the DOM entirely; only a full re-render (which
        # re-applies the filters) can get membership right.
        if self._filters.active:
            return full()

        # A removed card that was rendered inside an IO or note group needs
        # its group rebuilt, but the group maps are now stale. Moves are
        # finer-grained: a group moving whole (to one target) keeps its
        # membership — and the maps — intact and travels as one unit, so
        # only partial-group moves force the full render.
        if removed:
            grouped = self._builder.grouped_cids()
            if any(c in grouped for c in removed):
                return full()
        move_units = self._plan_unit_moves(moved, current)
        if move_units is None:
            return full()

        # Sections to rebuild: where added cards landed (their HTML doesn't
        # exist yet). Moves need no rebuild — the rendered element relocates
        # (moveUnit), which is what keeps drags silent. The root deck's own
        # card area isn't an addressable section, so anything landing there
        # falls back.
        sections = {current[c] for c in added}
        if self._tree_root.deck_id in sections | {t for _, _, t in move_units}:
            return full()

        # Moves first: a section rebuild renders from the live collection,
        # so rebuilding a move's source/target afterwards can only agree
        # with (or supersede) the relocation — never duplicate it.
        self._apply_unit_moves(col, move_units)
        for did in sections:
            self.refresh_section(did)

        for cid in removed:
            self._web.eval(f"removeCard({cid})")

        self._refresh_all_header_counts(col)
        return "spot"

    def _plan_unit_moves(self, moved, current) -> list[tuple[str, int, int]] | None:
        """Fold moved cids into whole rendered units: (kind, lead, target).

        Returns None when the fold isn't clean — some rendered group moved
        only partially, or its cards scattered to different decks — which
        leaves the group maps stale and requires a full render.
        """
        units: list[tuple[str, int, int]] = []
        in_groups: set[int] = set()
        for group_map in (self._builder.io_groups, self._builder.note_groups):
            for lead, members in group_map.items():
                touched = [m for m in members if m in moved]
                if not touched:
                    continue
                targets = {current[m] for m in touched}
                if len(touched) != len(members) or len(targets) != 1:
                    return None
                units.append(("group", lead, targets.pop()))
                in_groups.update(members)
        units.extend(("card", c, current[c]) for c in moved if c not in in_groups)
        return units

    def _apply_unit_moves(self, col, units) -> None:
        """Relocate each moved unit's DOM node into its target section.

        For every target deck the intended order is computed the same way a
        fresh render would (own cids + active sort); the JS then anchors the
        node on the first following unit already in that container. Units
        are applied in reverse render order so a unit whose anchor is
        another moved unit finds it already in place.
        """
        by_target: dict[int, list[tuple[str, int]]] = {}
        for kind, lead, target in units:
            by_target.setdefault(target, []).append((kind, lead))

        today = col.sched.today
        for target, target_units in by_target.items():
            own = list(col.decks.cids(DeckId(target), children=False))
            meta = get_cards_metadata(col, own)
            ordered = order_cids(own, meta, today, self._filters)
            index = {cid: i for i, cid in enumerate(ordered)}

            def unit_pos(unit: tuple[str, int]) -> int:
                kind, lead = unit
                members = self._unit_members(kind, lead)
                return min((index.get(m, len(ordered)) for m in members),
                           default=len(ordered))

            for kind, lead in sorted(target_units, key=unit_pos, reverse=True):
                members = set(self._unit_members(kind, lead))
                after = [c for c in ordered[unit_pos((kind, lead)) + 1:]
                         if c not in members][:20]
                self._web.eval(
                    f"moveUnit({lead}, {json.dumps(kind)}, {target}, "
                    f"{json.dumps(after)})"
                )

    def _unit_members(self, kind: str, lead: int) -> list[int]:
        """The cids a rendered unit spans (a lone card, or its group's cards)."""
        if kind == "group":
            return (self._builder.io_groups.get(lead)
                    or self._builder.note_groups.get(lead, [lead]))
        return [lead]
