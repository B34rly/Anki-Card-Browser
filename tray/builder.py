"""Page/section/unit HTML construction for the tray.

PageBuilder owns the per-render group maps (lead cid → member cids for IO and
note groups) and turns collection data into the tray's HTML. It never touches
the webview — CardTray pushes what it builds.

A RenderContext bundles everything a render pass needs (collection, prefetched
metadata, the filter result, the eager decision, collapse state), so section
building stays a pure function of its inputs.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from anki.cards import CardId
from anki.consts import (
    QUEUE_TYPE_SUSPENDED, QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED,
)
from anki.decks import DeckId

from ..core.card_data import (
    ACTIVE_ORDINAL_RE,
    extract_io_data,
    get_cards_metadata,
    get_note_fields,
    is_io_mid,
)
from ..rendering import (
    build_io_card_html,
    build_note_card_count,
    build_note_fields_table,
    build_note_group_html,
    format_deck_path,
    frame_classes,
    render_normal_card,
)
from ..core.card_state import (
    build_state_badge,
    card_countdown_from_meta,
    card_state_from_meta,
    group_flag,
)
from ..core.note_grouping import (
    group_cards_by_note,
    note_state_summary,
    note_summary_counts,
)
from .filters import FilterState, order_cids

# When filters are active and the whole result set is at most this many cards,
# sections render full card HTML up front instead of lazy placeholders — search
# results appear instantly and there is no lazy round-trip to lose to a bridge
# race. Larger result sets keep placeholder-based lazy loading.
EAGER_RENDER_LIMIT = 120


@dataclass
class RenderContext:
    """Everything one render pass needs, computed once by the caller."""

    col: object
    meta: dict
    today: int
    filters: FilterState
    allowed: set[int] | None  # None = no filters active
    eager: bool = False
    collapsed: set[int] = field(default_factory=set)


# ── IO-group helpers (shared by card building and the detail overlay) ──


def extract_group_io(cards):
    """Image src + mask shapes for an IO group's fetched cards.

    Tries the lead card first, then falls back to unioning every card's
    masks (some IO variants only carry the image on certain cards).
    Returns (img_src, masks); either may be empty when parsing fails.
    """
    img_src, masks = extract_io_data(cards[0].answer())
    if not img_src or not masks:
        all_masks: list[dict] = []
        found_src = img_src
        for gc in cards:
            src, ms = extract_io_data(gc.answer())
            if src and not found_src:
                found_src = src
            all_masks.extend(ms)
        if found_src and all_masks:
            img_src, masks = found_src, all_masks
    return img_src, masks


def io_suspended_ordinals(cards) -> set[str]:
    """Mask ordinals belonging to suspended cards (drawn grey)."""
    ords: set[str] = set()
    for gc in cards:
        if gc.queue == QUEUE_TYPE_SUSPENDED:
            mo = ACTIVE_ORDINAL_RE.search(gc.question())
            if mo:
                ords.add(mo.group(1))
    return ords


def cards_state_summary(cards, today) -> dict:
    """note_state_summary over already-fetched Card objects."""
    meta = {
        gc.id: {"queue": gc.queue, "type": gc.type, "due": gc.due}
        for gc in cards
    }
    return note_state_summary(meta, [gc.id for gc in cards], today)


class PageBuilder:
    """Builds the tray's HTML and tracks which cids render as groups."""

    def __init__(self, display_mode: str = "cards"):
        self.display_mode = display_mode
        self.io_groups: dict[int, list[int]] = {}    # lead cid → member cids
        self.note_groups: dict[int, list[int]] = {}  # lead cid → member cids

    def reset_groups(self) -> None:
        self.io_groups.clear()
        self.note_groups.clear()

    def expand_group_cids(self, cids) -> list[CardId]:
        """Expand any lead cid to its full IO/note group membership."""
        out: list[int] = []
        for c in cids:
            members = self.io_groups.get(int(c)) or self.note_groups.get(int(c))
            out.extend(members if members else [int(c)])
        return [CardId(c) for c in out]

    def grouped_cids(self) -> set[int]:
        """Every cid currently rendered as part of an IO or note group."""
        grouped: set[int] = set()
        for members in self.io_groups.values():
            grouped.update(members)
        for members in self.note_groups.values():
            grouped.update(members)
        return grouped

    # ── Full units (lazy-load fills, eager renders, targeted replaces) ──

    def unit_html(self, col, cid: int) -> str:
        """Full HTML for one rendered unit — IO group, note group, or card.

        The single dispatch shared by lazy loading and eager rendering, so a
        card fills identically no matter which path built it.
        """
        if cid in self.io_groups:
            return self.build_io_group(col, self.io_groups[cid])
        if cid in self.note_groups:
            return self.build_note_group(col, cid)
        return render_normal_card(col, cid)

    def _eager_html(self, col, cid: int, fallback: str) -> str:
        """Full unit HTML for eager (search-mode) rendering.

        Falls back to the lazy placeholder when the unit fails to render, so
        one broken template can't blank a whole results page.
        """
        try:
            return self.unit_html(col, cid)
        except Exception:
            return fallback

    def build_io_group(self, col, group_cids: list[int]) -> str:
        """Build full HTML for a group of IO cards (called during lazy load)."""
        cards = [col.get_card(CardId(gcid)) for gcid in group_cids]
        img_src, masks = extract_group_io(cards)
        if not img_src or not masks:
            return render_normal_card(col, group_cids[0])

        summary = cards_state_summary(cards, col.sched.today)
        try:
            io_tags = cards[0].note().tags
        except Exception:
            io_tags = []
        return build_io_card_html(
            img_src, masks, group_cids, io_suspended_ordinals(cards),
            summary["all_suspended"],
            state=summary["dominant_state"],
            countdown=summary["dominant_countdown"],
            tags=io_tags,
            all_buried=summary["all_buried"],
            flag=group_flag(gc.user_flag() for gc in cards),
        )

    def build_note_group(self, col, lead_cid: int) -> str:
        """Build full HTML for a multi-card note group (called during lazy load)."""
        group_cids = self.note_groups.get(lead_cid, [lead_cid])
        meta = get_cards_metadata(col, group_cids)
        today = col.sched.today

        # Determine nid from lead card
        m = meta.get(lead_cid)
        if m is None:
            return render_normal_card(col, lead_cid)
        nid = m["nid"]

        summary = note_state_summary(meta, group_cids, today)
        fields_table = build_note_fields_table(get_note_fields(col, nid))

        try:
            from anki.notes import NoteId
            note = col.get_note(NoteId(nid))
            tags = note.tags
        except Exception:
            tags = []

        return build_note_group_html(
            nid=nid,
            fields_table=fields_table,
            card_ids=group_cids,
            summary=summary,
            tags=tags,
            flag=group_flag(m.get("flags", 0) for m in meta.values()),
        )

    # ── Lazy placeholders ──

    @staticmethod
    def _placeholder_html(
        lazy_key: int, state: str, countdown: str, suspended: bool,
        buried: bool = False, inner: str = "", extra_attrs: str = "",
    ) -> str:
        """Build one lazy-load placeholder frame (shared by all item shapes)."""
        cls = frame_classes(state, suspended, buried, "card-placeholder")
        badge = build_state_badge(state, countdown)
        return (
            f'<div class="{cls}" data-lazy="{lazy_key}"{extra_attrs}>'
            f'  {badge}'
            f'  <div class="placeholder-inner">{inner}</div>'
            f'</div>'
        )

    def _group_placeholder(self, meta, today, cids: list[int], inner: str,
                           extra_attrs: str = "") -> str:
        """Placeholder for a card group (IO or note), keyed by its lead cid."""
        summary = note_state_summary(meta, cids, today)
        return self._placeholder_html(
            cids[0], summary["dominant_state"], summary["dominant_countdown"],
            summary["all_suspended"], summary["all_buried"],
            inner=inner, extra_attrs=extra_attrs,
        )

    def _card_placeholder(self, meta, today, cid: int) -> str:
        """Placeholder for a single standalone card."""
        m = meta.get(cid, {})
        return self._placeholder_html(
            cid,
            card_state_from_meta(m, today),
            card_countdown_from_meta(m, today),
            m.get("queue") == QUEUE_TYPE_SUSPENDED,
            m.get("queue") in (QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED),
        )

    # ── Item lists (one deck's own cards) ──

    def build_items(self, ctx: RenderContext, card_ids: Sequence[int]) -> str:
        """Dispatch to cards or notes item builder based on display mode."""
        if self.display_mode == "notes":
            return self._build_notes_items(ctx, card_ids)
        return self._build_cards_items(ctx, card_ids)

    def _build_cards_items(self, ctx: RenderContext, card_ids: Sequence[int]) -> str:
        """Item HTML for cards mode: lazy placeholders, or full card frames
        when ctx.eager (small filtered result sets)."""
        if not card_ids:
            return ""
        col, meta, today = ctx.col, ctx.meta, ctx.today

        # Group IO cards by note using bulk metadata
        note_groups: dict[int, list[int]] = {}
        order: list[tuple[str, int]] = []

        for cid in card_ids:
            m = meta.get(cid)
            if m is None:
                continue
            if is_io_mid(col, m["mid"]):
                nid = m["nid"]
                if nid not in note_groups:
                    note_groups[nid] = []
                    order.append(("note", nid))
                note_groups[nid].append(cid)
            else:
                order.append(("card", cid))

        parts: list[str] = []
        for kind, eid in order:
            if kind == "note":
                group_cids = note_groups[eid]
                self.io_groups[group_cids[0]] = group_cids
                io_badge = f'<span class="io-badge">{len(group_cids)} occlusion cards</span>'
                html = self._group_placeholder(meta, today, group_cids, io_badge)
                if ctx.eager:
                    html = self._eager_html(col, group_cids[0], html)
            else:
                html = self._card_placeholder(meta, today, eid)
                if ctx.eager:
                    html = self._eager_html(col, eid, html)
            parts.append(html)

        return "\n".join(parts)

    def _build_notes_items(self, ctx: RenderContext, card_ids: Sequence[int]) -> str:
        """Item HTML for notes mode: lazy placeholders, or full group frames
        when ctx.eager (small filtered result sets)."""
        if not card_ids:
            return ""
        col, meta, today = ctx.col, ctx.meta, ctx.today
        groups = group_cards_by_note(col, card_ids, meta)
        parts: list[str] = []

        for ng in groups:
            if ng.is_io:
                # IO notes render the same as cards mode
                self.io_groups[ng.cids[0]] = ng.cids
                io_badge = f'<span class="io-badge">{len(ng.cids)} occlusion cards</span>'
                html = self._group_placeholder(meta, today, ng.cids, io_badge)
            elif len(ng.cids) == 1:
                # Single-card notes render identically to cards mode
                html = self._card_placeholder(meta, today, ng.cids[0])
            else:
                # Multi-card note: render note group with field table
                self.note_groups[ng.cids[0]] = ng.cids
                summary = note_state_summary(meta, ng.cids, today)
                html = self._group_placeholder(
                    meta, today, ng.cids,
                    inner=build_note_card_count(summary),
                    extra_attrs=f' data-nid="{ng.nid}"',
                )
            if ctx.eager:
                html = self._eager_html(col, ng.cids[0], html)
            parts.append(html)

        return "\n".join(parts)

    # ── Deck sections ──

    def build_section(self, ctx: RenderContext, node, full_path: str,
                      depth: int) -> str:
        """Recursively build HTML for a collapsible deck section.

        ctx.meta must cover the section's subtree; ctx.allowed is the
        pre-computed filter set (None = no filters active).
        """
        col = ctx.col
        deck_id = node.deck_id
        own_cids = col.decks.cids(DeckId(deck_id), children=False)
        all_cids = col.decks.cids(DeckId(deck_id), children=True)

        own_items = order_cids(
            [c for c in own_cids if ctx.allowed is None or c in ctx.allowed],
            ctx.meta, ctx.today, ctx.filters,
        )
        cards_html = self.build_items(ctx, own_items) if own_items else ""

        children_html = ""
        for child in node.children:
            child_path = f"{full_path}::{child.name}"
            children_html += self.build_section(ctx, child, child_path, depth + 1)

        # Under filters: hide sections with no hits anywhere, and force the
        # rest open — a match inside a collapsed (possibly persisted-collapsed)
        # section would otherwise sit invisible in a height-0 body and never
        # lazy-load, looking like the search found nothing. The persisted
        # collapse state is untouched and applies again once filters clear.
        if ctx.allowed is not None:
            if not own_items and not children_html:
                return ""
            collapsed = False
        else:
            collapsed = deck_id in ctx.collapsed
        arrow_cls = "collapse-arrow collapsed" if collapsed else "collapse-arrow"
        body_style = ' style="height:0px"' if collapsed else ''
        name_html = format_deck_path(full_path)
        d = min(depth, 4)
        sc_html = self.state_counts_html(col, all_cids, ctx.meta, ctx.today)

        plus_menu = (
            f'<div class="plus-menu" id="plus-menu-{deck_id}">'
            f'<button onclick="plusAction(event,\'add_card\',{deck_id})">Add card…</button>'
            f'<button onclick="plusAction(event,\'add_subdeck\',{deck_id})">Add child subdeck…</button>'
            f'<button onclick="plusAction(event,\'add_sibling_subdeck\',{deck_id})">Add sibling subdeck…</button>'
            f'<hr class="plus-menu-sep">'
            f'<button onclick="plusAction(event,\'rename_deck\',{deck_id})">Rename deck…</button>'
            f'<button class="plus-menu-danger" onclick="plusAction(event,\'delete_deck\',{deck_id})">Delete deck…</button>'
            f'</div>'
        )

        return (
            f'<div class="deck-section" data-deck-id="{deck_id}">'
            f'<div class="deck-header depth-{d}" onclick="toggleSection({deck_id})">'
            f'<span class="{arrow_cls}" id="arrow-{deck_id}">▼</span>'
            f'<span class="deck-name">{name_html}</span>'
            f'<span class="deck-info">'
            f'<button class="header-plus-btn" onclick="togglePlusMenu(event,{deck_id})" title="Add…">+</button>'
            f'{plus_menu}'
            f'{sc_html}'
            f'<button class="deck-btn" onclick="deckAction(event,\'review_due_deck\',{deck_id})">Review due</button>'
            f'<button class="deck-btn" onclick="deckAction(event,\'force_review_deck\',{deck_id})">Force review all</button>'
            f'</span>'
            f'</div>'
            f'<div class="deck-body{" collapsed" if collapsed else ""}" id="body-{deck_id}"{body_style}>'
            f'<div class="deck-cards">{cards_html}</div>'
            f'{children_html}'
            f'</div>'
            f'</div>'
        )

    @staticmethod
    def build_root_header(root_deck_id: int) -> str:
        """The top-of-page bar for the tree root (plus-menu; no section header)."""
        plus_menu = (
            f'<div class="plus-menu" id="plus-menu-{root_deck_id}">'
            f'<button onclick="plusAction(event,\'add_card\',{root_deck_id})">Add card…</button>'
            f'<button onclick="plusAction(event,\'add_subdeck\',{root_deck_id})">Add child subdeck…</button>'
            f'</div>'
        )
        return (
            f'<div class="root-header" data-root-did="{root_deck_id}">'
            f'<button class="header-plus-btn" onclick="togglePlusMenu(event,{root_deck_id})" title="Add…">+</button>'
            f'{plus_menu}'
            f'</div>'
        )

    # ── Header counts and the widget title ──

    def state_counts_html(self, col, all_cids: Sequence[int], meta=None, today=None) -> str:
        """Build compact coloured state-count spans for a deck header.

        *meta*/*today* may be supplied (e.g. a whole-tree fetch reused across
        sections); a superset of *all_cids* is fine. They are fetched here only
        when omitted (targeted refreshes), keeping post-mutation data fresh.
        """
        if meta is None:
            meta = get_cards_metadata(col, all_cids) if all_cids else {}
        if today is None:
            today = col.sched.today if all_cids else 0

        if self.display_mode == "notes" and all_cids:
            sc = note_summary_counts(meta, all_cids, today)
            counts = (
                f'<span class="sc sc-new">{sc["new"]}N</span> '
                f'<span class="sc sc-learn">{sc["learn"]}L</span> '
                f'<span class="sc sc-upcoming">{sc["upcoming"]}U</span> '
                f'<span class="sc sc-due">{sc["due"]}D</span>'
            )
            return (
                f'<span class="card-count">{sc["notes"]} Notes / {sc["cards"]} '
                f'<span class="state-counts">({counts})</span> cards</span>'
            )

        total = len(all_cids)
        new = learn = due = upcoming = 0
        for cid in all_cids:
            m = meta.get(cid)
            if m is None:
                continue
            st = card_state_from_meta(m, today)
            if st == "new":
                new += 1
            elif st == "learn":
                learn += 1
            elif st == "review-due":
                due += 1
            elif st in ("review-soon", "review-mid", "review-later"):
                upcoming += 1
        counts = (
            f'<span class="sc sc-new">{new}N</span> '
            f'<span class="sc sc-learn">{learn}L</span> '
            f'<span class="sc sc-upcoming">{upcoming}U</span> '
            f'<span class="sc sc-due">{due}D</span>'
        )
        return (
            f'<span class="card-count">{total} '
            f'<span class="state-counts">({counts})</span> cards</span>'
        )

    def title_text(self, col, root_name: str,
                   visible_cids: Sequence[int], total_cids: Sequence[int],
                   meta=None, today=None) -> str:
        """The widget-header title, using note/card counts in notes mode."""
        has_filters = len(visible_cids) != len(total_cids)

        if self.display_mode == "notes":
            if meta is None:
                meta = get_cards_metadata(col, total_cids) if total_cids else {}
            if today is None:
                today = col.sched.today if total_cids else 0
            total_sc = note_summary_counts(meta, total_cids, today)
            if has_filters:
                vis_sc = note_summary_counts(meta, visible_cids, today)
                return (
                    f"{root_name}  ({vis_sc['notes']} / {total_sc['notes']} notes, "
                    f"{vis_sc['cards']} / {total_sc['cards']} cards)"
                )
            return (
                f"{root_name}  ({total_sc['notes']} notes / {total_sc['cards']} cards)"
            )
        if has_filters:
            return f"{root_name}  ({len(visible_cids)} / {len(total_cids)} cards)"
        return f"{root_name}  ({len(total_cids)} cards)"
