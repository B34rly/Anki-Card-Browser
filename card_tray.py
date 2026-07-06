from __future__ import annotations

import json
import time
from collections.abc import Sequence

from anki.cards import CardId
from anki.consts import (
    QUEUE_TYPE_SUSPENDED, QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED,
)
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
    group_flag,
)
from .card_data import (
    get_cards_metadata,
    get_card_decks,
    get_deck_cards,
    get_note_cards,
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
    frame_classes,
    build_note_fields_table,
    build_note_group_html,
    build_note_card_count,
)
from .deck_ops import (
    open_add_cards,
    prompt_new_subdeck,
    prompt_rename_deck,
    confirm_delete_deck,
)
from .note_grouping import (
    group_cards_by_note,
    note_state_summary,
    note_summary_counts,
)

# Collection-config key for the persisted set of collapsed deck ids. Stored on the
# collection so it survives restarts and scopes per profile (deck ids are unique
# within a collection); reused independently of Anki's own deck["collapsed"].
_COLLAPSE_CFG_KEY = "cardBrowser_collapsed_decks"


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

    def __init__(self, title: str = "", parent=None, display_mode: str = "cards"):
        super().__init__(parent)

        self._display_mode: str = display_mode
        self._edit_mode: bool = False
        self._collapsed_decks: set[int] = set()
        self._io_group_map: dict[int, list[int]] = {}  # lead_cid → [group cids]
        self._note_group_map: dict[int, list[int]] = {}  # lead_cid → [note group cids]

        # Scroll anchor (top-visible section deck id, px scrolled into it) restored
        # after a full re-render; None resets it on a deck switch. See restoreScroll.
        self._scroll_anchor: tuple[int, int] | None = None
        # card id → deck id for everything currently rendered; diffed against the
        # live collection on external ops to spot-refresh only the sections that
        # gained/lost/moved cards.
        self._known_cards: dict[int, int] = {}
        # Epoch-seconds watermark: cards/notes with mod >= this changed since the
        # last render / external-op sweep (see consume_modified).
        self._mod_watermark: int = int(time.time())

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

        if action == "scroll":
            # payload is "<deck_id>:<depth>"; deck_id 0 means a raw pixel offset.
            try:
                did_s, depth_s = payload.split(":")
                self._scroll_anchor = (int(did_s), int(depth_s))
            except ValueError:
                pass
            return

        if action == "visible_section":
            self.visible_section_changed.emit(int(payload))
            return

        # Collapse/expand state — no re-render needed; persisted so it survives
        # reopen. The payload carries the explicit end state (not a toggle), so
        # a replay or a race with a re-render can't invert what the user sees.
        if action == "set_collapsed":
            did_s, flag = payload.split(":")
            if flag == "1":
                self._collapsed_decks.add(int(did_s))
            else:
                self._collapsed_decks.discard(int(did_s))
            self._save_collapsed(col)
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
            # Reset every card in the subtree to due today, then start review.
            # This overwrites scheduling for the whole deck, so confirm first.
            deck_id = int(payload)
            deck = col.decks.get(DeckId(deck_id))
            cids = col.decks.cids(DeckId(deck_id), children=True)
            if not deck or not cids:
                return
            confirm = QMessageBox.question(
                self, "Force Review All",
                f'This resets all {len(cids)} card(s) in "{deck["name"]}" to be '
                f"due today, overwriting their current schedule.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            col.sched.set_due_date([CardId(c) for c in cids], "0")
            col.decks.set_current(DeckId(deck_id))
            mw.moveToState("review")
            return

        if action == "add_card":
            open_add_cards(int(payload))
            return

        if action == "edit_card":
            from aqt import dialogs
            browser = dialogs.open("Browser", mw)
            if browser:
                browser.search_for(f"cid:{payload}")
            return

        if action == "add_subdeck":
            deck = col.decks.get(DeckId(int(payload)))
            if deck and prompt_new_subdeck(self, deck["name"]):
                self._notify_tree_changed()
            return

        if action == "add_sibling_subdeck":
            deck = col.decks.get(DeckId(int(payload)))
            if not deck:
                return
            parts = deck["name"].split("::")
            if len(parts) < 2:
                return  # root deck has no parent to add a sibling under
            parent_name = "::".join(parts[:-1])
            if prompt_new_subdeck(self, parent_name, title="New Sibling Subdeck"):
                self._notify_tree_changed()
            return

        if action == "rename_deck":
            if prompt_rename_deck(self, int(payload)):
                self._notify_tree_changed()
            return

        if action == "delete_deck":
            if confirm_delete_deck(self, int(payload)):
                self._notify_tree_changed()
            return

        # Per-card / per-group actions all operate on a comma-separated cid list.
        if action in (
            "suspend", "unsuspend", "review_now", "bury", "unbury", "forget",
            "set_due", "reposition", "add_tag", "remove_tag", "change_deck",
        ) or action.startswith("flag_"):
            cids = [CardId(int(c)) for c in payload.split(",") if c]
            if cids:
                self._handle_card_action(col, action, cids)
            return

        if action == "delete_card":
            cids = [CardId(int(c)) for c in payload.split(",") if c]
            count = len(cids)
            label = f"{count} cards" if count > 1 else "this card"
            lead_cid = int(cids[0])
            # Capture deck + note-group identity BEFORE deletion (needed after).
            try:
                deck_id = col.get_card(cids[0]).did
            except Exception:
                deck_id = None
            # A group-level delete passes the whole cid list; deleting one inner
            # card passes a single cid that may coincide with a group lead — only
            # treat it as a group delete in the former case.
            is_note_group = lead_cid in self._note_group_map and len(cids) > 1
            confirm = QMessageBox.question(
                self, "Delete Card",
                f"Are you sure you want to delete {label}?\n\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            col.remove_cards_and_orphaned_notes(cids)
            for c in cids:
                self._known_cards.pop(int(c), None)
            # Remove the card / note group from the DOM (groups key on lead cid)
            if is_note_group:
                self._web.eval(f"removeGroup({lead_cid})")
            else:
                self._web.eval(f"removeCard({lead_cid})")
            # Update section header counts and title
            if deck_id is not None:
                self._refresh_header_counts(col, deck_id)
            self._update_title(col)
            return

    def _notify_tree_changed(self) -> None:
        """Tell the viewer the deck structure changed.

        The viewer refreshes both the sidebar and this tray in response (the
        tray must not also render here — that would double the work; it used
        to, which made every deck add/rename/delete render twice).
        """
        self.subdeck_created.emit()

    # ── Card action handlers (operate on a list of card ids) ──

    def _handle_card_action(self, col, action: str, cids) -> None:
        """Apply a per-card / per-group menu action and refresh the affected unit."""
        lead = int(cids[0])

        if action.startswith("flag_"):
            col.set_user_flag_for_cards(int(action[5:]), cids)
        elif action == "suspend":
            col.sched.suspend_cards(cids)
        elif action == "unsuspend":
            col.sched.unsuspend_cards(cids)
        elif action == "review_now":
            col.sched.set_due_date(cids, "0")
        elif action == "bury":
            col.sched.bury_cards(cids)
        elif action == "unbury":
            col.sched.unbury_cards(cids)
        elif action == "forget":
            col.sched.schedule_cards_as_new(cids)
        elif action == "set_due":
            spec, ok = QInputDialog.getText(
                self, "Set Due Date",
                "Days from today (e.g. 0, 3, 1-7), or a date (YYYY-MM-DD):",
            )
            spec = spec.strip()
            if not ok or not spec:
                return
            try:
                col.sched.set_due_date(cids, spec)
            except Exception as e:
                QMessageBox.warning(self, "Set Due Date Failed", str(e))
                return
        elif action == "reposition":
            pos, ok = QInputDialog.getInt(
                self, "Reposition New Cards", "New position:", 1, 0, 9999999
            )
            if not ok:
                return
            try:
                col.sched.reposition_new_cards(cids, pos, 1, False, False)
            except Exception as e:
                QMessageBox.warning(self, "Reposition Failed", str(e))
                return
        elif action in ("add_tag", "remove_tag"):
            self._handle_tag_action(col, action, cids)
            return
        elif action == "change_deck":
            self._handle_change_deck(col, cids)
            return
        else:
            return

        self._targeted_refresh_card(col, lead)

    def _handle_tag_action(self, col, action: str, cids) -> None:
        """Add or remove a tag on the note(s) behind *cids*, then refresh them."""
        from anki.notes import NoteId

        card_ids = [int(c) for c in cids]
        note_cards = get_note_cards(
            col, list({m["nid"] for m in get_cards_metadata(col, card_ids).values()})
        )
        note_ids = [NoteId(n) for n in note_cards]
        if not note_ids:
            return
        if action == "add_tag":
            tag, ok = QInputDialog.getText(
                self, "Add Tag", "Tag(s) to add (space-separated):"
            )
            tag = tag.strip()
            if not ok or not tag:
                return
            col.tags.bulk_add(note_ids, tag)
        else:
            current = set(get_tags_for_cards(col, card_ids))
            if not current:
                QMessageBox.information(self, "Remove Tag", "There are no tags to remove.")
                return
            tag, ok = QInputDialog.getItem(
                self, "Remove Tag", "Tag to remove:",
                sorted(current, key=str.lower), 0, False,
            )
            if not ok or not tag:
                return
            col.tags.bulk_remove(note_ids, tag)
        # Tags appear on every card of a note, so refresh each affected note.
        for nid, note_cids in note_cards.items():
            self.refresh_note(col, nid, note_cids)

    def _handle_change_deck(self, col, cids) -> None:
        """Prompt for a target deck and move *cids* there, then re-render."""
        choices = [d.name for d in col.decks.all_names_and_ids(include_filtered=False)]
        choices.sort(key=str.lower)
        if not choices:
            return
        try:
            cur_name = col.decks.name(col.get_card(cids[0]).did)
        except Exception:
            cur_name = ""
        start = choices.index(cur_name) if cur_name in choices else 0
        name, ok = QInputDialog.getItem(
            self, "Change Deck", "Move to deck:", choices, start, False
        )
        if not ok or not name:
            return
        did = col.decks.id(name)
        if did is None:
            return
        col.set_deck(cids, did)
        # The card(s) moved to another section, so re-render (scroll preserved).
        if self._tree_root is not None:
            self._render_deck_tree(emit_tags=False)

    # ── Persisted collapse state ──

    def _load_collapsed(self, col) -> set[int]:
        """Read the saved set of collapsed deck ids from the collection config."""
        try:
            saved = col.get_config(_COLLAPSE_CFG_KEY, [])
            if isinstance(saved, list):
                return {int(d) for d in saved}
        except Exception:
            pass
        return set()

    def _save_collapsed(self, col) -> None:
        """Persist the current collapsed-deck set to the collection config."""
        try:
            col.set_config(_COLLAPSE_CFG_KEY, sorted(self._collapsed_decks))
        except Exception:
            pass

    # ── Render ──

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

    @property
    def _has_filters(self) -> bool:
        """True when any content/tag/state/criteria filter is active."""
        return bool(
            self._search_text or self._active_chips
            or self._tag_filter or self._criteria
        )

    def _compute_allowed(self, col, card_ids: Sequence[int], meta, today) -> set[int] | None:
        """Card ids from *card_ids* passing the active filters.

        Returns None when no filters are active (= everything allowed), so a
        full render computes this once for the whole subtree and each section
        just intersects its own ids — no per-section SQL. *meta* must cover
        *card_ids*. Sorting is separate (_order_cids), applied per section.
        """
        if not self._has_filters:
            return None
        cids = list(card_ids)
        if self._search_text:
            cids = search_cards_by_content(col, cids, self._search_text)
        if self._tag_filter:
            cids = filter_cards_by_tag(col, cids, self._tag_filter)
        allowed = set(cids)
        if self._active_chips:
            allowed &= filter_cards_by_states(meta, today, self._active_chips)
        if self._criteria:
            allowed &= filter_cards_by_criteria(meta, self._criteria)
        return allowed

    def _order_cids(self, cids: list[int], meta, today) -> list[int]:
        """Apply the active sort to *cids* (deck order + ascending is a no-op)."""
        if self._sort_key != "deck" or self._sort_reverse:
            return sort_cards(cids, meta, today, self._sort_key, self._sort_reverse)
        return cids

    def set_deck_tree(self, root_node, root_name: str) -> None:
        """Render all subdecks as collapsible sections in one webview."""
        # Reset scroll only when switching to a different top-level deck; a
        # refresh of the same deck keeps the user's position (pain point #2).
        new_root = self._tree_root is None or self._tree_root.deck_id != root_node.deck_id
        self._tree_root = root_node
        self._tree_name = root_name
        self._io_group_map.clear()
        self._note_group_map.clear()
        if new_root:
            self._scroll_anchor = None
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

        # Restore the persisted collapse state (config is the source of truth,
        # kept current by set_collapsed saves) before building sections from it.
        self._collapsed_decks = self._load_collapsed(col)

        all_cids = col.decks.cids(DeckId(root_node.deck_id), children=True)

        # Fetch metadata for the whole subtree ONCE and thread it through the
        # section/count builders. Every section's cids are a subset of all_cids,
        # so meta.get(cid) serves them all without re-querying per section.
        meta = get_cards_metadata(col, all_cids)
        today = col.sched.today

        # Snapshot what this render shows, so external changes can be diffed
        # (membership by deck) and pinpointed (mod-time watermark).
        self._known_cards = {cid: m["did"] for cid, m in meta.items()}
        self._mod_watermark = int(time.time())

        # Emit available tags and flags for the toolbar (only on deck change)
        if emit_tags:
            tags = get_tags_for_cards(col, all_cids)
            self.tags_updated.emit(tags)
            flags = get_flags_for_cards(col, all_cids)
            self.flags_updated.emit(flags)

        # One filter pass over the whole subtree; sections intersect against it.
        allowed = self._compute_allowed(col, all_cids, meta, today)
        visible = all_cids if allowed is None else [c for c in all_cids if c in allowed]
        self._set_title_from_cids(col, root_name, visible, all_cids, meta, today)

        root_own = col.decks.cids(DeckId(root_node.deck_id), children=False)
        root_items = self._order_cids(
            [c for c in root_own if allowed is None or c in allowed], meta, today
        )
        root_cards = self._build_items_html(col, root_items, meta, today) if root_items else ""

        child_sections = ""
        for child in root_node.children:
            child_path = f"{root_name}::{child.name}"
            child_sections += self._build_section(
                col, child, full_path=child_path, depth=0,
                meta=meta, today=today, allowed=allowed,
            )

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

        self._render_page(body, restore_scroll=True)

    def _state_counts_html(self, col, all_cids: Sequence[int], meta=None, today=None) -> str:
        """Build compact coloured state-count spans for a deck header.

        *meta*/*today* may be supplied (e.g. a whole-tree fetch reused across
        sections); a superset of *all_cids* is fine. They are fetched here only
        when omitted (targeted refreshes), keeping post-mutation data fresh.
        """
        if meta is None:
            meta = get_cards_metadata(col, all_cids) if all_cids else {}
        if today is None:
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

    def _build_section(self, col, node, full_path: str, depth: int, meta, today, allowed=None) -> str:
        """Recursively build HTML for a collapsible deck section.

        *meta* must cover the section's subtree; *allowed* is the pre-computed
        filter set from _compute_allowed (None = no filters active).
        """
        deck_id = node.deck_id
        own_cids = col.decks.cids(DeckId(deck_id), children=False)
        all_cids = col.decks.cids(DeckId(deck_id), children=True)

        own_items = self._order_cids(
            [c for c in own_cids if allowed is None or c in allowed], meta, today
        )
        cards_html = self._build_items_html(col, own_items, meta, today) if own_items else ""

        children_html = ""
        for child in node.children:
            child_path = f"{full_path}::{child.name}"
            children_html += self._build_section(
                col, child, full_path=child_path, depth=depth + 1,
                meta=meta, today=today, allowed=allowed,
            )

        # Under filters: hide sections with no hits anywhere, and force the
        # rest open — a match inside a collapsed (possibly persisted-collapsed)
        # section would otherwise sit invisible in a height-0 body and never
        # lazy-load, looking like the search found nothing. The persisted
        # collapse state is untouched and applies again once filters clear.
        if allowed is not None:
            if not own_items and not children_html:
                return ""
            collapsed = False
        else:
            collapsed = deck_id in self._collapsed_decks
        arrow_cls = "collapse-arrow collapsed" if collapsed else "collapse-arrow"
        body_style = ' style="height:0px"' if collapsed else ''
        name_html = format_deck_path(full_path)
        d = min(depth, 4)
        sc_html = self._state_counts_html(col, all_cids, meta, today)

        plus_menu = (
            f'<div class="plus-menu" id="plus-menu-{deck_id}">'
            f'<button onclick="plusAction(event,\'add_card\',{deck_id})">Add card\u2026</button>'
            f'<button onclick="plusAction(event,\'add_subdeck\',{deck_id})">Add child subdeck\u2026</button>'
            f'<button onclick="plusAction(event,\'add_sibling_subdeck\',{deck_id})">Add sibling subdeck\u2026</button>'
            f'<hr class="plus-menu-sep">'
            f'<button onclick="plusAction(event,\'rename_deck\',{deck_id})">Rename deck\u2026</button>'
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

    def _build_cards_html(self, col, card_ids: Sequence[int], meta=None, today=None) -> str:
        """Build lightweight placeholder HTML for lazy-loaded cards."""
        if not card_ids:
            return ""

        if meta is None:
            meta = get_cards_metadata(col, card_ids)
        if today is None:
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
                self._io_group_map[group_cids[0]] = group_cids
                io_badge = f'<span class="io-badge">{len(group_cids)} occlusion cards</span>'
                parts.append(self._group_placeholder(meta, today, group_cids, io_badge))
            else:
                parts.append(self._card_placeholder(meta, today, eid))

        return "\n".join(parts)

    def _build_notes_html(self, col, card_ids: Sequence[int], meta=None, today=None) -> str:
        """Build placeholder HTML for note-grouped display (notes mode)."""
        if not card_ids:
            return ""

        if meta is None:
            meta = get_cards_metadata(col, card_ids)
        if today is None:
            today = col.sched.today
        groups = group_cards_by_note(col, card_ids, meta)
        parts: list[str] = []

        for ng in groups:
            if ng.is_io:
                # IO notes render the same as cards mode
                self._io_group_map[ng.cids[0]] = ng.cids
                io_badge = f'<span class="io-badge">{len(ng.cids)} occlusion cards</span>'
                parts.append(self._group_placeholder(meta, today, ng.cids, io_badge))
            elif len(ng.cids) == 1:
                # Single-card notes render identically to cards mode
                parts.append(self._card_placeholder(meta, today, ng.cids[0]))
            else:
                # Multi-card note: render note group with field table (lazy)
                self._note_group_map[ng.cids[0]] = ng.cids
                summary = note_state_summary(meta, ng.cids, today)
                parts.append(self._group_placeholder(
                    meta, today, ng.cids,
                    inner=build_note_card_count(summary),
                    extra_attrs=f' data-nid="{ng.nid}"',
                ))

        return "\n".join(parts)

    def _build_items_html(self, col, card_ids: Sequence[int], meta=None, today=None) -> str:
        """Dispatch to cards or notes HTML builder based on display mode."""
        if self._display_mode == "notes":
            return self._build_notes_html(col, card_ids, meta, today)
        return self._build_cards_html(col, card_ids, meta, today)

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
            cards = [col.get_card(CardId(gcid)) for gcid in group_cids]
            # Which mask ordinals belong to suspended cards (drawn grey)
            suspended_ords: set[str] = set()
            for gc in cards:
                if gc.queue == QUEUE_TYPE_SUSPENDED:
                    mo = ACTIVE_ORDINAL_RE.search(gc.question())
                    if mo:
                        suspended_ords.add(mo.group(1))
            meta = {
                gc.id: {"queue": gc.queue, "type": gc.type, "due": gc.due}
                for gc in cards
            }
            summary = note_state_summary(meta, [gc.id for gc in cards], col.sched.today)
            try:
                io_tags = first_card.note().tags
            except Exception:
                io_tags = []
            return build_io_card_html(
                img_src, masks, group_cids, suspended_ords,
                summary["all_suspended"],
                state=summary["dominant_state"],
                countdown=summary["dominant_countdown"],
                tags=io_tags,
                all_buried=summary["all_buried"],
                flag=group_flag(gc.user_flag() for gc in cards),
            )
        else:
            return render_normal_card(col, group_cids[0])

    def scroll_to_deck(self, deck_id: int) -> None:
        """Scroll the webview to a specific deck section."""
        self._web.eval(f"scrollToSection({deck_id})")

    def _render_page(self, body_html: str, restore_scroll: bool = False) -> None:
        """Render the full page with CSS, body content, overlay, and JS.

        The current edit/view mode is baked into the page (no post-render eval,
        so edit controls never flash in the wrong mode). Webview evals are
        queued until the DOM is ready, so the scroll restore lands after load.
        """
        color_map = get_state_colors()
        color_vars = ":root { " + " ".join(
            f"{k}: {v};" for k, v in color_map.items()
        ) + " }"
        mode_js = "true" if self._edit_mode else "false"
        self._web.stdHtml(
            f"<style>{color_vars}\n{TRAY_CSS}</style>"
            f"{body_html}"
            f'<div id="overlay" onclick="closeOverlay()">'
            f'  <div id="overlay-card" onclick="event.stopPropagation()">'
            f'    <button id="overlay-close" onclick="closeOverlay()">&times;</button>'
            f'    <div id="overlay-card-content"></div>'
            f'  </div>'
            f'</div>'
            f"<script>var _initialEditMode = {mode_js};</script>"
            f"<script>{TRAY_JS}</script>",
            context=self,
        )
        # Restore the prior scroll position (filter change / same-deck refresh).
        if restore_scroll and self._scroll_anchor is not None:
            did, depth = self._scroll_anchor
            self._web.eval(f"restoreScroll({did}, {depth})")

    def _on_lazy_load(self, col, payload: str) -> None:
        """Handle lazy_load bridge command: render requested cards and inject."""
        cids_str = [c.strip() for c in payload.split(",") if c.strip()]
        results: dict[str, str] = {}
        for cid_s in cids_str:
            cid = int(cid_s)
            try:
                if cid in self._io_group_map:
                    html = self._build_io_group(col, self._io_group_map[cid])
                elif cid in self._note_group_map:
                    html = self._build_note_group(col, cid)
                else:
                    html = render_normal_card(col, cid)
            except Exception:
                # The card vanished between render and lazy load (external
                # delete, stale group map); skip it rather than break the batch.
                continue
            results[cid_s] = html
        if results:
            self._web.eval(f"fillCards({json.dumps(results)})")

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
            flag=group_flag(m.get("flags", 0) for m in meta.values()),
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
        # The note-group body is keyed by its lead (first) cid.
        if cids_str:
            lead_cid = int(cids_str[0])
            escaped = json.dumps(combined)
            self._web.eval(f"fillNoteCards({lead_cid}, {escaped})")

    def _on_preview_card(self, col, payload: str) -> None:
        """Handle preview_card: render a single card's answer for overlay preview."""
        cid = int(payload.strip())
        card = col.get_card(CardId(cid))
        answer_html = card.answer()
        escaped = json.dumps(answer_html)
        self._web.eval(f"fillCardPreview({escaped})")

    def cleanup(self) -> None:
        self._web.cleanup()

    # ── Targeted refresh ──

    def refresh_tree(self) -> None:
        """Full re-render of the current tree (scroll position is preserved)."""
        if self._tree_root is not None:
            self._render_deck_tree(emit_tags=False)

    @property
    def known_cids(self):
        """Card ids currently rendered in the tree (view of the snapshot keys)."""
        return self._known_cards.keys()

    def _tree_deck_ids(self, col) -> list[int]:
        """Deck ids of the rendered tree (root plus all descendants)."""
        if self._tree_root is None:
            return []
        try:
            return list(col.decks.deck_and_child_ids(DeckId(self._tree_root.deck_id)))
        except Exception:
            return [self._tree_root.deck_id]

    def consume_modified(self, col) -> tuple[list[tuple[int, int]], list[int], bool]:
        """In-tree cards/notes modified since the last sweep, then advance.

        Returns ``(card_rows, nids, changed_anywhere)``: ``card_rows`` is
        ``[(cid, nid), …]`` and ``nids`` note ids whose ``mod`` is at or past
        the watermark, restricted to the rendered tree via the indexed
        ``cards.did`` column (no full-table scan on the common path). This
        pinpoints *which* items an external op touched (OpChanges carries no
        ids), regardless of where the edit came from. ``changed_anywhere`` is
        False only when the *whole collection* has no matching row — the undo
        signature (undo restores old mod times), which callers answer with a
        full re-render. Second-resolution overlap can re-report an item;
        refreshes are idempotent so that is harmless.
        """
        wm = self._mod_watermark
        self._mod_watermark = int(time.time())
        dids = self._tree_deck_ids(col)
        if not dids or len(dids) > 900:
            # No tree, or too many decks for one IN clause (SQLite parameter
            # limit) — fall back to whole-table sweeps; callers filter by nid.
            cards = col.db.all("SELECT id, nid FROM cards WHERE mod >= ?", wm)
            nids = col.db.list("SELECT id FROM notes WHERE mod >= ?", wm)
            return cards, nids, True
        ph = ",".join("?" * len(dids))
        cards = col.db.all(
            f"SELECT id, nid FROM cards WHERE did IN ({ph}) AND mod >= ?",
            *dids, wm,
        )
        nids = col.db.list(
            f"SELECT id FROM notes WHERE mod >= ? AND id IN "
            f"(SELECT nid FROM cards WHERE did IN ({ph}))",
            wm, *dids,
        )
        if cards or nids:
            return cards, nids, True
        changed = col.db.scalar(
            "SELECT 1 FROM notes WHERE mod >= ? LIMIT 1", wm
        ) or col.db.scalar(
            "SELECT 1 FROM cards WHERE mod >= ? LIMIT 1", wm
        )
        return [], [], bool(changed)

    def _replace_unit(self, col, cid: int) -> None:
        """Surgically replace one rendered unit — no count/title updates.

        Mirrors the lazy-load dispatch so IO and note groups rebuild as groups
        rather than collapsing into a single card.
        """
        try:
            if cid in self._io_group_map:
                html = self._build_io_group(col, self._io_group_map[cid])
                self._web.eval(f"replaceCard({cid}, {json.dumps(html)})")
            elif cid in self._note_group_map:
                html = self._build_note_group(col, cid)
                self._web.eval(f"replaceGroup({cid}, {json.dumps(html)})")
            else:
                html = render_normal_card(col, cid)
                self._web.eval(f"replaceCard({cid}, {json.dumps(html)})")
        except Exception:
            # The unit vanished mid-refresh; the caller's counts pass keeps the
            # page coherent and the next full render reconciles the rest.
            pass

    def _targeted_refresh_card(self, col, cid: int) -> None:
        """Re-render a single card / group in-place without a full page reload.

        If active filters are set, rebuilds the whole deck section instead (still
        no full-page reload, so scroll is preserved).
        """
        # Determine which deck section this card belongs to
        try:
            deck_id = col.get_card(CardId(cid)).did
        except Exception:
            # Card might not exist (edge case); fall back to a full re-render
            self.refresh_tree()
            return

        if self._has_filters:
            # Filters are active — the card might now be excluded, so rebuild the section
            if self._tree_root is not None:
                if deck_id == self._tree_root.deck_id:
                    # Card is in the root deck directly; must do a full re-render
                    self._render_deck_tree(emit_tags=False)
                else:
                    self.refresh_section(deck_id)
                self._update_title(col)
            return

        self._replace_unit(col, cid)
        self._refresh_header_counts(col, deck_id)
        self._update_title(col)

    def refresh_note(self, col, nid: int, cids: Sequence[int]) -> None:
        """Re-render the on-screen card(s) for a single edited note.

        Resolves the rendered unit(s) for the note — normal cards, an IO group,
        or a note group — replaces each in place, then updates counts and the
        title once (not once per card). With active filters, rebuilds the
        affected section(s) instead. Scroll is preserved throughout.
        """
        if self._tree_root is None or not cids:
            return

        affected_decks = set(get_card_decks(col, list(cids)).values())

        if self._has_filters:
            # A filtered card may now be included/excluded; rebuild each affected
            # deck section once (refresh_section / full render preserve scroll).
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
        for group_map in (self._io_group_map, self._note_group_map):
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

    def sync_external_changes(self, col) -> str:
        """Spot-apply external membership changes by diffing the tree's cards.

        Compares the subtree's current cid→deck map against the snapshot from the
        last render: sections that gained cards (adds, moves in) are rebuilt in
        place, sections that lost moved cards are rebuilt too, and removed cards
        are dropped from the DOM. Targeted updates preserve scroll. Falls back to
        one full re-render (scroll also preserved) when that is cheaper or safer:
        bulk changes, active filters (membership must be re-derived), a change
        touching a rendered group (stale group maps), or an add landing in the
        root deck's own card area (no standalone section to rebuild).

        Returns what happened, so the caller can plan follow-up refreshes:
        ``"full"`` (full re-render done, everything is fresh), ``"spot"``
        (membership changes applied in place), or ``"none"`` (no membership
        change).
        """
        if self._tree_root is None:
            return "none"
        current = get_deck_cards(col, self._tree_deck_ids(col))
        previous = self._known_cards
        self._known_cards = current

        added = current.keys() - previous.keys()
        removed = previous.keys() - current.keys()
        moved = {c for c in current.keys() & previous.keys() if current[c] != previous[c]}

        if not (added or removed or moved):
            return "none"

        def full() -> str:
            self._render_deck_tree(emit_tags=True)
            return "full"

        # A large external change (bulk import, sync, mass delete) is cheaper and
        # cleaner as one full re-render than hundreds of targeted DOM edits.
        if len(added) + len(removed) + len(moved) > 40:
            return full()

        # Under active filters a changed card may belong to a section that was
        # filtered out of the DOM entirely; only a full re-render (which
        # re-applies the filters) can get membership right.
        if self._has_filters:
            return full()

        # A removed/moved card that was rendered inside an IO or note group needs
        # its group rebuilt, but the group maps are now stale — re-render.
        if removed or moved:
            grouped: set[int] = set()
            for members in self._io_group_map.values():
                grouped.update(members)
            for members in self._note_group_map.values():
                grouped.update(members)
            if any(c in grouped for c in removed) or any(c in grouped for c in moved):
                return full()

        # Sections to rebuild: where added cards landed, and both ends of a move.
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

    def _refresh_header_counts(self, col, deck_id: int, include_self: bool = True) -> None:
        """Update the header count badges for a section and/or its ancestors.

        Fetches metadata once — the topmost ancestor's subtree is a superset of
        every other target's — instead of re-querying per header.
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
            sc = self._state_counts_html(col, cids, meta, today)
            self._web.eval(f"updateHeaderCounts({d}, {json.dumps(sc)})")

    def _update_title(self, col) -> None:
        """Recalculate and update the header title with current card counts."""
        if self._tree_root is None:
            return
        all_cids = col.decks.cids(DeckId(self._tree_root.deck_id), children=True)
        # Metadata is needed for notes-mode counts and for state/criteria filters.
        needs_meta = bool(
            self._display_mode == "notes" or self._active_chips or self._criteria
        )
        meta = get_cards_metadata(col, all_cids) if (needs_meta and all_cids) else None
        today = col.sched.today if all_cids else 0
        allowed = self._compute_allowed(col, all_cids, meta or {}, today)
        visible = all_cids if allowed is None else [c for c in all_cids if c in allowed]
        self._set_title_from_cids(col, self._tree_name, visible, all_cids, meta, today)

    def _set_title_from_cids(self, col, root_name: str,
                              visible_cids: Sequence[int],
                              total_cids: Sequence[int],
                              meta=None, today=None) -> None:
        """Set the header title, using note/card counts in notes mode."""
        has_filters = len(visible_cids) != len(total_cids)

        if self._display_mode == "notes":
            if meta is None:
                meta = get_cards_metadata(col, total_cids) if total_cids else {}
            if today is None:
                today = col.sched.today if total_cids else 0
            total_sc = note_summary_counts(meta, total_cids, today)
            if has_filters:
                vis_sc = note_summary_counts(meta, visible_cids, today)
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
            sc = self._state_counts_html(col, all_cids, meta, today)
            self._web.eval(f"updateHeaderCounts({deck_id}, {json.dumps(sc)})")
            self._update_section_counts(col, child, meta, today)

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
            all_cids = col.decks.cids(DeckId(deck_id), children=True)
            meta = get_cards_metadata(col, all_cids)
            today = col.sched.today
            allowed = self._compute_allowed(col, all_cids, meta, today)
            html = self._build_section(col, node, full_path, depth, meta, today, allowed)
            if not html:
                # The section is now filtered out entirely; a targeted replace
                # can't remove it cleanly, so re-render the tree.
                self._render_deck_tree(emit_tags=False)
                return
            self._web.eval(f"replaceSection({deck_id}, {json.dumps(html)})")

        # Update ancestor header counts (the rebuilt section's own header is
        # already fresh — _build_section embeds current counts).
        self._refresh_header_counts(col, deck_id, include_self=False)
