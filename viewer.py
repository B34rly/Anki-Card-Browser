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

from .card_data import get_note_cards
from .card_tray import CardTray
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
_SVG_REFRESH = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/>'
    '<path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/>'
    '</svg>'
)
_SVG_ARROW_DOWN = '<path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/>'
_SVG_ARROW_UP = '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>'


def _svg_icon(svg: str) -> QIcon:
    """Build a QIcon from an inline SVG string."""
    pm = QPixmap()
    pm.loadFromData(svg.encode("utf-8"))
    return QIcon(pm)


class CardBrowserWidget(QWidget):
    """Core browser widget: deck dropdown, sidebar tree, filter toolbar, and card tray.

    Used both inside a standalone QMainWindow (window mode) and embedded
    directly into Anki's main window layout (embedded mode).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_QSS)

        # ── Config (normalised so bad values fall back to documented defaults) ──
        conf = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
        display_mode = conf.get("display_mode", "cards")
        if display_mode not in ("cards", "notes"):
            display_mode = "cards"
        self._default_edit_mode = bool(conf.get("default_edit_mode", True))

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
        self._edit_mode = self._default_edit_mode
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

        self._refresh_btn = QToolButton()
        self._refresh_btn.setToolTip("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_current_deck)
        self._update_refresh_icon()
        search_row.addWidget(self._refresh_btn, 0)

        left_layout.addLayout(search_row)

        self._deck_tree = DeckTree()
        self._deck_tree.deck_selected.connect(self._on_tree_deck_selected)
        self._deck_tree.subdeck_created.connect(self._refresh_current_deck)
        left_layout.addWidget(self._deck_tree, 1)

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

        self.tray = CardTray(display_mode=display_mode)
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

        # Apply the default View/Edit mode now that the tray + deck tree exist
        # (setChecked is signal-blocked, then applied explicitly to avoid both a
        # missed apply when already unchecked and a double-apply when toggled).
        self._mode_btn.blockSignals(True)
        self._mode_btn.setChecked(self._edit_mode)
        self._mode_btn.blockSignals(False)
        self._on_mode_toggled(self._edit_mode)

        # Populate after the event loop starts
        QTimer.singleShot(0, self._populate_combo)

        # Auto-refresh on card changes
        self._hook()

    # ── Dropdown ──

    def _populate_combo(self, force_render: bool = False) -> None:
        """(Re)populate the top-level deck dropdown.

        Preserves the current selection and only re-renders when the selected
        deck actually changes (or nothing has been rendered yet), so reopening
        the embedded browser keeps the deck and scroll position. Pass
        *force_render* for deck-structure changes (a rename keeps the same deck
        id but still needs a re-render).
        """
        prev = self._combo.currentData()
        self._combo.blockSignals(True)
        self._combo.clear()
        for deck_id, name in get_top_level_decks():
            self._combo.addItem(name, userData=deck_id)
        target = 0
        if prev is not None:
            idx = self._combo.findData(prev)
            if idx >= 0:
                target = idx
        if self._combo.count() > 0:
            self._combo.setCurrentIndex(target)
        self._combo.blockSignals(False)

        if self._combo.count() > 0:
            new_data = self._combo.itemData(target)
            if force_render or new_data != prev or self.tray._tree_root is None:
                self._on_deck_changed(target)

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

        self._ease_min, self._ease_max = self._add_range_row(form, "Ease:", 999, "%")
        self._ivl_min, self._ivl_max = self._add_range_row(form, "Interval:", 99999, " d")
        self._lapse_min, self._lapse_max = self._add_range_row(form, "Lapses:", 99999)
        self._reps_min, self._reps_max = self._add_range_row(form, "Reviews:", 99999)

        # Clear all button
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        clear_btn = QPushButton("Clear all filters")
        clear_btn.setObjectName("clearFilters")
        clear_btn.clicked.connect(self._clear_all_filters)
        clear_row.addWidget(clear_btn)
        form.addRow("", clear_row)

        return panel

    def _add_range_row(
        self, form: QFormLayout, label: str, maximum: int, suffix: str = ""
    ) -> tuple[QSpinBox, QSpinBox]:
        """Add a min–max spinbox row to the filter panel; 0 means 'no limit'."""
        row = QHBoxLayout()
        row.setSpacing(4)
        boxes: list[QSpinBox] = []
        for special in ("Min", "Max"):
            sb = QSpinBox()
            sb.setRange(0, maximum)
            sb.setValue(0)
            if suffix:
                sb.setSuffix(suffix)
            sb.setSpecialValueText(special)
            sb.editingFinished.connect(self._apply_filters)
            boxes.append(sb)
        row.addWidget(boxes[0])
        row.addWidget(QLabel("–"))
        row.addWidget(boxes[1])
        row.addStretch()
        form.addRow(label, row)
        return boxes[0], boxes[1]

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
        """Gather advanced filter criteria from the panel widgets (0 = no limit)."""
        criteria: dict = {}
        flag = self._flag_combo.currentData()
        if flag:
            criteria["flag"] = flag
        ranges = (
            # Ease is entered as % but filtered in permille, hence the ×10.
            ("min_ease", self._ease_min, 10), ("max_ease", self._ease_max, 10),
            ("min_ivl", self._ivl_min, 1), ("max_ivl", self._ivl_max, 1),
            ("min_lapses", self._lapse_min, 1), ("max_lapses", self._lapse_max, 1),
            ("min_reps", self._reps_min, 1), ("max_reps", self._reps_max, 1),
        )
        for key, sb, mult in ranges:
            if sb.value() > 0:
                criteria[key] = sb.value() * mult
        return criteria

    def _build_filter_summary(self, criteria: dict, tag_filter: str) -> str:
        """Build a short summary string of active advanced filters."""
        parts: list[str] = []
        if tag_filter:
            parts.append(f"Tag: {tag_filter}")
        if criteria.get("flag"):
            parts.append(f"Flag: {FLAG_NAMES.get(criteria['flag'], '?')}")
        ranges = (
            # (label, min key, max key, unit, divisor back to display units)
            ("Ease", "min_ease", "max_ease", "%", 10),
            ("Ivl", "min_ivl", "max_ivl", "d", 1),
            ("Lapses", "min_lapses", "max_lapses", "", 1),
            ("Reps", "min_reps", "max_reps", "", 1),
        )
        for label, lo_key, hi_key, unit, div in ranges:
            lo = criteria.get(lo_key, 0) // div
            hi = criteria.get(hi_key, 0) // div
            if lo and hi:
                parts.append(f"{label}: {lo}\u2013{hi}{unit}")
            elif lo:
                parts.append(f"{label} \u2265 {lo}{unit}")
            elif hi:
                parts.append(f"{label} \u2264 {hi}{unit}")
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
            f'{_SVG_ARROW_DOWN if desc else _SVG_ARROW_UP}</svg>'
        )
        self._sort_dir_btn.setToolTip(
            "Descending (click for ascending)" if desc
            else "Ascending (click for descending)"
        )
        self._sort_dir_btn.setIcon(_svg_icon(arrow))

    def _on_mode_toggled(self, checked: bool) -> None:
        self._edit_mode = checked
        self.tray.edit_mode = checked
        self._deck_tree.edit_mode = checked
        self._update_mode_icon()

    def _update_mode_icon(self) -> None:
        color = self.palette().windowText().color().name()
        template = _SVG_EDIT if self._edit_mode else _SVG_VIEW
        self._mode_btn.setIcon(_svg_icon(template.format(color=color)))
        self._mode_btn.setToolTip("Edit mode" if self._edit_mode else "View mode")

    def cleanup(self) -> None:
        self._unhook()
        self.tray.cleanup()

    # ── Auto-refresh hooks ──

    _needs_refresh_on_show: bool = False

    def _hook(self) -> None:
        gui_hooks.operation_did_execute.append(self._on_operation_did_execute)
        gui_hooks.sync_did_finish.append(self._on_sync_did_finish)

    def _unhook(self) -> None:
        for hook, cb in (
            (gui_hooks.operation_did_execute, self._on_operation_did_execute),
            (gui_hooks.sync_did_finish, self._on_sync_did_finish),
        ):
            try:
                hook.remove(cb)
            except ValueError:
                pass

    def _on_sync_did_finish(self) -> None:
        """Fully refresh after a sync.

        Synced changes carry their original (remote) mod times, so the
        watermark diff in _refresh_modified can't see them — a full refresh is
        the only reliable response. Scroll position is preserved.
        """
        if self.isVisible():
            self._populate_combo(force_render=True)
        else:
            self._needs_refresh_on_show = True

    def _on_operation_did_execute(self, changes, handler) -> None:
        """React to external collection changes with the minimal refresh.

        The add-on's own mutations update the DOM directly (they don't run
        through CollectionOp, so they never fire this hook); anything that
        reaches here is an external change — an edit in the Browser, Add
        Cards, another add-on, undo.
        """
        if not (
            changes.card or changes.note or changes.deck
            or changes.notetype or changes.study_queues
        ):
            return

        # Not visible → defer a full refresh until we are shown again.
        if not self.isVisible():
            self._needs_refresh_on_show = True
            return

        col = mw.col
        if col is None or self.tray._tree_root is None:
            return

        try:
            # Deck structure or a notetype changed → full refresh, including the
            # top-level dropdown (a rename keeps ids but changes labels).
            if changes.deck or changes.notetype:
                self._populate_combo(force_render=True)
                return

            # Spot-apply membership changes (Add Cards, external delete/move)
            # by diffing the tree's card→deck map. "full" = it re-rendered
            # everything (which also advances the mod watermark) — done.
            structural = self.tray.sync_external_changes(col)
            if structural == "full":
                return

            if changes.card or changes.note:
                self._refresh_modified(col, structural_handled=structural == "spot")
        except Exception:
            # Never leave a stale view (or break the hook chain) because a
            # targeted refresh hit an edge case — converge with a full render.
            self._refresh_current_deck()

    def _refresh_modified(self, col, structural_handled: bool = False) -> None:
        """Refresh the notes an external op touched, found via mod times.

        ``OpChanges`` says *that* something changed but not *what*; the tray's
        mod-time watermark identifies the exact cards/notes regardless of
        where the change originated. Falls back to a full (scroll-preserving)
        re-render when the change is large or can't be pinpointed (undo
        restores old mod times, so nothing in the collection matches).
        *structural_handled* means membership changes were already
        spot-applied — an empty sweep is then expected (e.g. a deletion leaves
        no modified rows behind), not a pinpoint miss.
        """
        card_rows, nids, changed_anywhere = self.tray.consume_modified(col)
        nid_set = set(nids)
        nid_set.update(nid for _cid, nid in card_rows)

        if not nid_set:
            if not changed_anywhere and not structural_handled:
                self.tray.refresh_tree()
            return
        if len(nid_set) > 200:
            # Bulk change; resolving cards per note would be slower than one render.
            self.tray.refresh_tree()
            return

        known = self.tray.known_cids
        to_refresh = [
            (nid, cids)
            for nid, cids in get_note_cards(col, list(nid_set)).items()
            if any(c in known for c in cids)
        ]

        if not to_refresh:
            return  # the change was outside the rendered tree
        if len(to_refresh) > 25 or (len(to_refresh) > 1 and self.tray._has_filters):
            # Bulk change — or several sections to rebuild under active
            # filters, where per-note refreshes each rebuild a section (or the
            # whole tree); one render is cheaper and equally correct.
            self.tray.refresh_tree()
            return
        for nid, cids in to_refresh:
            self.tray.refresh_note(col, nid, cids)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._needs_refresh_on_show:
            self._needs_refresh_on_show = False
            self._refresh_current_deck()

    def _update_refresh_icon(self) -> None:
        color = self.palette().windowText().color().name()
        self._refresh_btn.setIcon(_svg_icon(_SVG_REFRESH.format(color=color)))


# ── Window mode ──


class CardBrowserWindow(QMainWindow):
    """Standalone floating window wrapping CardBrowserWidget."""

    _instance: CardBrowserWindow | None = None

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Card Browser")
        self.resize(1100, 750)
        self._widget = CardBrowserWidget(self)
        self.setCentralWidget(self._widget)

    def closeEvent(self, a0):
        CardBrowserWindow._instance = None
        self._widget.cleanup()
        super().closeEvent(a0)


def open_card_browser_window():
    """Open the Card Browser as a standalone window (singleton)."""
    if CardBrowserWindow._instance is None:
        CardBrowserWindow._instance = CardBrowserWindow(mw)
    CardBrowserWindow._instance.show()
    CardBrowserWindow._instance.activateWindow()
    # Refresh the top-level deck dropdown (a deck may have been added/removed);
    # this is a no-op render when the selection is unchanged.
    CardBrowserWindow._instance._widget._populate_combo()


# ── Embedded mode ──


class EmbeddedBrowser:
    """Manages showing/hiding the CardBrowserWidget inside Anki's main window."""

    _instance: EmbeddedBrowser | None = None

    def __init__(self) -> None:
        self._widget: CardBrowserWidget | None = None
        self._active = False
        # This is a lifetime singleton (the widget is created once and reused), so
        # these hooks are registered exactly once and never need removing.
        gui_hooks.state_will_change.append(self._on_state_will_change)
        # After an op (e.g. editing a card) Anki re-renders its own screen into
        # mw.web and re-shows it on top of us. These post-render hooks fire *after*
        # that show, so re-hiding here reliably keeps us in front — whether the
        # browser was opened over the deck list or a deck's overview.
        gui_hooks.deck_browser_did_render.append(self._reassert)
        gui_hooks.overview_did_refresh.append(self._reassert)

    def show(self) -> None:
        if self._widget is None:
            self._widget = CardBrowserWidget(mw)
            mw.mainLayout.addWidget(self._widget)

        # Hide Anki's own content areas and bring ours to the front. bottomWeb
        # needs a *real* Qt hide (setVisible): its own hide() merely collapses the
        # height to 1px, and Anki re-expands it asynchronously after every render
        # (BottomBar.draw / moveToState → adjustHeightToFit → setFixedHeight lands
        # a turn later, after our render hooks), which flashed the bottom toolbar
        # ("Get Shared / Create Deck / Import File") back over us. A setVisible
        # widget is dropped from the layout and ignores that deferred height change.
        mw.web.hide()
        mw.bottomWeb.setVisible(False)
        self._widget.show()
        self._widget.raise_()
        self._active = True

        # Refresh content (deck list may have changed)
        self._widget._populate_combo()

    def hide(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._widget is not None:
            self._widget.hide()
        # Restore Anki's own content areas. bottomWeb was Qt-hidden via setVisible,
        # so make it visible again and let its height re-fit to content.
        mw.web.show()
        mw.bottomWeb.setVisible(True)
        mw.bottomWeb.show()

    def _reassert(self, *args) -> None:
        """Keep our widget in front if Anki re-rendered its deck browser over us."""
        if self._active and self._widget is not None:
            mw.web.hide()
            mw.bottomWeb.setVisible(False)
            self._widget.raise_()

    def _on_state_will_change(self, new_state: str, old_state: str) -> None:
        # When Anki transitions to any standard state, hide viewer
        if self._active:
            self.hide()

    def teardown(self) -> None:
        """Destroy the widget (profile close) so no stale collection state
        survives into the next profile. The singleton and its hooks remain;
        they no-op until show() builds a fresh widget."""
        self.hide()
        if self._widget is not None:
            self._widget.cleanup()
            self._widget.deleteLater()
            self._widget = None


def open_card_browser_embedded():
    """Show the browser inside Anki's main window."""
    if EmbeddedBrowser._instance is None:
        EmbeddedBrowser._instance = EmbeddedBrowser()
    EmbeddedBrowser._instance.show()


def open_card_browser():
    """Open the Card Browser using the configured mode."""
    conf = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    mode = conf.get("mode", "embedded")
    if mode == "window":
        open_card_browser_window()
    else:
        open_card_browser_embedded()


def _on_profile_will_close() -> None:
    """Tear down any open browser UI before the collection goes away.

    Both hosts hold references into the closing collection (deck tree nodes,
    card-id snapshots, hooks); a fresh widget is built on next open.
    """
    if CardBrowserWindow._instance is not None:
        CardBrowserWindow._instance.close()
    if EmbeddedBrowser._instance is not None:
        EmbeddedBrowser._instance.teardown()


gui_hooks.profile_will_close.append(_on_profile_will_close)
