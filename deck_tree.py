from __future__ import annotations

from aqt.qt import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QInputDialog,
    Qt,
    pyqtSignal,
)


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
        layout.addWidget(self._tree)

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool) -> None:
        self._edit_mode = value

    def populate(self, root_node, parent_path: str = "") -> None:
        """Build the tree from an Anki DeckTreeNode (the selected top-level deck)."""
        self._tree.clear()
        root_item = self._tree.invisibleRootItem()
        if root_item is not None:
            self._add_children(root_node, parent_path, root_item)
        self._tree.expandAll()

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

        from aqt import mw
        from anki.decks import DeckId

        menu = QMenu(self)
        add_subdeck_action = menu.addAction("Add subdeck\u2026")
        add_card_action = menu.addAction("Add card\u2026")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))

        col = mw.col
        if col is None:
            return

        if chosen == add_subdeck_action:
            name, ok = QInputDialog.getText(
                self, "New Subdeck", f"Subdeck name under {full_name}:"
            )
            if ok and name.strip():
                col.decks.id(f"{full_name}::{name.strip()}")
                self.subdeck_created.emit()
        elif chosen == add_card_action:
            col.decks.set_current(DeckId(int(deck_id)))
            from aqt.addcards import AddCards
            add = AddCards(mw)
            add.show()

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
        """Show only tree items whose name (or descendants) match *text*."""
        root = self._tree.invisibleRootItem()
        if root is None:
            return
        needle = text.strip().lower()
        if not needle:
            self._set_all_visible(root, True)
            self._tree.expandAll()
            return
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
