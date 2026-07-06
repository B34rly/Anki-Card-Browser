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

from ..core.card_data import get_card_decks, get_deck_cards


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

    def refresh_units(self, col, lead_cids) -> None:
        """Refresh several rendered units after a bulk mutation.

        Under filters (visibility may have changed) or for large selections,
        one full render is cheaper and equally correct.
        """
        if self._filters.active or len(lead_cids) > 25:
            self.refresh_tree()
            return
        for lead in lead_cids:
            self._replace_unit(col, lead)
        for did in set(get_card_decks(col, [int(c) for c in lead_cids]).values()):
            self._refresh_header_counts(col, did)
        self._update_title(col)

    # ── Our own moves (drag-drop / bulk change-deck) ──

    def apply_local_move(self, col, lead_cids, moved_cids, src_dids,
                         target_did: int) -> None:
        """Update the page after we moved *moved_cids* to *target_did*.

        Targeted path: drop the moved unit(s) from the DOM, rebuild only the
        receiving section, and update the source/ancestor counts — no page
        reload, scroll untouched. Falls back to one full (scroll-preserving)
        re-render whenever the targeted path can't be proven correct:

        - active filters — the target section may be absent from the DOM
          entirely (filtered out), so there is nothing to rebuild into;
        - the move touches the tree root's own card area — it renders as a
          bare card grid, not a rebuildable section;
        - the target isn't in the rendered tree (defensive; drops only ever
          target in-tree headers).

        The membership snapshot is updated either way so the next external-op
        diff doesn't mistake our own move for an external one (undo still
        shows up as a diff and is spot-applied).
        """
        self._tracker.record_move(moved_cids, target_did)

        root_id = self._tree_root.deck_id if self._tree_root else None
        if (
            self._filters.active
            or root_id is None
            or target_did == root_id
            or root_id in src_dids
            or self._find_node_context(target_did) is None
        ):
            self._render_deck_tree(emit_tags=False)
            return

        # Remove the old unit(s) first: after the target section rebuild, a
        # merged note group could reuse the same lead id.
        for lead in lead_cids:
            self._web.eval(f"removeCard({int(lead)})")
        self.refresh_section(target_did)
        for did in set(src_dids):
            if did != target_did:
                self._refresh_header_counts(col, did)
        self._update_title(col)
        self._refresh_open_detail(col)

    # ── External changes (Anki's Browser, Add Cards, undo, other add-ons) ──

    def sync_external_changes(self, col) -> str:
        """Spot-apply external membership changes by diffing the tree's cards.

        Compares the subtree's current cid→deck map against the snapshot from
        the last render: sections that gained cards (adds, moves in) are
        rebuilt in place, sections that lost moved cards are rebuilt too, and
        removed cards are dropped from the DOM. Falls back to one full
        re-render (scroll also preserved) when that is cheaper or safer: bulk
        changes, active filters (membership must be re-derived), a change
        touching a rendered group (stale group maps), or an add landing in
        the root deck's own card area (no standalone section to rebuild).

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

        # A removed/moved card that was rendered inside an IO or note group
        # needs its group rebuilt, but the group maps are now stale.
        if removed or moved:
            grouped = self._builder.grouped_cids()
            if any(c in grouped for c in removed) or any(c in grouped for c in moved):
                return full()

        # Sections to rebuild: where added cards landed, and both ends of a
        # move.
        sections: set[int] = set()
        for c in added:
            sections.add(current[c])
        for c in moved:
            sections.add(current[c])
            sections.add(previous[c])
        if self._tree_root.deck_id in sections:
            return full()
        for did in sections:
            self.refresh_section(did)

        for cid in removed:
            self._web.eval(f"removeCard({cid})")

        self._refresh_all_header_counts(col)
        return "spot"
