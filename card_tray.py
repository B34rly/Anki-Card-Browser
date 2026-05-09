from __future__ import annotations

import json
from collections.abc import Sequence

from anki.cards import CardId
from anki.consts import QUEUE_TYPE_SUSPENDED
from anki.decks import DeckId
from aqt import mw
from aqt.webview import AnkiWebView, AnkiWebViewKind
from aqt.qt import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    QInputDialog,
    QMessageBox,
    pyqtSignal,
)

from .tray_styles import TRAY_CSS
from .tray_js import TRAY_JS
from .card_state import (
    card_state_from_meta,
    card_countdown_from_meta,
    build_state_badge,
    get_state_colors,
    filter_cards_by_states,
    filter_cards_by_criteria,
    sort_cards,
    STATE_PRIORITY,
)
from .card_data import (
    get_cards_metadata,
    is_io_mid,
    extract_io_data,
    search_cards_by_content,
    filter_cards_by_tag,
    get_tags_for_cards,
    get_flags_for_cards,
    get_note_fields,
    get_card_template_names,
    ACTIVE_ORDINAL_RE,
)
from .card_rendering import (
    build_io_card_html,
    render_normal_card,
    format_deck_path,
    build_note_fields_table,
    build_note_group_html,
    build_note_card_count,
)
from .note_grouping import (
    group_cards_by_note,
    note_state_summary,
    note_summary_counts,
)


class CardTray(QWidget):
    """Displays cards in a single AnkiWebView with hover, expand, and menu."""

    # Emits deck_id of the section currently visible at the top of the scroll
    visible_section_changed = pyqtSignal(object)

    # Emits when a new subdeck is created (so the viewer can refresh the tree)
    subdeck_created = pyqtSignal()

    # Emits sorted list of tag strings for the current deck
    tags_updated = pyqtSignal(list)

    # Emits sorted list of flag ints for the current deck
    flags_updated = pyqtSignal(list)

    # Emits after bridge cmd handles a card action (so viewer suppresses op hook)
    card_action_handled = pyqtSignal()

    def __init__(self, title: str = "", parent=None, display_mode: str = "cards"):
        super().__init__(parent)

        self._display_mode: str = display_mode
        self._edit_mode: bool = False
        self._collapsed_decks: set[int] = set()
        self._io_group_map: dict[int, list[int]] = {}  # lead_cid → [group cids]
        self._note_group_map: dict[int, list[int]] = {}  # lead_cid → [note group cids]

        # Context tracking for deferred targeted refresh
        self._pending_edit_cid: int | None = None
        self._pending_add_deck_id: int | None = None

        # Filter/sort state (set from viewer toolbar)
        self._search_text: str = ""
        self._active_chips: set[str] = set()
        self._tag_filter: str = ""
        self._sort_key: str = "deck"
        self._sort_reverse: bool = False
        self._criteria: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel(title)
        self._header.setStyleSheet(
            "font-size: 14px; font-weight: 600; padding: 8px 12px;"
        )
        layout.addWidget(self._header, 0)

        self._web = AnkiWebView(parent=self, kind=AnkiWebViewKind.DEFAULT)
        self._web.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._web.set_bridge_command(self._on_bridge_cmd, self)
        layout.addWidget(self._web, 1)

    @property
    def title(self) -> str:
        return self._header.text()

    @title.setter
    def title(self, value: str):
        self._header.setText(value)

    @property
    def display_mode(self) -> str:
        return self._display_mode

    @display_mode.setter
    def display_mode(self, value: str) -> None:
        self._display_mode = value

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool) -> None:
        self._edit_mode = value
        self._web.eval(f"setEditMode({'true' if value else 'false'})")

    # ── Bridge commands from JS ──

    def _on_bridge_cmd(self, cmd: str) -> None:
        col = mw.col
        if col is None:
            return
        if ":" not in cmd:
            return
        action, payload = cmd.split(":", 1)

        if action == "visible_section":
            self.visible_section_changed.emit(int(payload))
            return

        # Collapse/expand state — no re-render needed
        if action == "toggle_section":
            deck_id = int(payload)
            self._collapsed_decks.symmetric_difference_update({deck_id})
            return

        if action == "lazy_load":
            self._on_lazy_load(col, payload)
            return

        if action == "lazy_load_note_cards":
            self._on_lazy_load_note_cards(col, payload)
            return

        if action == "preview_card":
            self._on_preview_card(col, payload)
            return

        if action == "review_due_deck":
            # Open Anki's reviewer filtered to this deck (due cards only)
            deck_id = int(payload)
            deck = col.decks.get(DeckId(deck_id))
            if deck:
                col.decks.set_current(DeckId(deck_id))
                mw.moveToState("review")
            return

        if action == "force_review_deck":
            # Set all cards in the deck to due today, then start review
            deck_id = int(payload)
            cids = col.decks.cids(DeckId(deck_id), children=True)
            if cids:
                col.sched.set_due_date([CardId(c) for c in cids], "0")
                col.decks.set_current(DeckId(deck_id))
                mw.moveToState("review")
            return

        if action == "add_card":
            deck_id = int(payload)
            self._pending_add_deck_id = deck_id
            col.decks.set_current(DeckId(deck_id))
            from aqt.addcards import AddCards
            add = AddCards(mw)
            add.show()
            return

        if action == "edit_card":
            self._pending_edit_cid = int(payload)
            from aqt import dialogs
            browser = dialogs.open("Browser", mw)
            if browser:
                browser.search_for(f"cid:{payload}")
            return

        if action == "add_subdeck":
            deck_id = int(payload)
            deck = col.decks.get(DeckId(deck_id))
            if not deck:
                return
            parent_name = deck["name"]
            name, ok = QInputDialog.getText(
                self, "New Subdeck", f"Subdeck name under {parent_name}:"
            )
            if ok and name.strip():
                full_name = f"{parent_name}::{name.strip()}"
                col.decks.id(full_name)
                if self._tree_root is not None:
                    from .decks import find_deck_node
                    new_root = find_deck_node(self._tree_root.deck_id)
                    if new_root:
                        self.set_deck_tree(new_root, self._tree_name)
                self.subdeck_created.emit()
            return

        if action == "add_sibling_subdeck":
            deck_id = int(payload)
            deck = col.decks.get(DeckId(deck_id))
            if not deck:
                return
            deck_name = deck["name"]
            parts = deck_name.split("::")
            if len(parts) < 2:
                return  # root deck has no parent to add a sibling under
            parent_name = "::".join(parts[:-1])
            name, ok = QInputDialog.getText(
                self, "New Sibling Subdeck", f"Subdeck name under {parent_name}:"
            )
            if ok and name.strip():
                full_name = f"{parent_name}::{name.strip()}"
                col.decks.id(full_name)
                if self._tree_root is not None:
                    from .decks import find_deck_node
                    new_root = find_deck_node(self._tree_root.deck_id)
                    if new_root:
                        self.set_deck_tree(new_root, self._tree_name)
                self.subdeck_created.emit()
            return

        if action == "delete_deck":
            deck_id = int(payload)
            deck = col.decks.get(DeckId(deck_id))
            if not deck:
                return
            deck_name = deck["name"]
            own_cids = col.decks.cids(DeckId(deck_id), children=False)
            children = col.decks.children(DeckId(deck_id))
            if own_cids or children:
                QMessageBox.warning(
                    self, "Cannot Delete",
                    f'The deck "{deck_name}" is not empty.\n\n'
                    "Move or delete all cards and child subdecks first.",
                )
            else:
                confirm = QMessageBox.question(
                    self, "Delete Deck",
                    f'Are you sure you want to delete "{deck_name}"?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if confirm == QMessageBox.StandardButton.Yes:
                    col.decks.remove([DeckId(deck_id)])
                    if self._tree_root is not None:
                        from .decks import find_deck_node
                        new_root = find_deck_node(self._tree_root.deck_id)
                        if new_root:
                            self.set_deck_tree(new_root, self._tree_name)
                    self.subdeck_created.emit()
            return

        if action in ("suspend", "unsuspend", "review_now"):
            cid = CardId(int(payload))
            if action == "suspend":
                col.sched.suspend_cards([cid])
            elif action == "unsuspend":
                col.sched.unsuspend_cards([cid])
            elif action == "review_now":
                col.sched.set_due_date([cid], "0")
            self._targeted_refresh_card(col, int(payload))
            self.card_action_handled.emit()
            return
        elif action in ("suspend_group", "unsuspend_group", "review_now_group"):
            cids = [CardId(int(c)) for c in payload.split(",") if c]
            if action == "suspend_group":
                col.sched.suspend_cards(cids)
            elif action == "unsuspend_group":
                col.sched.unsuspend_cards(cids)
            elif action == "review_now_group":
                col.sched.set_due_date(cids, "0")
            # Find the lead cid for this IO group
            lead_cid = int(payload.split(",")[0]) if "," in payload else int(payload)
            self._targeted_refresh_card(col, lead_cid, is_group=True)
            self.card_action_handled.emit()
            return
        elif action == "delete_card":
            cids = [CardId(int(c)) for c in payload.split(",") if c]
            count = len(cids)
            label = f"{count} cards" if count > 1 else "this card"
            # Determine deck before deletion for header count update
            try:
                deck_id = col.get_card(cids[0]).did
            except Exception:
                deck_id = None
            confirm = QMessageBox.question(
                self, "Delete Card",
                f"Are you sure you want to delete {label}?\n\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            col.remove_cards_and_orphaned_notes(cids)
            # Remove card(s) from DOM
            lead_cid = int(payload.split(",")[0]) if "," in payload else int(payload)
            self._web.eval(f"removeCard({lead_cid})")
            # Update section header counts and title
            if deck_id is not None:
                self._refresh_header_counts(col, deck_id)
            self._update_title(col)
            self.card_action_handled.emit()
            return

        if self._tree_root is not None:
            self.set_deck_tree(self._tree_root, self._tree_name)
        elif self._current_card_ids is not None:
            self.set_cards(self._current_card_ids)

    # ── Render ──

    _current_card_ids: Sequence[int] | None = None
    _tree_root = None
    _tree_name: str = ""

    def set_filters(
        self,
        search_text: str = "",
        active_chips: set[str] | None = None,
        tag_filter: str = "",
        sort_key: str = "deck",
        sort_reverse: bool = False,
        criteria: dict | None = None,
    ) -> None:
        """Update filter/sort state and re-render if a deck tree is loaded."""
        self._search_text = search_text
        self._active_chips = active_chips or set()
        self._tag_filter = tag_filter
        self._sort_key = sort_key
        self._sort_reverse = sort_reverse
        self._criteria = criteria or {}
        if self._tree_root is not None:
            self._render_deck_tree(emit_tags=False)

    def _apply_filters(self, col, card_ids: Sequence[int]) -> list[int]:
        """Apply search, state, tag filters and sorting to a list of card IDs."""
        cids = list(card_ids)
        if not cids:
            return cids

        # Content search
        if self._search_text:
            cids = search_cards_by_content(col, cids, self._search_text)

        # Tag filter
        if self._tag_filter:
            cids = filter_cards_by_tag(col, cids, self._tag_filter)

        # State filter
        if self._active_chips:
            meta = get_cards_metadata(col, cids)
            today = col.sched.today
            allowed = filter_cards_by_states(meta, today, self._active_chips)
            cids = [c for c in cids if c in allowed]

        # Advanced criteria filter
        if self._criteria:
            meta = get_cards_metadata(col, cids)
            allowed = filter_cards_by_criteria(meta, self._criteria)
            cids = [c for c in cids if c in allowed]

        # Sorting
        if self._sort_key != "deck" or self._sort_reverse:
            meta = get_cards_metadata(col, cids)
            today = col.sched.today
            cids = sort_cards(cids, meta, today, self._sort_key, self._sort_reverse)

        return cids

    def set_deck_tree(self, root_node, root_name: str) -> None:
        """Render all subdecks as collapsible sections in one webview."""
        self._tree_root = root_node
        self._tree_name = root_name
        self._current_card_ids = None
        self._io_group_map.clear()
        self._note_group_map.clear()
        self._render_deck_tree(emit_tags=True)

    def _render_deck_tree(self, emit_tags: bool = True) -> None:
        """Internal render — builds and pushes HTML for the current deck tree."""
        root_node = self._tree_root
        root_name = self._tree_name
        self._io_group_map.clear()
        self._note_group_map.clear()

        col = mw.col
        if col is None:
            self._web.stdHtml("<p>No collection loaded.</p>")
            return

        all_cids = col.decks.cids(DeckId(root_node.deck_id), children=True)

        # Emit available tags and flags for the toolbar (only on deck change)
        if emit_tags:
            tags = get_tags_for_cards(col, all_cids)
            self.tags_updated.emit(tags)
            flags = get_flags_for_cards(col, all_cids)
            self.flags_updated.emit(flags)

        # Pre-compute filtered total for title
        has_filters = bool(self._search_text or self._active_chips or self._tag_filter or self._criteria)
        if has_filters:
            filtered_total = self._apply_filters(col, all_cids)
            self._set_title_from_cids(col, root_name, filtered_total, all_cids)
        else:
            self._set_title_from_cids(col, root_name, all_cids, all_cids)

        # Apply filters to root's own cards
        root_own = col.decks.cids(DeckId(root_node.deck_id), children=False)
        root_own_filtered = self._apply_filters(col, root_own)
        root_cards = self._build_items_html(col, root_own_filtered) if root_own_filtered else ""

        child_sections = ""
        for child in root_node.children:
            child_path = f"{root_name}::{child.name}"
            child_sections += self._build_section(col, child, full_path=child_path, depth=0)

        root_plus_menu = (
            f'<div class="plus-menu" id="plus-menu-{root_node.deck_id}">'
            f'<button onclick="plusAction(event,\'add_card\',{root_node.deck_id})">Add card\u2026</button>'
            f'<button onclick="plusAction(event,\'add_subdeck\',{root_node.deck_id})">Add child subdeck\u2026</button>'
            f'</div>'
        )
        root_header = (
            f'<div class="root-header">'
            f'<button class="header-plus-btn" onclick="togglePlusMenu(event,{root_node.deck_id})" title="Add\u2026">+</button>'
            f'{root_plus_menu}'
            f'</div>'
        )

        body = root_header
        if root_cards:
            body += f'<div class="deck-cards">{root_cards}</div>'
        body += child_sections

        self._render_page(body)

    def _state_counts_html(self, col, all_cids: Sequence[int]) -> str:
        """Build compact coloured state-count spans for a deck header."""
        meta = get_cards_metadata(col, all_cids) if all_cids else {}
        today = col.sched.today if all_cids else 0

        if self._display_mode == "notes" and all_cids:
            sc = note_summary_counts(meta, all_cids, today)
            n = sc["new"]
            l = sc["learn"]
            u = sc["upcoming"]
            d = sc["due"]
            notes = sc["notes"]
            cards = sc["cards"]
            counts = (
                f'<span class="sc sc-new">{n}N</span> '
                f'<span class="sc sc-learn">{l}L</span> '
                f'<span class="sc sc-upcoming">{u}U</span> '
                f'<span class="sc sc-due">{d}D</span>'
            )
            return (
                f'<span class="card-count">{notes} Notes / {cards} '
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

    def _build_section(self, col, node, full_path: str, depth: int) -> str:
        """Recursively build HTML for a collapsible deck section."""
        deck_id = node.deck_id
        own_cids = col.decks.cids(DeckId(deck_id), children=False)
        all_cids = col.decks.cids(DeckId(deck_id), children=True)

        own_filtered = self._apply_filters(col, own_cids)
        cards_html = self._build_items_html(col, own_filtered) if own_filtered else ""

        children_html = ""
        for child in node.children:
            child_path = f"{full_path}::{child.name}"
            children_html += self._build_section(col, child, full_path=child_path, depth=depth + 1)

        has_filters = bool(self._search_text or self._active_chips or self._tag_filter or self._criteria)
        if not own_filtered and not children_html and not node.children and has_filters:
            return ""

        collapsed = deck_id in self._collapsed_decks
        arrow_cls = "collapse-arrow collapsed" if collapsed else "collapse-arrow"
        body_style = ' style="height:0px"' if collapsed else ''
        name_html = format_deck_path(full_path)
        d = min(depth, 4)
        sc_html = self._state_counts_html(col, all_cids)

        plus_menu = (
            f'<div class="plus-menu" id="plus-menu-{deck_id}">'
            f'<button onclick="plusAction(event,\'add_card\',{deck_id})">Add card\u2026</button>'
            f'<button onclick="plusAction(event,\'add_subdeck\',{deck_id})">Add child subdeck\u2026</button>'
            f'<button onclick="plusAction(event,\'add_sibling_subdeck\',{deck_id})">Add sibling subdeck\u2026</button>'
            f'<hr class="plus-menu-sep">'
            f'<button class="plus-menu-danger" onclick="plusAction(event,\'delete_deck\',{deck_id})">Delete deck\u2026</button>'
            f'</div>'
        )

        return (
            f'<div class="deck-section" data-deck-id="{deck_id}">'
            f'<div class="deck-header depth-{d}" onclick="toggleSection({deck_id})">'
            f'<span class="{arrow_cls}" id="arrow-{deck_id}">\u25bc</span>'
            f'<span class="deck-name">{name_html}</span>'
            f'<span class="deck-info">'
            f'<button class="header-plus-btn" onclick="togglePlusMenu(event,{deck_id})" title="Add\u2026">+</button>'
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

    def _build_cards_html(self, col, card_ids: Sequence[int]) -> str:
        """Build lightweight placeholder HTML for lazy-loaded cards."""
        if not card_ids:
            return ""

        meta = get_cards_metadata(col, card_ids)
        today = col.sched.today

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
                lead_cid = group_cids[0]
                self._io_group_map[lead_cid] = group_cids

                # Determine group state from metadata
                group_state = ""
                group_countdown = ""
                all_susp = True
                for gcid in group_cids:
                    gm = meta.get(gcid, {})
                    if gm.get("queue") != QUEUE_TYPE_SUSPENDED:
                        all_susp = False
                        st = card_state_from_meta(gm, today)
                        if STATE_PRIORITY.get(st, 0) > STATE_PRIORITY.get(group_state, 0):
                            group_state = st
                            group_countdown = card_countdown_from_meta(gm, today)

                cls_parts = ["card-frame", "card-placeholder"]
                if all_susp:
                    cls_parts.append("suspended")
                if group_state:
                    cls_parts.append(f"state-{group_state}")
                cls = " ".join(cls_parts)
                badge = build_state_badge(group_state, group_countdown)
                n_cards = len(group_cids)
                parts.append(
                    f'<div class="{cls}" data-lazy="{lead_cid}">'
                    f'  {badge}'
                    f'  <div class="placeholder-inner">'
                    f'    <span class="io-badge">{n_cards} occlusion cards</span>'
                    f'  </div>'
                    f'</div>'
                )
            else:
                cid = eid
                m = meta.get(cid, {})
                state = card_state_from_meta(m, today)
                countdown = card_countdown_from_meta(m, today)
                suspended = m.get("queue") == QUEUE_TYPE_SUSPENDED

                cls_parts = ["card-frame", "card-placeholder"]
                if suspended:
                    cls_parts.append("suspended")
                if state:
                    cls_parts.append(f"state-{state}")
                cls = " ".join(cls_parts)
                badge = build_state_badge(state, countdown)
                parts.append(
                    f'<div class="{cls}" data-lazy="{cid}">'
                    f'  {badge}'
                    f'  <div class="placeholder-inner"></div>'
                    f'</div>'
                )

        return "\n".join(parts)

    def _build_notes_html(self, col, card_ids: Sequence[int]) -> str:
        """Build placeholder HTML for note-grouped display (notes mode)."""
        if not card_ids:
            return ""

        groups = group_cards_by_note(col, card_ids)
        meta = get_cards_metadata(col, card_ids)
        today = col.sched.today
        parts: list[str] = []

        for ng in groups:
            if ng.is_io:
                # IO notes render the same as cards mode
                lead_cid = ng.cids[0]
                self._io_group_map[lead_cid] = ng.cids

                summary = note_state_summary(meta, ng.cids, today)
                cls_parts = ["card-frame", "card-placeholder"]
                if summary["all_suspended"]:
                    cls_parts.append("suspended")
                if summary["dominant_state"]:
                    cls_parts.append(f"state-{summary['dominant_state']}")
                cls = " ".join(cls_parts)
                badge = build_state_badge(summary["dominant_state"], summary["dominant_countdown"])
                n_cards = len(ng.cids)
                parts.append(
                    f'<div class="{cls}" data-lazy="{lead_cid}">'
                    f'  {badge}'
                    f'  <div class="placeholder-inner">'
                    f'    <span class="io-badge">{n_cards} occlusion cards</span>'
                    f'  </div>'
                    f'</div>'
                )
            elif len(ng.cids) == 1:
                # Single-card notes render identically to cards mode
                cid = ng.cids[0]
                m = meta.get(cid, {})
                state = card_state_from_meta(m, today)
                countdown = card_countdown_from_meta(m, today)
                suspended = m.get("queue") == QUEUE_TYPE_SUSPENDED

                cls_parts = ["card-frame", "card-placeholder"]
                if suspended:
                    cls_parts.append("suspended")
                if state:
                    cls_parts.append(f"state-{state}")
                cls = " ".join(cls_parts)
                badge = build_state_badge(state, countdown)
                parts.append(
                    f'<div class="{cls}" data-lazy="{cid}">'
                    f'  {badge}'
                    f'  <div class="placeholder-inner"></div>'
                    f'</div>'
                )
            else:
                # Multi-card note: render note group with field table (lazy)
                lead_cid = ng.cids[0]
                self._note_group_map[lead_cid] = ng.cids

                summary = note_state_summary(meta, ng.cids, today)
                cls_parts = ["card-frame", "card-placeholder", "note-group-placeholder"]
                if summary["all_suspended"]:
                    cls_parts.append("suspended")
                if summary["dominant_state"]:
                    cls_parts.append(f"state-{summary['dominant_state']}")
                cls = " ".join(cls_parts)
                badge = build_state_badge(summary["dominant_state"], summary["dominant_countdown"])
                count_html = build_note_card_count(summary)
                parts.append(
                    f'<div class="{cls}" data-lazy="{lead_cid}" data-nid="{ng.nid}">'
                    f'  {badge}'
                    f'  <div class="placeholder-inner">'
                    f'    {count_html}'
                    f'  </div>'
                    f'</div>'
                )

        return "\n".join(parts)

    def _build_items_html(self, col, card_ids: Sequence[int]) -> str:
        """Dispatch to cards or notes HTML builder based on display mode."""
        if self._display_mode == "notes":
            return self._build_notes_html(col, card_ids)
        return self._build_cards_html(col, card_ids)

    def _build_io_group(self, col, group_cids: list[int]) -> str:
        """Build full HTML for a group of IO cards (called during lazy load)."""
        first_card = col.get_card(CardId(group_cids[0]))
        answer_html = first_card.answer()
        img_src, masks = extract_io_data(answer_html)

        if not img_src or not masks:
            all_masks: list[dict] = []
            found_src = img_src
            for gcid in group_cids:
                gc = col.get_card(CardId(gcid))
                src, ms = extract_io_data(gc.answer())
                if src and not found_src:
                    found_src = src
                all_masks.extend(ms)
            if found_src and all_masks:
                img_src, masks = found_src, all_masks

        if img_src and masks:
            suspended_ords: set[str] = set()
            all_susp = True
            group_state = ""
            group_countdown = ""
            today = col.sched.today
            for gcid in group_cids:
                gc = col.get_card(CardId(gcid))
                is_susp = gc.queue == QUEUE_TYPE_SUSPENDED
                if not is_susp:
                    all_susp = False
                    m = {"queue": gc.queue, "type": gc.type, "due": gc.due}
                    st = card_state_from_meta(m, today)
                    if STATE_PRIORITY.get(st, 0) > STATE_PRIORITY.get(group_state, 0):
                        group_state = st
                        group_countdown = card_countdown_from_meta(m, today)
                q_html = gc.question()
                mo = ACTIVE_ORDINAL_RE.search(q_html)
                if mo and is_susp:
                    suspended_ords.add(mo.group(1))
            try:
                io_tags = first_card.note().tags
            except Exception:
                io_tags = []
            return build_io_card_html(
                img_src, masks, group_cids, suspended_ords, all_susp,
                state=group_state, countdown=group_countdown,
                tags=io_tags,
            )
        else:
            return render_normal_card(col, group_cids[0])

    def scroll_to_deck(self, deck_id: int) -> None:
        """Scroll the webview to a specific deck section."""
        self._web.eval(f"scrollToSection({deck_id})")

    def _render_page(self, body_html: str) -> None:
        """Render the full page with CSS, body content, overlay, and JS."""
        color_map = get_state_colors()
        color_vars = ":root { " + " ".join(
            f"{k}: {v};" for k, v in color_map.items()
        ) + " }"
        self._web.stdHtml(
            f"<style>{color_vars}\n{TRAY_CSS}</style>"
            f"{body_html}"
            f'<div id="overlay" onclick="closeOverlay()">'
            f'  <div id="overlay-card" onclick="event.stopPropagation()">'
            f'    <button id="overlay-close" onclick="closeOverlay()">&times;</button>'
            f'    <div id="overlay-card-content"></div>'
            f'  </div>'
            f'</div>'
            f"<script>{TRAY_JS}</script>",
            context=self,
        )
        # Re-apply edit mode after full page rebuild
        if self._edit_mode:
            self._web.eval("setEditMode(true)")

    def _on_lazy_load(self, col, payload: str) -> None:
        """Handle lazy_load bridge command: render requested cards and inject."""
        cids_str = [c.strip() for c in payload.split(",") if c.strip()]
        results: dict[str, str] = {}
        for cid_s in cids_str:
            cid = int(cid_s)
            if cid in self._io_group_map:
                html = self._build_io_group(col, self._io_group_map[cid])
            elif cid in self._note_group_map:
                html = self._build_note_group(col, cid)
            else:
                html = render_normal_card(col, cid)
            results[cid_s] = html
        data_json = json.dumps(results)
        self._web.eval(f"fillCards({data_json})")

    def _build_note_group(self, col, lead_cid: int) -> str:
        """Build full HTML for a multi-card note group (called during lazy load)."""
        group_cids = self._note_group_map.get(lead_cid, [lead_cid])
        meta = get_cards_metadata(col, group_cids)
        today = col.sched.today

        # Determine nid from lead card
        m = meta.get(lead_cid)
        if m is None:
            return render_normal_card(col, lead_cid)
        nid = m["nid"]

        summary = note_state_summary(meta, group_cids, today)
        fields = get_note_fields(col, nid)
        fields_table = build_note_fields_table(fields)
        card_names = get_card_template_names(col, nid)

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
            card_names=card_names,
            summary=summary,
            tags=tags,
        )

    def _on_lazy_load_note_cards(self, col, payload: str) -> None:
        """Handle lazy_load_note_cards: render individual cards within a note group."""
        cids_str = [c.strip() for c in payload.split(",") if c.strip()]
        parts: list[str] = []
        for cid_s in cids_str:
            cid = int(cid_s)
            html = render_normal_card(col, cid)
            parts.append(html)
        combined = "\n".join(parts)
        # Determine nid from first card
        if cids_str:
            first_cid = int(cids_str[0])
            try:
                card = col.get_card(CardId(first_cid))
                nid = card.nid
            except Exception:
                nid = 0
            escaped = json.dumps(combined)
            self._web.eval(f"fillNoteCards({nid}, {escaped})")

    def _on_preview_card(self, col, payload: str) -> None:
        """Handle preview_card: render a single card's answer for overlay preview."""
        cid = int(payload.strip())
        card = col.get_card(CardId(cid))
        answer_html = card.answer()
        escaped = json.dumps(answer_html)
        self._web.eval(f"fillCardPreview({escaped})")

    def set_cards(self, card_ids: Sequence[int]) -> None:
        """Render a flat list of cards (legacy single-deck view)."""
        self._current_card_ids = card_ids
        self._tree_root = None
        self._io_group_map.clear()
        self._note_group_map.clear()
        col = mw.col
        if col is None:
            self._web.stdHtml("<p>No collection loaded.</p>")
            return
        if not card_ids:
            self._web.stdHtml("<p>No cards in this deck.</p>")
            return

        body = f'<div class="deck-cards">{self._build_items_html(col, card_ids)}</div>'
        self._render_page(body)

    def cleanup(self) -> None:
        self._web.cleanup()

    # ── Targeted refresh ──

    def _targeted_refresh_card(self, col, cid: int, is_group: bool = False) -> None:
        """Re-render a single card (or IO group) in-place without full page reload.

        If active filters are set, falls back to refreshing the whole deck section
        (still no full-page reload). Otherwise, replaces just the card element.
        """
        has_filters = bool(self._search_text or self._active_chips or self._tag_filter or self._criteria)

        # Determine which deck section this card belongs to
        try:
            card = col.get_card(CardId(cid))
            deck_id = card.did
        except Exception:
            # Card might not exist (edge case); fall back to full refresh
            if self._tree_root is not None:
                self.set_deck_tree(self._tree_root, self._tree_name)
            return

        if has_filters:
            # Filters are active — the card might now be excluded, so rebuild the section
            if self._tree_root is not None:
                if deck_id == self._tree_root.deck_id:
                    # Card is in root deck directly; must do full re-render
                    self._render_deck_tree(emit_tags=False)
                else:
                    self.refresh_section(deck_id)
                self._update_title(col)
            return

        # No active filters: surgically replace just this card in the DOM
        if is_group and cid in self._io_group_map:
            html = self._build_io_group(col, self._io_group_map[cid])
        else:
            html = render_normal_card(col, cid)

        escaped = json.dumps(html)
        self._web.eval(f"replaceCard({cid}, {escaped})")

        # Update section header counts
        self._refresh_header_counts(col, deck_id)
        self._update_title(col)

    def _refresh_header_counts(self, col, deck_id: int) -> None:
        """Update the header count badges for a section and its ancestors."""
        if self._tree_root is None:
            return
        # Update the section itself (if it's a child section)
        ctx = self._find_node_context(deck_id)
        if ctx is not None:
            all_cids = col.decks.cids(DeckId(deck_id), children=True)
            sc = self._state_counts_html(col, all_cids)
            self._web.eval(f"updateHeaderCounts({deck_id}, {json.dumps(sc)})")
        # Update ancestor header counts
        for anc_id in self._ancestor_deck_ids(deck_id):
            anc_cids = col.decks.cids(DeckId(anc_id), children=True)
            sc = self._state_counts_html(col, anc_cids)
            self._web.eval(f"updateHeaderCounts({anc_id}, {json.dumps(sc)})")

    def _update_title(self, col) -> None:
        """Recalculate and update the header title with current card counts."""
        if self._tree_root is None:
            return
        all_cids = col.decks.cids(DeckId(self._tree_root.deck_id), children=True)
        has_filters = bool(self._search_text or self._active_chips or self._tag_filter or self._criteria)
        if has_filters:
            filtered_total = self._apply_filters(col, all_cids)
            self._set_title_from_cids(col, self._tree_name, filtered_total, all_cids)
        else:
            self._set_title_from_cids(col, self._tree_name, all_cids, all_cids)

    def _set_title_from_cids(self, col, root_name: str,
                              visible_cids: Sequence[int],
                              total_cids: Sequence[int]) -> None:
        """Set the header title, using note/card counts in notes mode."""
        has_filters = len(visible_cids) != len(total_cids)

        if self._display_mode == "notes":
            meta = get_cards_metadata(col, total_cids) if total_cids else {}
            today = col.sched.today if total_cids else 0
            total_sc = note_summary_counts(meta, total_cids, today)
            if has_filters:
                vis_meta = get_cards_metadata(col, visible_cids) if visible_cids else {}
                vis_sc = note_summary_counts(vis_meta, visible_cids, today)
                self.title = (
                    f"{root_name}  ({vis_sc['notes']} / {total_sc['notes']} notes, "
                    f"{vis_sc['cards']} / {total_sc['cards']} cards)"
                )
            else:
                self.title = (
                    f"{root_name}  ({total_sc['notes']} notes / {total_sc['cards']} cards)"
                )
        else:
            if has_filters:
                self.title = f"{root_name}  ({len(visible_cids)} / {len(total_cids)} cards)"
            else:
                self.title = f"{root_name}  ({len(total_cids)} cards)"

    def _refresh_all_header_counts(self, col) -> None:
        """Update all section header counts without touching card content."""
        if self._tree_root is None:
            return
        self._update_section_counts(col, self._tree_root)
        self._update_title(col)

    def _update_section_counts(self, col, node) -> None:
        """Recursively update header counts for all sections."""
        for child in node.children:
            deck_id = child.deck_id
            all_cids = col.decks.cids(DeckId(deck_id), children=True)
            sc = self._state_counts_html(col, all_cids)
            self._web.eval(f"updateHeaderCounts({deck_id}, {json.dumps(sc)})")
            self._update_section_counts(col, child)

    def _find_node_context(
        self, deck_id: int, node=None, parent_path: str = "", depth: int = 0
    ) -> tuple | None:
        """Find (node, full_path, depth) for *deck_id* within the current tree."""
        if node is None:
            node = self._tree_root
            if node is None:
                return None
            parent_path = self._tree_name
            # Check root's direct children (root itself is depth -1, children start at 0)
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
        """Return deck IDs from the target up to (but not including) the tree root."""
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

    def refresh_section(self, deck_id: int) -> None:
        """Rebuild one deck section in-place and update ancestor header counts."""
        col = mw.col
        if col is None or self._tree_root is None:
            return

        ctx = self._find_node_context(deck_id)
        if ctx is not None:
            node, full_path, depth = ctx
            html = self._build_section(col, node, full_path, depth)
            if html:
                escaped = json.dumps(html)
                self._web.eval(f"replaceSection({deck_id}, {escaped})")
            # Update header counts for the rebuilt section itself
            all_cids = col.decks.cids(DeckId(deck_id), children=True)
            sc = self._state_counts_html(col, all_cids)
            self._web.eval(f"updateHeaderCounts({deck_id}, {json.dumps(sc)})")

        # Update ancestor header counts (they include children totals)
        for anc_id in self._ancestor_deck_ids(deck_id):
            anc_cids = col.decks.cids(DeckId(anc_id), children=True)
            sc = self._state_counts_html(col, anc_cids)
            self._web.eval(f"updateHeaderCounts({anc_id}, {json.dumps(sc)})")
