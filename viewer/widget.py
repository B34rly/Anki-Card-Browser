from __future__ import annotations

from aqt import mw, gui_hooks
from aqt.qt import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QComboBox,
    QLineEdit,
    QSplitter,
    QToolButton,
    QLabel,
    QPushButton,
    QTimer,
    Qt,
)

from ..tray import CardTray
from ..decks.sidebar import DeckTree
from ..decks import get_top_level_decks, find_deck_node

from .style import (
    _QSS,
    _SVG_EDIT,
    _SVG_VIEW,
    _SVG_REFRESH,
    _SVG_ARROW_DOWN,
    _SVG_ARROW_UP,
    _svg_icon,
)
from .filter_bar import FLAG_NAMES, build_filter_panel, build_criteria, update_filter_chips
from .searches import open_saved_search_menu


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
        edit_target = conf.get("edit_target", "browser")
        if edit_target not in ("browser", "inline"):
            edit_target = "browser"

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
        self._search.setPlaceholderText("Search subdecks…")
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
        self._card_search.setPlaceholderText("Search card content…")
        self._card_search.setToolTip(
            "Plain text searches note content.\n"
            "Queries with a colon use Anki search syntax, e.g.\n"
            "tag:leech · is:due · flag:1 · added:7 · prop:ivl>=10"
        )
        self._card_search.setClearButtonEnabled(True)
        self._card_search.setMaximumWidth(220)
        self._saved_search_btn = QPushButton("☆")
        self._saved_search_btn.setObjectName("sortDirBtn")
        self._saved_search_btn.setToolTip("Saved searches")
        self._saved_search_btn.clicked.connect(
            lambda: open_saved_search_menu(self, self._saved_search_btn)
        )
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filters)
        self._card_search.textChanged.connect(lambda: self._search_timer.start())
        row1_layout.addWidget(self._card_search)
        row1_layout.addWidget(self._saved_search_btn)

        sep1 = QLabel("│")
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

        self._filter_btn = QPushButton("⚙ Filters")
        self._filter_btn.setObjectName("filterToggle")
        self._filter_btn.clicked.connect(self._toggle_filter_panel)
        row2_layout.addWidget(self._filter_btn)

        for glyph, tip, collapsed in (
            ("⊟", "Collapse all subdecks", True),
            ("⊞", "Expand all subdecks", False),
        ):
            btn = QPushButton(glyph)
            btn.setObjectName("sortDirBtn")
            btn.setToolTip(tip)
            btn.clicked.connect(
                lambda _=False, c=collapsed: self.tray.set_all_collapsed(c)
            )
            row2_layout.addWidget(btn)

        # Active advanced filters as removable chips (see filter_bar).
        chips_box = QWidget()
        self._active_chips_layout = QHBoxLayout(chips_box)
        self._active_chips_layout.setContentsMargins(0, 0, 0, 0)
        self._active_chips_layout.setSpacing(4)
        row2_layout.addWidget(chips_box)
        row2_layout.addStretch(1)

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
        self._filter_panel = build_filter_panel(self)
        self._filter_panel.setVisible(False)
        right_layout.addWidget(self._filter_panel)

        self.tray = CardTray(display_mode=display_mode, edit_target=edit_target)
        self.tray.visible_section_changed.connect(self._on_visible_section)
        self.tray.subdeck_created.connect(self._refresh_current_deck)
        self.tray.tags_updated.connect(self._on_tags_updated)
        self.tray.flags_updated.connect(self._on_flags_updated)
        self.tray.tag_filter_requested.connect(self._on_tag_filter_requested)
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

    def _toggle_filter_panel(self) -> None:
        vis = not self._filter_panel.isVisible()
        self._filter_panel.setVisible(vis)

    def _on_chip_toggled(self, _checked: bool) -> None:
        self._apply_filters()

    def _on_tag_filter_requested(self, tag: str) -> None:
        """A tag pill was clicked in the page — filter by that tag."""
        idx = self._tag_combo.findData(tag)
        if idx < 0:
            self._tag_combo.addItem(tag, userData=tag)
            idx = self._tag_combo.count() - 1
        # currentIndexChanged → _apply_filters (no-op when already selected).
        self._tag_combo.setCurrentIndex(idx)

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

    def _apply_filters(self) -> None:
        """Gather current filter/sort state and push to the tray."""
        # A chip click / sort change / clear-all landing while the search
        # debounce is pending must not render the same page twice.
        self._search_timer.stop()
        search_text = self._card_search.text().strip()
        active_chips = {k for k, btn in self._chip_buttons.items() if btn.isChecked()}
        tag_filter = self._tag_combo.currentData() or ""
        sort_key = self._sort_combo.currentData() or "deck"
        sort_reverse = not self._sort_ascending
        criteria = build_criteria(self)

        # Update the removable-chip row and filter button indicator
        update_filter_chips(self, criteria, tag_filter)
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
        tray's watermark diff can't see them — a full refresh is
        the only reliable response. Scroll position is preserved.
        """
        if self.isVisible():
            self._populate_combo(force_render=True)
        else:
            self._needs_refresh_on_show = True

    def _on_operation_did_execute(self, changes, handler) -> None:
        """React to structural collection changes (deck / notetype).

        Card- and note-level changes are handled by the tray's own
        operation_did_execute handler (one pipeline for our ops and external
        ones alike); this widget only rebuilds what the tray can't — the
        top-level deck dropdown and the sidebar (a rename keeps ids but
        changes labels/templates).
        """
        if not (changes.deck or changes.notetype):
            return
        if not self.isVisible():
            self._needs_refresh_on_show = True
            return
        try:
            self._populate_combo(force_render=True)
        except Exception:
            # Never leave a stale view because a refresh hit an edge case.
            self._refresh_current_deck()


    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._needs_refresh_on_show:
            self._needs_refresh_on_show = False
            self._refresh_current_deck()

    def _update_refresh_icon(self) -> None:
        color = self.palette().windowText().color().name()
        self._refresh_btn.setIcon(_svg_icon(_SVG_REFRESH.format(color=color)))
