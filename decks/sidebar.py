from __future__ import annotations

from aqt import mw
from aqt.qt import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    Qt,
    pyqtSignal,
)

from .ops import (
    open_add_cards,
    prompt_new_subdeck,
    prompt_rename_deck,
    confirm_delete_deck,
)

# Collection-config key for the sidebar's collapsed deck ids. Deliberately
# separate from the tray's cardBrowser_collapsed_decks — the two views are
# collapsed independently (a deck folded in the sidebar may stay open in the
# grid and vice versa).
_SIDEBAR_COLLAPSE_KEY = "cardBrowser_sidebar_collapsed"


class DeckTree(QWidget):
    """A collapsible tree view of subdecks. Emits `deck_selected` when clicked."""

    # Emits (deck_id, full_deck_name) when the user clicks a deck
    # Use 'object' for deck_id — Anki IDs are 64-bit and overflow C++ int
    deck_selected = pyqtSignal(object, str)

    # Emits when a subdeck is created via the context menu
    subdeck_created = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._edit_mode: bool = False
        self._collapsed: set[int] = set()
        # True while a name filter is active — its match-expansion is a view
        # aid, not a state change (mirrors the tray's force-expand on search).
        # Code-driven expansion (populate / filter clear) blocks the tree's
        # signals instead, like highlight_deck does.
        self._filtered: bool = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: palette(base);
                font-size: 13px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px 2px;
            }
            QTreeWidget::item:hover {
                background: palette(midlight);
            }
            QTreeWidget::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
        """)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemExpanded.connect(
            lambda item: self._on_expand_changed(item, collapsed=False)
        )
        self._tree.itemCollapsed.connect(
            lambda item: self._on_expand_changed(item, collapsed=True)
        )
        layout.addWidget(self._tree)

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool) -> None:
        self._edit_mode = value

    def populate(self, root_node, parent_path: str = "") -> None:
        """Build the tree from an Anki DeckTreeNode (the selected top-level deck).

        Expansion state is restored from the persisted set — decks default to
        expanded; only ones the user collapsed stay collapsed across
        repopulates and restarts.
        """
        self._collapsed = self._load_collapsed()
        self._filtered = False  # a rebuilt tree starts unfiltered
        self._tree.blockSignals(True)
        try:
            self._tree.clear()
            root_item = self._tree.invisibleRootItem()
            if root_item is not None:
                self._add_children(root_node, parent_path, root_item)
                self._apply_saved_expansion(root_item)
        finally:
            self._tree.blockSignals(False)

    # ── Persisted collapse state ──

    def _load_collapsed(self) -> set[int]:
        """Read the saved sidebar-collapsed deck ids from the collection config."""
        col = getattr(mw, "col", None)
        if col is None:
            return set(self._collapsed)
        try:
            saved = col.get_config(_SIDEBAR_COLLAPSE_KEY, [])
            if isinstance(saved, list):
                return {int(d) for d in saved}
        except Exception:
            pass
        return set()

    def _save_collapsed(self) -> None:
        """Persist the current sidebar-collapsed deck ids."""
        col = getattr(mw, "col", None)
        if col is None:
            return
        try:
            col.set_config(_SIDEBAR_COLLAPSE_KEY, sorted(self._collapsed))
        except Exception:
            pass

    def _apply_saved_expansion(self, item: QTreeWidgetItem) -> None:
        """Expand every item except those in the persisted collapsed set."""
        for i in range(item.childCount()):
            child = item.child(i)
            if child is None:
                continue
            deck_id = child.data(0, Qt.ItemDataRole.UserRole)
            child.setExpanded(deck_id is None or int(deck_id) not in self._collapsed)
            self._apply_saved_expansion(child)

    def _on_expand_changed(self, item: QTreeWidgetItem, collapsed: bool) -> None:
        """A tree item was expanded/collapsed — persist genuine user changes.

        Programmatic changes never get here: populate/filter-clear and
        highlight_deck block the tree's signals while they mutate it. An
        active name filter sets _filtered instead — its match-expansion (and
        any clicks on that ephemeral view) is temporary by design.
        """
        if self._filtered:
            return
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        if deck_id is None:
            return
        if collapsed:
            self._collapsed.add(int(deck_id))
        else:
            self._collapsed.discard(int(deck_id))
        self._save_collapsed()

    def _add_children(self, node, parent_path: str, parent_item: QTreeWidgetItem) -> None:
        for child in node.children:
            full_name = f"{parent_path}::{child.name}" if parent_path else child.name
            item = QTreeWidgetItem(parent_item, [child.name])
            item.setData(0, Qt.ItemDataRole.UserRole, child.deck_id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, full_name)
            self._add_children(child, full_name, item)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        full_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if deck_id is not None:
            self.deck_selected.emit(int(deck_id), full_name)

    def _on_context_menu(self, pos) -> None:
        if not self._edit_mode:
            return
        item = self._tree.itemAt(pos)
        if item is None:
            return
        deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        full_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if deck_id is None:
            return

        menu = QMenu(self)
        add_card_action = menu.addAction("Add card\u2026")
        add_child_action = menu.addAction("Add child subdeck\u2026")
        # Sibling only makes sense for non-root decks (name contains "::")
        add_sibling_action = None
        if "::" in full_name:
            add_sibling_action = menu.addAction("Add sibling subdeck\u2026")
        menu.addSeparator()
        rename_action = menu.addAction("Rename deck\u2026")
        delete_action = menu.addAction("Delete deck\u2026")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))

        if chosen == add_card_action:
            open_add_cards(int(deck_id))
        elif chosen == add_child_action:
            if prompt_new_subdeck(self, full_name):
                self.subdeck_created.emit()
        elif add_sibling_action and chosen == add_sibling_action:
            parent_name = "::".join(full_name.split("::")[:-1])
            if prompt_new_subdeck(self, parent_name, title="New Sibling Subdeck"):
                self.subdeck_created.emit()
        elif chosen == rename_action:
            if prompt_rename_deck(self, int(deck_id)):
                self.subdeck_created.emit()
        elif chosen == delete_action:
            if confirm_delete_deck(self, int(deck_id)):
                self.subdeck_created.emit()

    def highlight_deck(self, deck_id: int) -> None:
        """Select the tree item for *deck_id* without emitting signals."""
        item = self._find_item(deck_id)
        if item is None:
            return
        self._tree.blockSignals(True)
        self._tree.setCurrentItem(item)
        self._tree.scrollToItem(item)
        self._tree.blockSignals(False)

    def _find_item(self, deck_id: int, root: QTreeWidgetItem | None = None) -> QTreeWidgetItem | None:
        if root is None:
            root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == deck_id:
                return child
            found = self._find_item(deck_id, child)
            if found is not None:
                return found
        return None

    def filter(self, text: str) -> None:
        """Show only tree items whose name (or descendants) match *text*.

        Matching branches are expanded so hits are visible, but only for the
        duration of the filter — clearing it restores the saved expansion
        state, not expand-all.
        """
        root = self._tree.invisibleRootItem()
        if root is None:
            return
        needle = text.strip().lower()
        if not needle:
            self._filtered = False
            self._set_all_visible(root, True)
            self._tree.blockSignals(True)
            try:
                self._apply_saved_expansion(root)
            finally:
                self._tree.blockSignals(False)
            return
        self._filtered = True
        self._filter_item(root, needle)

    def _filter_item(self, item: QTreeWidgetItem, needle: str) -> bool:
        """Recursively filter. Returns True if this item or any child matches."""
        match = False
        for i in range(item.childCount()):
            child = item.child(i)
            if child is None:
                continue
            child_match = self._filter_item(child, needle)
            name = (child.text(0) or "").lower()
            full = (child.data(0, Qt.ItemDataRole.UserRole + 1) or "").lower()
            if needle in name or needle in full:
                child_match = True
            child.setHidden(not child_match)
            if child_match:
                child.setExpanded(True)
                match = True
        return match

    @staticmethod
    def _set_all_visible(item: QTreeWidgetItem, visible: bool) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            if child is None:
                continue
            child.setHidden(not visible)
            DeckTree._set_all_visible(child, visible)
