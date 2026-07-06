"""Full-page rendering and section/count updates for CardTray.

RenderMixin is one half of CardTray's implementation (the other is
refresh.RefreshMixin). It builds and pushes page content: full renders,
single-section rebuilds, header counts, the widget title, and lazy-load
fills. State it relies on (owned by CardTray, documented in tray.py):
_web, _builder, _filters, _tracker, _collapsed_decks, _tree_root, _tree_name,
_scroll_anchor, _eager, _edit_mode, _open_detail.
"""
from __future__ import annotations

import json

from anki.cards import CardId
from anki.decks import DeckId
from aqt import mw

from ..core.card_data import (
    get_cards_metadata,
    get_flags_for_cards,
    get_tags_for_cards,
)
from ..rendering import build_selection_bar, render_normal_card
from ..core.card_state import get_state_colors
from . import builder as builder_mod
from .assets import tray_css, tray_js
from .builder import RenderContext
from .filters import compute_allowed, order_cids


class RenderMixin:
    # ── Full render ──

    def set_deck_tree(self, root_node, root_name: str) -> None:
        """Render all subdecks as collapsible sections in one webview."""
        # Reset scroll only when switching to a different top-level deck; a
        # refresh of the same deck keeps the user's position.
        new_root = (
            self._tree_root is None
            or self._tree_root.deck_id != root_node.deck_id
        )
        self._tree_root = root_node
        self._tree_name = root_name
        self._builder.reset_groups()
        if new_root:
            self._scroll_anchor = None
        self._render_deck_tree(emit_tags=True)

    def _render_deck_tree(self, emit_tags: bool = True) -> None:
        """Internal render — builds and pushes HTML for the current deck tree."""
        root_node = self._tree_root
        root_name = self._tree_name
        self._builder.reset_groups()

        col = mw.col
        if col is None:
            self._web.stdHtml("<p>No collection loaded.</p>")
            return

        # A fresh page starts with the overlay closed.
        self._open_detail = None

        # Restore the persisted collapse state (config is the source of truth,
        # kept current by set_collapsed saves) before building sections from it.
        self._collapsed_decks = self._load_collapsed(col)

        all_cids = col.decks.cids(DeckId(root_node.deck_id), children=True)

        # Fetch metadata for the whole subtree ONCE and thread it through the
        # section/count builders. Every section's cids are a subset of
        # all_cids, so meta.get(cid) serves them all without re-querying.
        meta = get_cards_metadata(col, all_cids)
        today = col.sched.today

        # Snapshot what this render shows, so external changes can be diffed
        # (membership by deck) and pinpointed (mod-time watermark).
        self._tracker.snapshot(meta)

        # Emit available tags and flags for the toolbar (only on deck change)
        if emit_tags:
            self.tags_updated.emit(get_tags_for_cards(col, all_cids))
            self.flags_updated.emit(get_flags_for_cards(col, all_cids))

        # One filter pass over the whole subtree; sections intersect against it.
        allowed = compute_allowed(col, all_cids, meta, today, self._filters)
        visible = all_cids if allowed is None else [c for c in all_cids if c in allowed]
        # One eager decision per render, reused by targeted section refreshes
        # (filters can't change without another full render), so a refreshed
        # section can't disagree with the page around it.
        self._eager = (
            allowed is not None and len(visible) <= builder_mod.EAGER_RENDER_LIMIT
        )
        ctx = RenderContext(
            col=col, meta=meta, today=today, filters=self._filters,
            allowed=allowed, eager=self._eager, collapsed=self._collapsed_decks,
        )
        self.title = self._builder.title_text(
            col, root_name, visible, all_cids, meta, today
        )

        root_own = col.decks.cids(DeckId(root_node.deck_id), children=False)
        root_items = order_cids(
            [c for c in root_own if allowed is None or c in allowed],
            meta, today, self._filters,
        )
        root_cards = self._builder.build_items(ctx, root_items) if root_items else ""

        child_sections = ""
        for child in root_node.children:
            child_path = f"{root_name}::{child.name}"
            child_sections += self._builder.build_section(
                ctx, child, full_path=child_path, depth=0
            )

        body = self._builder.build_root_header(root_node.deck_id)
        if root_cards:
            body += f'<div class="deck-cards">{root_cards}</div>'
        body += child_sections

        self._render_page(body, restore_scroll=True)

    def _render_page(self, body_html: str, restore_scroll: bool = False) -> None:
        """Render the full page with CSS, body content, overlay, and JS.

        The current edit/view mode is baked into the page (no post-render
        eval, so edit controls never flash in the wrong mode). Webview evals
        are queued until the DOM is ready, so the scroll restore lands after
        load.
        """
        color_map = get_state_colors()
        color_vars = ":root { " + " ".join(
            f"{k}: {v};" for k, v in color_map.items()
        ) + " }"
        mode_js = "true" if self._edit_mode else "false"
        self._web.stdHtml(
            f"<style>{color_vars}\n{tray_css()}</style>"
            f"{body_html}"
            f'<div id="overlay" onclick="closeOverlay()">'
            f'  <div id="overlay-card" onclick="event.stopPropagation()">'
            f'    <button id="overlay-close" onclick="closeOverlay()">&times;</button>'
            f'    <div id="overlay-card-content"></div>'
            f'  </div>'
            f'</div>'
            f"{build_selection_bar()}"
            f"<script>var _initialEditMode = {mode_js};</script>"
            f"<script>{tray_js()}</script>",
            context=self,
        )
        # Restore the prior scroll position (filter change / same-deck refresh).
        if restore_scroll and self._scroll_anchor is not None:
            did, depth = self._scroll_anchor
            self._web.eval(f"restoreScroll({did}, {depth})")

    # ── Single-section rebuild ──

    def refresh_section(self, deck_id: int) -> None:
        """Rebuild one deck section in-place and update ancestor header counts."""
        col = mw.col
        if col is None or self._tree_root is None:
            return

        found = self._find_node_context(deck_id)
        if found is not None:
            node, full_path, depth = found
            all_cids = col.decks.cids(DeckId(deck_id), children=True)
            meta = get_cards_metadata(col, all_cids)
            today = col.sched.today
            allowed = compute_allowed(col, all_cids, meta, today, self._filters)
            ctx = RenderContext(
                col=col, meta=meta, today=today, filters=self._filters,
                allowed=allowed, eager=self._eager,
                collapsed=self._collapsed_decks,
            )
            html = self._builder.build_section(ctx, node, full_path, depth)
            if not html:
                # The section is now filtered out entirely; a targeted replace
                # can't remove it cleanly, so re-render the tree.
                self._render_deck_tree(emit_tags=False)
                return
            self._web.eval(f"replaceSection({deck_id}, {json.dumps(html)})")

        # Update ancestor header counts (the rebuilt section's own header is
        # already fresh — build_section embeds current counts).
        self._refresh_header_counts(col, deck_id, include_self=False)

    # ── Header counts and title ──

    def _refresh_header_counts(self, col, deck_id: int, include_self: bool = True) -> None:
        """Update the header count badges for a section and/or its ancestors.

        Fetches metadata once — the topmost ancestor's subtree is a superset
        of every other target's — instead of re-querying per header.
        """
        if self._tree_root is None:
            return
        targets: list[int] = []
        if include_self and self._find_node_context(deck_id) is not None:
            targets.append(deck_id)
        # The tree root renders as the widget title, not a section header.
        targets.extend(
            a for a in self._ancestor_deck_ids(deck_id)
            if a != self._tree_root.deck_id
        )
        if not targets:
            return
        cid_lists = {d: col.decks.cids(DeckId(d), children=True) for d in targets}
        meta = get_cards_metadata(col, max(cid_lists.values(), key=len))
        today = col.sched.today
        for d, cids in cid_lists.items():
            sc = self._builder.state_counts_html(col, cids, meta, today)
            self._web.eval(f"updateHeaderCounts({d}, {json.dumps(sc)})")

    def _refresh_all_header_counts(self, col) -> None:
        """Update all section header counts without touching card content."""
        if self._tree_root is None:
            return
        root_cids = col.decks.cids(DeckId(self._tree_root.deck_id), children=True)
        meta = get_cards_metadata(col, root_cids)
        today = col.sched.today
        self._update_section_counts(col, self._tree_root, meta, today)
        self._update_title(col)

    def _update_section_counts(self, col, node, meta, today) -> None:
        """Recursively update header counts for all sections."""
        for child in node.children:
            deck_id = child.deck_id
            all_cids = col.decks.cids(DeckId(deck_id), children=True)
            sc = self._builder.state_counts_html(col, all_cids, meta, today)
            self._web.eval(f"updateHeaderCounts({deck_id}, {json.dumps(sc)})")
            self._update_section_counts(col, child, meta, today)

    def _update_title(self, col) -> None:
        """Recalculate and update the header title with current card counts."""
        if self._tree_root is None:
            return
        all_cids = col.decks.cids(DeckId(self._tree_root.deck_id), children=True)
        # Metadata is needed for notes-mode counts and state/criteria filters.
        needs_meta = bool(
            self._builder.display_mode == "notes"
            or self._filters.active_chips or self._filters.criteria
        )
        meta = get_cards_metadata(col, all_cids) if (needs_meta and all_cids) else None
        today = col.sched.today if all_cids else 0
        allowed = compute_allowed(col, all_cids, meta or {}, today, self._filters)
        visible = all_cids if allowed is None else [c for c in all_cids if c in allowed]
        self.title = self._builder.title_text(
            col, self._tree_name, visible, all_cids, meta, today
        )

    # ── Tree lookups ──

    def _tree_deck_ids(self, col) -> list[int]:
        """Deck ids of the rendered tree (root plus all descendants)."""
        if self._tree_root is None:
            return []
        try:
            return list(col.decks.deck_and_child_ids(DeckId(self._tree_root.deck_id)))
        except Exception:
            return [self._tree_root.deck_id]

    def _find_node_context(
        self, deck_id: int, node=None, parent_path: str = "", depth: int = 0
    ) -> tuple | None:
        """Find (node, full_path, depth) for *deck_id* within the current tree."""
        if node is None:
            node = self._tree_root
            if node is None:
                return None
            parent_path = self._tree_name
            # Root's children start at depth 0 (root itself is the title bar).
            for child in node.children:
                child_path = f"{parent_path}::{child.name}"
                if child.deck_id == deck_id:
                    return (child, child_path, 0)
                found = self._find_node_context(deck_id, child, child_path, 1)
                if found is not None:
                    return found
            return None
        for child in node.children:
            child_path = f"{parent_path}::{child.name}"
            if child.deck_id == deck_id:
                return (child, child_path, depth)
            found = self._find_node_context(deck_id, child, child_path, depth + 1)
            if found is not None:
                return found
        return None

    def _ancestor_deck_ids(self, deck_id: int) -> list[int]:
        """Deck IDs from the target up to (but not including) the tree root."""
        col = mw.col
        if col is None:
            return []
        deck = col.decks.get(DeckId(deck_id))
        if not deck:
            return []
        parts = deck["name"].split("::")
        ancestors: list[int] = []
        for i in range(len(parts) - 1, 0, -1):
            parent_name = "::".join(parts[:i])
            pid = col.decks.id_for_name(parent_name)
            if pid is not None:
                ancestors.append(pid)
        return ancestors

    # ── Lazy-load / preview serving ──

    def _on_lazy_load(self, col, payload: str) -> None:
        """Handle lazy_load bridge command: render requested cards and inject."""
        cids_str = [c.strip() for c in payload.split(",") if c.strip()]
        results: dict[str, str] = {}
        for cid_s in cids_str:
            try:
                results[cid_s] = self._builder.unit_html(col, int(cid_s))
            except Exception:
                # The card vanished between render and lazy load (external
                # delete, stale group map). Drop its placeholder — leaving it
                # would make the JS rescue sweep re-request it forever.
                self._web.eval(f"removeCard({int(cid_s)})")
        if results:
            self._web.eval(f"fillCards({json.dumps(results)})")

    def _on_lazy_load_note_cards(self, col, payload: str) -> None:
        """Render the individual cards inside an expanded note group."""
        cids = [int(c.strip()) for c in payload.split(",") if c.strip()]
        if not cids:
            return
        combined = "\n".join(render_normal_card(col, cid) for cid in cids)
        # The note-group body is keyed by its lead (first) cid.
        self._web.eval(f"fillNoteCards({cids[0]}, {json.dumps(combined)})")

    def _on_preview_card(self, col, payload: str) -> None:
        """Render a single card's answer for the overlay's preview area."""
        card = col.get_card(CardId(int(payload.strip())))
        self._web.eval(f"fillCardPreview({json.dumps(card.answer())})")

    def scroll_to_deck(self, deck_id: int) -> None:
        """Scroll the webview to a specific deck section."""
        self._web.eval(f"scrollToSection({deck_id})")
