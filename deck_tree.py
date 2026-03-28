from __future__ import annotations

from aqt.qt import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    Qt,
    pyqtSignal,
)


class DeckTree(QWidget):
    """A collapsible tree view of subdecks. Emits `deck_selected` when clicked."""

    # Emits (deck_id, full_deck_name) when the user clicks a deck
    # Use 'object' for deck_id — Anki IDs are 64-bit and overflow C++ int
    deck_selected = pyqtSignal(object, str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

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
