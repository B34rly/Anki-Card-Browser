from __future__ import annotations

from anki.decks import DeckId
from aqt import mw
from aqt.qt import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
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

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # ── Top bar: deck selector dropdown ──
        top_bar = QHBoxLayout()
        self._combo = QComboBox()
        self._combo.setMinimumWidth(250)
        self._combo.currentIndexChanged.connect(self._on_deck_changed)
        top_bar.addWidget(self._combo)
        top_bar.addStretch()
        root_layout.addLayout(top_bar)

        # ── Body: sidebar tree | card tray ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        self._deck_tree = DeckTree()
        self._deck_tree.setMinimumWidth(180)
        self._deck_tree.setMaximumWidth(350)
        self._deck_tree.deck_selected.connect(self._on_tree_deck_selected)
        splitter.addWidget(self._deck_tree)

        self.tray = CardTray(parent=splitter)
        splitter.addWidget(self.tray)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

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

        # Show this deck's own cards in the tray
        self._show_deck(int(deck_id), deck_name)

    # ── Sidebar tree ──

    def _on_tree_deck_selected(self, deck_id: int, full_name: str) -> None:
        self._show_deck(deck_id, full_name)

    # ── Loading cards ──

    def _show_deck(self, deck_id: int, deck_name: str) -> None:
        col = mw.col
        if col is None:
            self.tray.title = "No collection loaded"
            return
        card_ids = col.decks.cids(DeckId(deck_id), children=True)
        self.tray.title = f"{deck_name}  ({len(card_ids)} cards)"
        self.tray.set_cards(card_ids)

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
