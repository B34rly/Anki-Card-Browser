from __future__ import annotations

from aqt import mw
from aqt.qt import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QComboBox,
    QSplitter,
    QTimer,
    Qt,
)

from .card_tray import CardTray
from .deck_tree import DeckTree
from .decks import get_top_level_decks, find_deck_node


class CardViewerWindow(QMainWindow):
    """Main viewer window with a deck dropdown, sidebar tree, and card tray."""

    _instance: CardViewerWindow | None = None

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Card Viewer")
        self.resize(1100, 750)

        # ── Left panel: dropdown + deck tree ──
        left_panel = QWidget()
        left_panel.setMinimumWidth(180)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._combo = QComboBox()
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._combo.currentIndexChanged.connect(self._on_deck_changed)
        left_layout.addWidget(self._combo, 0)

        self._deck_tree = DeckTree()
        self._deck_tree.deck_selected.connect(self._on_tree_deck_selected)
        left_layout.addWidget(self._deck_tree, 1)

        # Will be connected after tray is created
        self._tray_signal_connected = False

        # ── Splitter: left panel | card tray ──
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(5)
        self._splitter.setChildrenCollapsible(False)

        self._splitter.addWidget(left_panel)

        self.tray = CardTray()
        self.tray.visible_section_changed.connect(self._on_visible_section)
        self._splitter.addWidget(self.tray)

        self._splitter.setSizes([260, 840])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        self.setCentralWidget(self._splitter)

        # Populate after the event loop starts
        QTimer.singleShot(0, self._populate_combo)

    # ── Dropdown ──

    def _populate_combo(self) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        for deck_id, name in get_top_level_decks():
            self._combo.addItem(name, userData=deck_id)
        self._combo.blockSignals(False)

        if self._combo.count() > 0:
            self._combo.setCurrentIndex(0)
            self._on_deck_changed(0)

    def _on_deck_changed(self, index: int) -> None:
        deck_id = self._combo.itemData(index)
        if deck_id is None:
            return
        node = find_deck_node(int(deck_id))
        if node is None:
            return
        deck_name = self._combo.itemText(index)

        # Rebuild the sidebar tree
        self._deck_tree.populate(node, deck_name)

        # Render all subdecks in a continuous scroll
        self.tray.set_deck_tree(node, deck_name)

    # ── Sidebar tree ──

    def _on_tree_deck_selected(self, deck_id: int, full_name: str) -> None:
        self.tray.scroll_to_deck(deck_id)

    def _on_visible_section(self, deck_id: int) -> None:
        self._deck_tree.highlight_deck(deck_id)

    def closeEvent(self, a0):
        CardViewerWindow._instance = None
        self.tray.cleanup()
        super().closeEvent(a0)


def open_card_viewer():
    """Open the Card Viewer window (singleton)."""
    if CardViewerWindow._instance is None:
        CardViewerWindow._instance = CardViewerWindow(mw)
    CardViewerWindow._instance.show()
    CardViewerWindow._instance.activateWindow()
