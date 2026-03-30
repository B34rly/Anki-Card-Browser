from __future__ import annotations

from aqt import mw, gui_hooks
from aqt.qt import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QLineEdit,
    QSplitter,
    QToolButton,
    QLabel,
    QPushButton,
    QSpinBox,
    QFrame,
    QIcon,
    QPixmap,
    QTimer,
    Qt,
)

from .card_tray import CardTray
from .card_state import FILTER_CHIP_STATES, SORT_KEYS
from .deck_tree import DeckTree
from .decks import get_top_level_decks, find_deck_node

# ── Flag constants ──
FLAG_NAMES: dict[int, str] = {
    1: "Red", 2: "Orange", 3: "Green", 4: "Blue",
    5: "Pink", 6: "Turquoise", 7: "Purple",
}


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
QPushButton#sortDirBtn {
    padding: 4px;
    border-radius: 4px;
    border: 1px solid transparent;
    background: transparent;
}
QPushButton#sortDirBtn:hover {
    background: palette(midlight);
    border-color: palette(mid);
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
QFrame#filterPanel {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 10px;
}
QFrame#filterPanel QLabel {
    font-size: 12px;
}
QFrame#filterPanel QSpinBox {
    padding: 2px 4px;
    border: 1px solid palette(mid);
    border-radius: 3px;
    background: palette(base);
    min-width: 70px;
    min-height: 20px;
    font-size: 12px;
}
QFrame#filterPanel QComboBox {
    padding: 3px 8px;
    min-height: 20px;
    font-size: 12px;
}
QPushButton#filterToggle {
    padding: 3px 10px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background: palette(base);
    font-size: 12px;
    min-height: 20px;
}
QPushButton#filterToggle:hover {
    border-color: palette(dark);
    background: palette(midlight);
}
QPushButton#filterToggle[hasFilters="true"] {
    border-color: palette(highlight);
    color: palette(highlight);
}
QPushButton#clearFilters {
    padding: 3px 10px;
    border: 1px solid palette(mid);
    border-radius: 4px;
    background: palette(base);
    font-size: 11px;
    min-height: 18px;
}
QPushButton#clearFilters:hover {
    border-color: palette(dark);
    background: palette(midlight);
}
QLabel#filterSummary {
    font-size: 11px;
    color: palette(highlight);
    padding: 0 4px;
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


class CardViewerWidget(QWidget):
    """Core viewer widget: deck dropdown, sidebar tree, filter toolbar, and card tray.

    Used both inside a standalone QMainWindow (window mode) and embedded
    directly into Anki's main window layout (embedded mode).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_QSS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

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

        # ── Row 1: search + state chips ──
        row1 = QWidget()
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(8, 6, 8, 2)
        row1_layout.setSpacing(6)

        self._card_search = QLineEdit()
        self._card_search.setPlaceholderText("Search card content\u2026")
        self._card_search.setClearButtonEnabled(True)
        self._card_search.setMaximumWidth(220)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filters)
        self._card_search.textChanged.connect(lambda: self._search_timer.start())
        row1_layout.addWidget(self._card_search)

        sep1 = QLabel("\u2502")
        sep1.setObjectName("filterLabel")
        row1_layout.addWidget(sep1)

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
            row1_layout.addWidget(btn)
            self._chip_buttons[key] = btn

        row1_layout.addStretch(1)
        right_layout.addWidget(row1)

        # ── Row 2: filter button + summary + sort ──
        row2 = QWidget()
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(8, 2, 8, 4)
        row2_layout.setSpacing(6)

        self._filter_btn = QPushButton("\u2699 Filters")
        self._filter_btn.setObjectName("filterToggle")
        self._filter_btn.clicked.connect(self._toggle_filter_panel)
        row2_layout.addWidget(self._filter_btn)

        self._filter_summary = QLabel("")
        self._filter_summary.setObjectName("filterSummary")
        row2_layout.addWidget(self._filter_summary, 1)

        sort_label = QLabel("Sort:")
        sort_label.setObjectName("filterLabel")
        row2_layout.addWidget(sort_label)
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Deck order", userData="deck")
        self._sort_combo.addItem("Due date", userData="due")
        self._sort_combo.addItem("Card state", userData="state")
        self._sort_combo.addItem("Sort field", userData="sort_field")
        self._sort_combo.addItem("Ease", userData="ease")
        self._sort_combo.addItem("Interval", userData="interval")
        self._sort_combo.addItem("Lapse count", userData="lapses")
        self._sort_combo.addItem("Review count", userData="reps")
        self._sort_combo.addItem("Created", userData="created")
        self._sort_combo.addItem("Last modified", userData="modified")
        self._sort_combo.setMinimumWidth(120)
        self._sort_combo.currentIndexChanged.connect(self._apply_filters)
        row2_layout.addWidget(self._sort_combo)

        self._sort_dir_btn = QPushButton()
        self._sort_dir_btn.setObjectName("sortDirBtn")
        self._sort_ascending = True
        self._sort_dir_btn.setToolTip("Toggle ascending / descending")
        self._sort_dir_btn.clicked.connect(self._on_sort_dir_clicked)
        self._update_sort_dir_icon()
        row2_layout.addWidget(self._sort_dir_btn)

        right_layout.addWidget(row2)

        # ── Filter panel (collapsed by default) ──
        self._filter_panel = self._build_filter_panel()
        self._filter_panel.setVisible(False)
        right_layout.addWidget(self._filter_panel)

        self.tray = CardTray()
        self.tray.visible_section_changed.connect(self._on_visible_section)
        self.tray.subdeck_created.connect(self._refresh_current_deck)
        self.tray.tags_updated.connect(self._on_tags_updated)
        self.tray.flags_updated.connect(self._on_flags_updated)
        right_layout.addWidget(self.tray, 1)

        self._splitter.addWidget(right_panel)

        self._splitter.setSizes([260, 840])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        outer.addWidget(self._splitter)

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

    def _build_filter_panel(self) -> QFrame:
        """Build the collapsible advanced filter panel."""
        panel = QFrame()
        panel.setObjectName("filterPanel")
        form = QFormLayout(panel)
        form.setContentsMargins(12, 8, 12, 8)
        form.setSpacing(6)
        form.setHorizontalSpacing(12)

        # Tag
        self._tag_combo = QComboBox()
        self._tag_combo.addItem("All tags", userData="")
        self._tag_combo.setMinimumWidth(140)
        self._tag_combo.currentIndexChanged.connect(self._apply_filters)
        form.addRow("Tag:", self._tag_combo)

        # Flag
        self._flag_combo = QComboBox()
        self._flag_combo.addItem("Any flag", userData=0)
        self._flag_combo.setMinimumWidth(140)
        self._flag_combo.currentIndexChanged.connect(self._apply_filters)
        form.addRow("Flag:", self._flag_combo)

        # Ease range
        ease_row = QHBoxLayout()
        ease_row.setSpacing(4)
        self._ease_min = QSpinBox()
        self._ease_min.setRange(0, 999)
        self._ease_min.setValue(0)
        self._ease_min.setSuffix("%")
        self._ease_min.setSpecialValueText("Min")
        self._ease_min.editingFinished.connect(self._apply_filters)
        ease_row.addWidget(self._ease_min)
        ease_row.addWidget(QLabel("\u2013"))
        self._ease_max = QSpinBox()
        self._ease_max.setRange(0, 999)
        self._ease_max.setValue(0)
        self._ease_max.setSuffix("%")
        self._ease_max.setSpecialValueText("Max")
        self._ease_max.editingFinished.connect(self._apply_filters)
        ease_row.addWidget(self._ease_max)
        ease_row.addStretch()
        form.addRow("Ease:", ease_row)

        # Interval range
        ivl_row = QHBoxLayout()
        ivl_row.setSpacing(4)
        self._ivl_min = QSpinBox()
        self._ivl_min.setRange(0, 99999)
        self._ivl_min.setValue(0)
        self._ivl_min.setSuffix(" d")
        self._ivl_min.setSpecialValueText("Min")
        self._ivl_min.editingFinished.connect(self._apply_filters)
        ivl_row.addWidget(self._ivl_min)
        ivl_row.addWidget(QLabel("\u2013"))
        self._ivl_max = QSpinBox()
        self._ivl_max.setRange(0, 99999)
        self._ivl_max.setValue(0)
        self._ivl_max.setSuffix(" d")
        self._ivl_max.setSpecialValueText("Max")
        self._ivl_max.editingFinished.connect(self._apply_filters)
        ivl_row.addWidget(self._ivl_max)
        ivl_row.addStretch()
        form.addRow("Interval:", ivl_row)

        # Lapses range
        lapse_row = QHBoxLayout()
        lapse_row.setSpacing(4)
        self._lapse_min = QSpinBox()
        self._lapse_min.setRange(0, 99999)
        self._lapse_min.setValue(0)
        self._lapse_min.setSpecialValueText("Min")
        self._lapse_min.editingFinished.connect(self._apply_filters)
        lapse_row.addWidget(self._lapse_min)
        lapse_row.addWidget(QLabel("\u2013"))
        self._lapse_max = QSpinBox()
        self._lapse_max.setRange(0, 99999)
        self._lapse_max.setValue(0)
        self._lapse_max.setSpecialValueText("Max")
        self._lapse_max.editingFinished.connect(self._apply_filters)
        lapse_row.addWidget(self._lapse_max)
        lapse_row.addStretch()
        form.addRow("Lapses:", lapse_row)

        # Reviews range
        reps_row = QHBoxLayout()
        reps_row.setSpacing(4)
        self._reps_min = QSpinBox()
        self._reps_min.setRange(0, 99999)
        self._reps_min.setValue(0)
        self._reps_min.setSpecialValueText("Min")
        self._reps_min.editingFinished.connect(self._apply_filters)
        reps_row.addWidget(self._reps_min)
        reps_row.addWidget(QLabel("\u2013"))
        self._reps_max = QSpinBox()
        self._reps_max.setRange(0, 99999)
        self._reps_max.setValue(0)
        self._reps_max.setSpecialValueText("Max")
        self._reps_max.editingFinished.connect(self._apply_filters)
        reps_row.addWidget(self._reps_max)
        reps_row.addStretch()
        form.addRow("Reviews:", reps_row)

        # Clear all button
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        clear_btn = QPushButton("Clear all filters")
        clear_btn.setObjectName("clearFilters")
        clear_btn.clicked.connect(self._clear_all_filters)
        clear_row.addWidget(clear_btn)
        form.addRow("", clear_row)

        return panel

    def _toggle_filter_panel(self) -> None:
        vis = not self._filter_panel.isVisible()
        self._filter_panel.setVisible(vis)

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
        if prev_tag:
            idx = self._tag_combo.findData(prev_tag)
            if idx >= 0:
                self._tag_combo.setCurrentIndex(idx)
        self._tag_combo.blockSignals(False)

    def _on_flags_updated(self, flags: list) -> None:
        """Called when the tray emits flag values present in the current deck."""
        prev_flag = self._flag_combo.currentData()
        self._flag_combo.blockSignals(True)
        self._flag_combo.clear()
        self._flag_combo.addItem("Any flag", userData=0)
        for f in flags:
            name = FLAG_NAMES.get(f, f"Flag {f}")
            self._flag_combo.addItem(name, userData=f)
        if prev_flag:
            idx = self._flag_combo.findData(prev_flag)
            if idx >= 0:
                self._flag_combo.setCurrentIndex(idx)
        self._flag_combo.blockSignals(False)

    def _build_criteria(self) -> dict:
        """Gather advanced filter criteria from the panel widgets."""
        criteria: dict = {}
        flag = self._flag_combo.currentData()
        if flag:
            criteria["flag"] = flag
        # Ease (convert from % to permille): 0 means "no limit"
        if self._ease_min.value() > 0:
            criteria["min_ease"] = self._ease_min.value() * 10
        if self._ease_max.value() > 0:
            criteria["max_ease"] = self._ease_max.value() * 10
        # Interval
        if self._ivl_min.value() > 0:
            criteria["min_ivl"] = self._ivl_min.value()
        if self._ivl_max.value() > 0:
            criteria["max_ivl"] = self._ivl_max.value()
        # Lapses
        if self._lapse_min.value() > 0:
            criteria["min_lapses"] = self._lapse_min.value()
        if self._lapse_max.value() > 0:
            criteria["max_lapses"] = self._lapse_max.value()
        # Reviews
        if self._reps_min.value() > 0:
            criteria["min_reps"] = self._reps_min.value()
        if self._reps_max.value() > 0:
            criteria["max_reps"] = self._reps_max.value()
        return criteria

    def _build_filter_summary(self, criteria: dict, tag_filter: str) -> str:
        """Build a short summary string of active advanced filters."""
        parts: list[str] = []
        if tag_filter:
            parts.append(f"Tag: {tag_filter}")
        if criteria.get("flag"):
            parts.append(f"Flag: {FLAG_NAMES.get(criteria['flag'], '?')}")
        if criteria.get("min_ease") or criteria.get("max_ease"):
            lo = criteria.get("min_ease", 0) // 10
            hi = criteria.get("max_ease", 0) // 10
            if lo and hi:
                parts.append(f"Ease: {lo}\u2013{hi}%")
            elif lo:
                parts.append(f"Ease \u2265 {lo}%")
            else:
                parts.append(f"Ease \u2264 {hi}%")
        if criteria.get("min_ivl") or criteria.get("max_ivl"):
            lo = criteria.get("min_ivl", 0)
            hi = criteria.get("max_ivl", 0)
            if lo and hi:
                parts.append(f"Ivl: {lo}\u2013{hi}d")
            elif lo:
                parts.append(f"Ivl \u2265 {lo}d")
            else:
                parts.append(f"Ivl \u2264 {hi}d")
        if criteria.get("min_lapses") or criteria.get("max_lapses"):
            lo = criteria.get("min_lapses", 0)
            hi = criteria.get("max_lapses", 0)
            if lo and hi:
                parts.append(f"Lapses: {lo}\u2013{hi}")
            elif lo:
                parts.append(f"Lapses \u2265 {lo}")
            else:
                parts.append(f"Lapses \u2264 {hi}")
        if criteria.get("min_reps") or criteria.get("max_reps"):
            lo = criteria.get("min_reps", 0)
            hi = criteria.get("max_reps", 0)
            if lo and hi:
                parts.append(f"Reps: {lo}\u2013{hi}")
            elif lo:
                parts.append(f"Reps \u2265 {lo}")
            else:
                parts.append(f"Reps \u2264 {hi}")
        return "  \u00b7  ".join(parts)

    def _apply_filters(self) -> None:
        """Gather current filter/sort state and push to the tray."""
        search_text = self._card_search.text().strip()
        active_chips = {k for k, btn in self._chip_buttons.items() if btn.isChecked()}
        tag_filter = self._tag_combo.currentData() or ""
        sort_key = self._sort_combo.currentData() or "deck"
        sort_reverse = not self._sort_ascending
        criteria = self._build_criteria()

        # Update summary label and filter button indicator
        summary = self._build_filter_summary(criteria, tag_filter)
        self._filter_summary.setText(summary)
        has_advanced = bool(criteria or tag_filter)
        self._filter_btn.setProperty("hasFilters", has_advanced)
        self._filter_btn.style().unpolish(self._filter_btn)
        self._filter_btn.style().polish(self._filter_btn)

        self.tray.set_filters(search_text, active_chips, tag_filter, sort_key, sort_reverse, criteria)

    def _clear_all_filters(self) -> None:
        """Reset all filter controls to defaults."""
        # Block signals during reset to avoid repeated re-renders
        for btn in self._chip_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self._tag_combo.blockSignals(True)
        self._tag_combo.setCurrentIndex(0)
        self._tag_combo.blockSignals(False)
        self._flag_combo.blockSignals(True)
        self._flag_combo.setCurrentIndex(0)
        self._flag_combo.blockSignals(False)
        for sb in (self._ease_min, self._ease_max, self._ivl_min, self._ivl_max,
                    self._lapse_min, self._lapse_max, self._reps_min, self._reps_max):
            sb.blockSignals(True)
            sb.setValue(0)
            sb.blockSignals(False)
        self._card_search.clear()
        self._sort_combo.blockSignals(True)
        self._sort_combo.setCurrentIndex(0)
        self._sort_combo.blockSignals(False)
        self._sort_ascending = True
        self._update_sort_dir_icon()
        self._apply_filters()

    def _on_sort_dir_clicked(self) -> None:
        self._sort_ascending = not self._sort_ascending
        self._update_sort_dir_icon()
        self._apply_filters()

    def _update_sort_dir_icon(self) -> None:
        """Update the asc/desc toggle button icon."""
        color = self.palette().windowText().color().name()
        desc = not self._sort_ascending
        # Down arrow = descending, Up arrow = ascending
        arrow = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
        )
        if desc:
            arrow += '<path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/>'
            self._sort_dir_btn.setToolTip("Descending (click for ascending)")
        else:
            arrow += '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>'
            self._sort_dir_btn.setToolTip("Ascending (click for descending)")
        arrow += '</svg>'
        pm = QPixmap()
        pm.loadFromData(arrow.encode("utf-8"))
        self._sort_dir_btn.setIcon(QIcon(pm))

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

    def cleanup(self) -> None:
        self.tray.cleanup()


# ── Window mode ──


class CardViewerWindow(QMainWindow):
    """Standalone floating window wrapping CardViewerWidget."""

    _instance: CardViewerWindow | None = None

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Card Viewer")
        self.resize(1100, 750)
        self._widget = CardViewerWidget(self)
        self.setCentralWidget(self._widget)

    def closeEvent(self, a0):
        CardViewerWindow._instance = None
        self._widget.cleanup()
        super().closeEvent(a0)


def open_card_viewer_window():
    """Open the Card Viewer as a standalone window (singleton)."""
    if CardViewerWindow._instance is None:
        CardViewerWindow._instance = CardViewerWindow(mw)
    CardViewerWindow._instance.show()
    CardViewerWindow._instance.activateWindow()


# ── Embedded mode ──


class EmbeddedViewer:
    """Manages showing/hiding the CardViewerWidget inside Anki's main window."""

    _instance: EmbeddedViewer | None = None

    def __init__(self) -> None:
        self._widget: CardViewerWidget | None = None
        self._active = False
        gui_hooks.state_will_change.append(self._on_state_will_change)

    def show(self) -> None:
        if self._widget is None:
            self._widget = CardViewerWidget(mw)
            mw.mainLayout.addWidget(self._widget)

        # Hide Anki's own content areas
        mw.web.hide()
        mw.bottomWeb.hide()
        self._widget.show()
        self._active = True

        # Refresh content (deck list may have changed)
        self._widget._populate_combo()

    def hide(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._widget is not None:
            self._widget.hide()
        # Restore Anki's own content areas
        mw.web.show()
        mw.bottomWeb.show()

    def _on_state_will_change(self, new_state: str, old_state: str) -> None:
        # When Anki transitions to any standard state, hide viewer
        if self._active:
            self.hide()


def open_card_viewer_embedded():
    """Show the viewer inside Anki's main window."""
    if EmbeddedViewer._instance is None:
        EmbeddedViewer._instance = EmbeddedViewer()
    EmbeddedViewer._instance.show()


def open_card_viewer():
    """Open the Card Viewer using the configured mode."""
    conf = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    mode = conf.get("mode", "embedded")
    if mode == "window":
        open_card_viewer_window()
    else:
        open_card_viewer_embedded()
