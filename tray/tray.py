"""CardTray — the widget that shows the deck tree as a card grid.

The class is deliberately thin: it owns the widget/webview, the state shared
by its two implementation halves (render.RenderMixin builds and pushes page
content; refresh.RefreshMixin applies targeted updates), and the bridge
dispatch that routes JS pycmd messages to them. HTML construction lives in
builder.py / details.py; collection mutations in actions.py; external-change
snapshots in sync.py.

State contract (owned here, used by both mixins):
    _web              TrayWebView
    _builder          PageBuilder (display mode + per-render group maps)
    _filters          FilterState (from the viewer toolbar)
    _tracker          ChangeTracker (membership snapshot + mod watermark)
    _collapsed_decks  persisted collapsed deck ids
    _tree_root/_tree_name   the rendered DeckTreeNode + display name
    _scroll_anchor    (deck id, px depth) restored after full renders
    _eager            last full render's search-mode decision
    _edit_mode        view/edit toggle
    _open_detail      ("card"|"note", unit id) while the overlay shows one
"""
from __future__ import annotations

import json

from anki.cards import CardId
from anki.decks import DeckId
from aqt import mw
from aqt.qt import (
    QLabel,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)
from aqt.webview import AnkiWebViewKind

from ..core.card_data import get_card_decks
from ..decks.ops import (
    confirm_delete_deck,
    open_add_cards,
    prompt_new_subdeck,
    prompt_rename_deck,
)
from . import actions, details
from .builder import PageBuilder
from .filters import FilterState
from .render import RenderMixin
from .refresh import RefreshMixin
from .sync import ChangeTracker
from .webview import TrayWebView

# Collection-config key for the persisted set of collapsed deck ids. Stored on
# the collection so it survives restarts and scopes per profile; independent
# of Anki's own deck["collapsed"].
_COLLAPSE_CFG_KEY = "cardBrowser_collapsed_decks"


class CardTray(QWidget, RenderMixin, RefreshMixin):
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

        self._builder = PageBuilder(display_mode)
        self._filters = FilterState()
        self._tracker = ChangeTracker()
        self._edit_mode: bool = False
        self._collapsed_decks: set[int] = set()
        self._open_detail: tuple[str, int] | None = None
        self._eager: bool = False
        self._tree_root = None
        self._tree_name: str = ""
        # Scroll anchor (top-visible section deck id, px scrolled into it)
        # restored after a full re-render; None resets it on a deck switch.
        self._scroll_anchor: tuple[int, int] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel(title)
        self._header.setStyleSheet(
            "font-size: 14px; font-weight: 600; padding: 8px 12px;"
        )
        layout.addWidget(self._header, 0)

        self._web = TrayWebView(parent=self, kind=AnkiWebViewKind.DEFAULT)
        self._web.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._web.set_bridge_command(self._on_bridge_cmd, self)
        layout.addWidget(self._web, 1)

    # ── Simple properties ──

    @property
    def title(self) -> str:
        return self._header.text()

    @title.setter
    def title(self, value: str):
        self._header.setText(value)

    @property
    def display_mode(self) -> str:
        return self._builder.display_mode

    @display_mode.setter
    def display_mode(self, value: str) -> None:
        self._builder.display_mode = value

    @property
    def has_filters(self) -> bool:
        """True when any content/tag/state/criteria filter is active."""
        return self._filters.active

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool) -> None:
        self._edit_mode = value
        self._web.eval(f"setEditMode({'true' if value else 'false'})")

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
        self._filters = FilterState(
            search_text=search_text,
            active_chips=active_chips or set(),
            tag_filter=tag_filter,
            sort_key=sort_key,
            sort_reverse=sort_reverse,
            criteria=criteria or {},
        )
        if self._tree_root is not None:
            self._render_deck_tree(emit_tags=False)

    def cleanup(self) -> None:
        self._web.cleanup()

    def _notify_tree_changed(self) -> None:
        """Tell the viewer the deck structure changed.

        The viewer refreshes both the sidebar and this tray in response (the
        tray must not also render here — that would double the work).
        """
        self.subdeck_created.emit()

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

    # ── Bridge dispatch (pycmd messages from the page JS) ──

    def _on_bridge_cmd(self, cmd: str) -> None:
        col = mw.col
        if col is None or ":" not in cmd:
            return
        action, payload = cmd.split(":", 1)

        handler = self._BRIDGE.get(action)
        if handler is not None:
            handler(self, col, payload)
            return
        # Per-card / per-group actions all operate on a comma-separated cid
        # list; flags arrive as flag_0 … flag_7.
        if action in actions.CARD_ACTIONS or action.startswith("flag_"):
            cids = [CardId(int(c)) for c in payload.split(",") if c]
            if cids:
                self._on_card_action(col, action, cids)

    def _on_scroll(self, col, payload: str) -> None:
        # payload is "<deck_id>:<depth>"; deck_id 0 means a raw pixel offset.
        try:
            did_s, depth_s = payload.split(":")
            self._scroll_anchor = (int(did_s), int(depth_s))
        except ValueError:
            pass

    def _on_visible_section(self, col, payload: str) -> None:
        self.visible_section_changed.emit(int(payload))

    def _on_set_collapsed(self, col, payload: str) -> None:
        # Persisted so it survives reopen. The payload carries the explicit
        # end state (not a toggle), so a replay or a race with a re-render
        # can't invert what the user sees.
        did_s, flag = payload.split(":")
        if flag == "1":
            self._collapsed_decks.add(int(did_s))
        else:
            self._collapsed_decks.discard(int(did_s))
        self._save_collapsed(col)

    # ── Deck-level bridge handlers ──

    def _on_review_due_deck(self, col, payload: str) -> None:
        """Open Anki's reviewer for this deck (due cards only)."""
        deck_id = int(payload)
        if col.decks.get(DeckId(deck_id)):
            col.decks.set_current(DeckId(deck_id))
            mw.moveToState("review")

    def _on_force_review_deck(self, col, payload: str) -> None:
        """Reset every card in the subtree to due today, then start review.

        This overwrites scheduling for the whole deck, so confirm first.
        """
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

    def _on_add_card(self, col, payload: str) -> None:
        open_add_cards(int(payload))

    def _on_edit_card(self, col, payload: str) -> None:
        from aqt import dialogs
        browser = dialogs.open("Browser", mw)
        if browser:
            browser.search_for(f"cid:{payload}")

    def _on_add_subdeck(self, col, payload: str) -> None:
        deck = col.decks.get(DeckId(int(payload)))
        if deck and prompt_new_subdeck(self, deck["name"]):
            self._notify_tree_changed()

    def _on_add_sibling_subdeck(self, col, payload: str) -> None:
        deck = col.decks.get(DeckId(int(payload)))
        if not deck:
            return
        parts = deck["name"].split("::")
        if len(parts) < 2:
            return  # root deck has no parent to add a sibling under
        parent_name = "::".join(parts[:-1])
        if prompt_new_subdeck(self, parent_name, title="New Sibling Subdeck"):
            self._notify_tree_changed()

    def _on_rename_deck(self, col, payload: str) -> None:
        if prompt_rename_deck(self, int(payload)):
            self._notify_tree_changed()

    def _on_delete_deck(self, col, payload: str) -> None:
        if confirm_delete_deck(self, int(payload)):
            self._notify_tree_changed()

    # ── Card-level bridge handlers ──

    def _on_card_action(self, col, action: str, cids) -> None:
        """Apply a per-card / per-group action and refresh the affected unit."""
        lead = int(cids[0])
        if action in ("add_tag", "remove_tag"):
            note_cards = actions.prompt_tag_action(self, col, action, cids)
            if note_cards is None:
                return
            # Tags show on every card of a note; refresh each affected note.
            for nid, note_cids in note_cards.items():
                self.refresh_note(col, nid, note_cids)
        elif action == "change_deck":
            target = actions.prompt_change_deck(self, col, cids)
            if target is None:
                return
            self._move_cids(col, [lead], [int(c) for c in cids], target)
            return  # _move_cids handles the refresh, incl. the open detail
        else:
            if not actions.apply_scheduling_action(self, col, action, cids):
                return
            self._targeted_refresh_card(col, lead)
        self._refresh_open_detail(col)

    def _on_bulk_action(self, col, payload: str) -> None:
        """Multiselect bar: "<action>:<lead cids>". Leads are expanded to
        their group members; the selection is cleared once the action
        actually changed something (a cancelled prompt keeps it)."""
        action, cids_s = payload.split(":", 1)
        leads = [int(c) for c in cids_s.split(",") if c]
        if not leads:
            return
        expanded = [int(c) for c in self._builder.expand_group_cids(leads)]
        card_ids = [CardId(c) for c in expanded]

        if action == "change_deck":
            target = actions.prompt_change_deck(self, col, card_ids)
            if target is None:
                return
            self._web.eval("clearSelection()")
            self._move_cids(col, leads, expanded, target)
            return

        if action == "delete":
            if not actions.confirm_delete(self, len(card_ids)):
                return
            affected = set(get_card_decks(col, expanded).values())
            col.remove_cards_and_orphaned_notes(card_ids)
            self._tracker.forget(expanded)
            self._web.eval("clearSelection()")
            for lead in leads:
                self._web.eval(f"removeCard({lead})")
            for did in affected:
                self._refresh_header_counts(col, did)
            self._update_title(col)
            self._close_detail_if_deleted(set(expanded))
            self._refresh_open_detail(col)
            return

        if action in ("add_tag", "remove_tag"):
            note_cards = actions.prompt_tag_action(self, col, action, card_ids)
            if note_cards is None:
                return
            self._web.eval("clearSelection()")
            if len(note_cards) > 25:
                self.refresh_tree()
            else:
                for nid, note_cids in note_cards.items():
                    self.refresh_note(col, nid, note_cids)
            self._refresh_open_detail(col)
            return

        if not actions.apply_scheduling_action(self, col, action, card_ids):
            return
        self._web.eval("clearSelection()")
        self.refresh_units(col, leads)
        self._refresh_open_detail(col)

    def _on_move_cards(self, col, payload: str) -> None:
        """Drag-and-drop: "<deck_id>:<cids>". Lead cids stand in for their
        whole group (the drag handle is the group frame; inner cards aren't
        draggable)."""
        did_s, cids_s = payload.split(":", 1)
        leads = [int(c) for c in cids_s.split(",") if c]
        if not leads:
            return
        moved = [int(c) for c in self._builder.expand_group_cids(leads)]
        self._move_cids(col, leads, moved, int(did_s))

    def _move_cids(self, col, lead_cids, moved_cids, target_did: int) -> None:
        """Move cards and apply the localized page update."""
        # Source decks must be read BEFORE the move.
        src_dids = set(get_card_decks(col, moved_cids).values())
        if not actions.move_cards(col, moved_cids, target_did):
            return
        self.apply_local_move(col, lead_cids, moved_cids, src_dids, target_did)

    def _on_delete_card(self, col, payload: str) -> None:
        cids = [CardId(int(c)) for c in payload.split(",") if c]
        if not cids:
            return
        lead_cid = int(cids[0])
        # Capture deck + note-group identity BEFORE deletion (needed after).
        try:
            deck_id = col.get_card(cids[0]).did
        except Exception:
            deck_id = None
        # A group-level delete passes the whole cid list; deleting one inner
        # card passes a single cid that may coincide with a group lead — only
        # treat it as a group delete in the former case.
        is_note_group = lead_cid in self._builder.note_groups and len(cids) > 1
        if not actions.confirm_delete(self, len(cids)):
            return
        col.remove_cards_and_orphaned_notes(cids)
        self._tracker.forget(cids)
        # Remove the card / note group from the DOM (groups key on lead cid)
        self._web.eval(
            f"removeGroup({lead_cid})" if is_note_group else f"removeCard({lead_cid})"
        )
        if deck_id is not None:
            self._refresh_header_counts(col, deck_id)
        self._update_title(col)
        self._close_detail_if_deleted({int(c) for c in cids})
        # An open group detail may have contained one of the deleted cards —
        # refresh it so counts/actions don't go stale.
        self._refresh_open_detail(col)

    # ── Detail overlay orchestration ──

    def _on_card_detail(self, col, payload: str) -> None:
        # A note-group lead can arrive here too (e.g. arrow-navigating onto a
        # not-yet-loaded placeholder) — show the right detail kind.
        cid = int(payload)
        if cid in self._builder.note_groups:
            self._push_note_detail(col, cid)
        else:
            self._push_card_detail(col, cid)

    def _on_note_detail(self, col, payload: str) -> None:
        self._push_note_detail(col, int(payload))

    def _on_detail_closed(self, col, payload: str) -> None:
        self._open_detail = None

    def _push_card_detail(self, col, cid: int) -> bool:
        """Build and show the detail overlay for a single card or IO group."""
        try:
            if cid in self._builder.io_groups:
                html = details.build_io_detail(col, self._builder.io_groups[cid])
            else:
                html = details.build_card_detail(col, cid)
        except Exception:
            return False  # the unit vanished; leave the page as it is
        self._open_detail = ("card", cid)
        self._web.eval(f"showCardDetail({json.dumps(html)}, {cid})")
        return True

    def _push_note_detail(self, col, lead_cid: int) -> bool:
        """Build and show the detail overlay for a multi-card note group."""
        try:
            html = details.build_note_detail(
                col, self._builder.note_groups, lead_cid
            )
        except Exception:
            return False
        self._open_detail = ("note", lead_cid)
        self._web.eval(f"showCardDetail({json.dumps(html)}, {lead_cid})")
        return True

    def _refresh_open_detail(self, col) -> None:
        """Re-push the open detail overlay after an action changed its unit.

        No-op when no detail is open — including after a full re-render,
        which resets the overlay and clears the state. If the unit can no
        longer be rendered (deleted underneath the overlay), close it rather
        than leave stale content.
        """
        if self._open_detail is None:
            return
        kind, oid = self._open_detail
        ok = (
            self._push_note_detail(col, oid) if kind == "note"
            else self._push_card_detail(col, oid)
        )
        if not ok:
            self._open_detail = None
            self._web.eval("closeOverlay()")

    def _close_detail_if_deleted(self, deleted_cids: set[int]) -> None:
        """Close the detail overlay when its unit was just deleted."""
        if self._open_detail is not None and self._open_detail[1] in deleted_cids:
            self._open_detail = None
            self._web.eval("closeOverlay()")

    # Dispatch table: bridge action → handler(self, col, payload). Card/flag
    # actions are matched separately in _on_bridge_cmd (open-ended names).
    _BRIDGE = {
        "scroll": _on_scroll,
        "visible_section": _on_visible_section,
        "set_collapsed": _on_set_collapsed,
        "lazy_load": RenderMixin._on_lazy_load,
        "lazy_load_note_cards": RenderMixin._on_lazy_load_note_cards,
        "preview_card": RenderMixin._on_preview_card,
        "card_detail": _on_card_detail,
        "note_detail": _on_note_detail,
        "detail_closed": _on_detail_closed,
        "review_due_deck": _on_review_due_deck,
        "force_review_deck": _on_force_review_deck,
        "add_card": _on_add_card,
        "edit_card": _on_edit_card,
        "add_subdeck": _on_add_subdeck,
        "add_sibling_subdeck": _on_add_sibling_subdeck,
        "rename_deck": _on_rename_deck,
        "delete_deck": _on_delete_deck,
        "move_cards": _on_move_cards,
        "delete_card": _on_delete_card,
        "bulk": _on_bulk_action,
    }
