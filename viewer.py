from __future__ import annotations

from aqt import mw
from aqt.qt import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QComboBox,
    QLineEdit,
    QSplitter,
    QToolButton,
    QLabel,
    QPushButton,
    QIcon,
    QPixmap,
    QTimer,
    Qt,
)

from .card_tray import CardTray
from .card_state import FILTER_CHIP_STATES, SORT_KEYS
from .deck_tree import DeckTree
from .decks import get_top_level_decks, find_deck_node


# ── Qt stylesheet for native widgets (palette-aware for light/dark) ──
_QSS = """\
QComboBox {
    padding: 5px 10px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background: palette(base);
    min-height: 22px;
}
QComboBox:hover {
    border-color: palette(dark);
}
QComboBox::drop-down {
    border: none;
    padding-right: 6px;
}
QComboBox QAbstractItemView {
    background: palette(base);
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
    border: 1px solid palette(mid);
    padding: 2px;
}
QSplitter::handle {
    background: palette(mid);
}
QLineEdit {
    padding: 5px 8px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background: palette(base);
    min-height: 22px;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: palette(highlight);
}
QToolButton {
    padding: 4px;
    border-radius: 4px;
    border: 1px solid transparent;
}
QToolButton:hover {
    background: palette(midlight);
    border-color: palette(mid);
}
QToolButton:checked {
    background: palette(highlight);
    color: palette(highlighted-text);
}
QPushButton#filterChip {
    padding: 3px 10px;
    border: 1px solid palette(mid);
    border-radius: 10px;
    background: palette(base);
    font-size: 12px;
    min-height: 20px;
}
QPushButton#filterChip:hover {
    border-color: palette(dark);
}
QPushButton#filterChip:checked {
    border-color: palette(highlight);
    background: palette(highlight);
    color: palette(highlighted-text);
}
QLabel#filterLabel {
    font-size: 12px;
    color: palette(mid);
    padding: 0 2px;
}
"""

# ── SVG icon templates for the toolbar toggle (use {color} placeholder) ──
_SVG_VIEW = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
    '<circle cx="12" cy="12" r="3"/></svg>'
)
_SVG_EDIT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 20h9"/>'
    '<path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>'
)


class CardViewerWindow(QMainWindow):
    """Main viewer window with a deck dropdown, sidebar tree, and card tray."""

    _instance: CardViewerWindow | None = None

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Card Viewer")
        self.resize(1100, 750)
        self.setStyleSheet(_QSS)

        # ── Left panel: dropdown + deck tree ──
        left_panel = QWidget()
        left_panel.setMinimumWidth(180)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 6, 6, 0)
        left_layout.setSpacing(4)

        self._combo = QComboBox()
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._combo.currentIndexChanged.connect(self._on_deck_changed)
        left_layout.addWidget(self._combo, 0)

        # Search bar + view/edit toggle on one row
        self._edit_mode = False
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(4)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search subdecks\u2026")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self._search, 1)
        self._mode_btn = QToolButton()
        self._mode_btn.setCheckable(True)
        self._mode_btn.setToolTip("Toggle between View and Edit mode")
        self._mode_btn.toggled.connect(self._on_mode_toggled)
        self._update_mode_icon()
        search_row.addWidget(self._mode_btn, 0)
        left_layout.addLayout(search_row)

        self._deck_tree = DeckTree()
        self._deck_tree.deck_selected.connect(self._on_tree_deck_selected)
        self._deck_tree.subdeck_created.connect(self._refresh_current_deck)
        left_layout.addWidget(self._deck_tree, 1)

        # Will be connected after tray is created
        self._tray_signal_connected = False

        # ── Splitter: left panel | card tray ──
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(5)
        self._splitter.setChildrenCollapsible(False)

        self._splitter.addWidget(left_panel)

        # ── Right panel: filter toolbar + card tray ──
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Filter toolbar
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(6)

        # Card content search
        self._card_search = QLineEdit()
        self._card_search.setPlaceholderText("Search card content\u2026")
        self._card_search.setClearButtonEnabled(True)
        self._card_search.setMaximumWidth(220)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filters)
        self._card_search.textChanged.connect(lambda: self._search_timer.start())
        toolbar_layout.addWidget(self._card_search)

        # Separator
        sep1 = QLabel("\u2502")
        sep1.setObjectName("filterLabel")
        toolbar_layout.addWidget(sep1)

        # State filter chips
        self._chip_buttons: dict[str, QPushButton] = {}
        chip_labels = {
            "new": "New",
            "learning": "Learning",
            "due": "Due",
            "upcoming": "Upcoming",
            "suspended": "Suspended",
        }
        for key, label in chip_labels.items():
            btn = QPushButton(label)
            btn.setObjectName("filterChip")
            btn.setCheckable(True)
            btn.toggled.connect(self._on_chip_toggled)
            toolbar_layout.addWidget(btn)
            self._chip_buttons[key] = btn

        # Separator
        sep2 = QLabel("\u2502")
        sep2.setObjectName("filterLabel")
        toolbar_layout.addWidget(sep2)

        # Tag filter dropdown
        tag_label = QLabel("Tag:")
        tag_label.setObjectName("filterLabel")
        toolbar_layout.addWidget(tag_label)
        self._tag_combo = QComboBox()
        self._tag_combo.addItem("All tags", userData="")
        self._tag_combo.setMinimumWidth(100)
        self._tag_combo.currentIndexChanged.connect(self._apply_filters)
        toolbar_layout.addWidget(self._tag_combo)

        # Sort dropdown
        sort_label = QLabel("Sort:")
        sort_label.setObjectName("filterLabel")
        toolbar_layout.addWidget(sort_label)
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Deck order", userData="deck")
        self._sort_combo.addItem("Due date", userData="due")
        self._sort_combo.addItem("Card state", userData="state")
        self._sort_combo.setMinimumWidth(100)
        self._sort_combo.currentIndexChanged.connect(self._apply_filters)
        toolbar_layout.addWidget(self._sort_combo)

        toolbar_layout.addStretch(1)
        right_layout.addWidget(toolbar)

        self.tray = CardTray()
        self.tray.visible_section_changed.connect(self._on_visible_section)
        self.tray.subdeck_created.connect(self._refresh_current_deck)
        self.tray.tags_updated.connect(self._on_tags_updated)
        right_layout.addWidget(self.tray, 1)

        self._splitter.addWidget(right_panel)

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

    def _refresh_current_deck(self) -> None:
        """Re-render both the sidebar tree and the card tray for the current deck."""
        index = self._combo.currentIndex()
        if index < 0:
            return
        self._on_deck_changed(index)

    # ── View / Edit mode toggle ──

    def _on_search_changed(self, text: str) -> None:
        self._deck_tree.filter(text)

    # ── Filter toolbar ──

    def _on_chip_toggled(self, _checked: bool) -> None:
        self._apply_filters()

    def _on_tags_updated(self, tags: list) -> None:
        """Called when the tray emits a new tag list for the current deck."""
        prev_tag = self._tag_combo.currentData()
        self._tag_combo.blockSignals(True)
        self._tag_combo.clear()
        self._tag_combo.addItem("All tags", userData="")
        for t in tags:
            self._tag_combo.addItem(t, userData=t)
        # Restore previous selection if still present
        if prev_tag:
            idx = self._tag_combo.findData(prev_tag)
            if idx >= 0:
                self._tag_combo.setCurrentIndex(idx)
        self._tag_combo.blockSignals(False)

    def _apply_filters(self) -> None:
        """Gather current filter/sort state and push to the tray."""
        search_text = self._card_search.text().strip()
        active_chips = {k for k, btn in self._chip_buttons.items() if btn.isChecked()}
        tag_filter = self._tag_combo.currentData() or ""
        sort_key = self._sort_combo.currentData() or "deck"
        self.tray.set_filters(search_text, active_chips, tag_filter, sort_key)

    def _on_mode_toggled(self, checked: bool) -> None:
        self._edit_mode = checked
        self.tray.edit_mode = checked
        self._deck_tree.edit_mode = checked
        self._update_mode_icon()

    def _update_mode_icon(self) -> None:
        color = self.palette().windowText().color().name()
        template = _SVG_EDIT if self._edit_mode else _SVG_VIEW
        svg = template.format(color=color)
        pm = QPixmap()
        pm.loadFromData(svg.encode("utf-8"))
        self._mode_btn.setIcon(QIcon(pm))
        self._mode_btn.setToolTip("Edit mode" if self._edit_mode else "View mode")

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
