from __future__ import annotations

from aqt.qt import (
    QFormLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QFrame,
)

# ── Flag constants ──
FLAG_NAMES: dict[int, str] = {
    1: "Red", 2: "Orange", 3: "Green", 4: "Blue",
    5: "Pink", 6: "Turquoise", 7: "Purple",
}


def build_filter_panel(widget) -> QFrame:
    """Build the collapsible advanced filter panel."""
    panel = QFrame()
    panel.setObjectName("filterPanel")
    form = QFormLayout(panel)
    form.setContentsMargins(12, 8, 12, 8)
    form.setSpacing(6)
    form.setHorizontalSpacing(12)

    # Tag
    widget._tag_combo = QComboBox()
    widget._tag_combo.addItem("All tags", userData="")
    widget._tag_combo.setMinimumWidth(140)
    widget._tag_combo.currentIndexChanged.connect(widget._apply_filters)
    form.addRow("Tag:", widget._tag_combo)

    # Flag
    widget._flag_combo = QComboBox()
    widget._flag_combo.addItem("Any flag", userData=0)
    widget._flag_combo.setMinimumWidth(140)
    widget._flag_combo.currentIndexChanged.connect(widget._apply_filters)
    form.addRow("Flag:", widget._flag_combo)

    widget._ease_min, widget._ease_max = _add_range_row(widget, form, "Ease:", 999, "%")
    widget._ivl_min, widget._ivl_max = _add_range_row(widget, form, "Interval:", 99999, " d")
    widget._lapse_min, widget._lapse_max = _add_range_row(widget, form, "Lapses:", 99999)
    widget._reps_min, widget._reps_max = _add_range_row(widget, form, "Reviews:", 99999)

    # Clear all button
    clear_row = QHBoxLayout()
    clear_row.addStretch()
    clear_btn = QPushButton("Clear all filters")
    clear_btn.setObjectName("clearFilters")
    clear_btn.clicked.connect(widget._clear_all_filters)
    clear_row.addWidget(clear_btn)
    form.addRow("", clear_row)

    return panel


def _add_range_row(
    widget, form: QFormLayout, label: str, maximum: int, suffix: str = ""
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
        sb.editingFinished.connect(widget._apply_filters)
        boxes.append(sb)
    row.addWidget(boxes[0])
    row.addWidget(QLabel("–"))
    row.addWidget(boxes[1])
    row.addStretch()
    form.addRow(label, row)
    return boxes[0], boxes[1]


def build_criteria(widget) -> dict:
    """Gather advanced filter criteria from the panel widgets (0 = no limit)."""
    criteria: dict = {}
    flag = widget._flag_combo.currentData()
    if flag:
        criteria["flag"] = flag
    ranges = (
        # Ease is entered as % but filtered in permille, hence the ×10.
        ("min_ease", widget._ease_min, 10), ("max_ease", widget._ease_max, 10),
        ("min_ivl", widget._ivl_min, 1), ("max_ivl", widget._ivl_max, 1),
        ("min_lapses", widget._lapse_min, 1), ("max_lapses", widget._lapse_max, 1),
        ("min_reps", widget._reps_min, 1), ("max_reps", widget._reps_max, 1),
    )
    for key, sb, mult in ranges:
        if sb.value() > 0:
            criteria[key] = sb.value() * mult
    return criteria


def build_filter_summary(criteria: dict, tag_filter: str) -> str:
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
            parts.append(f"{label}: {lo}–{hi}{unit}")
        elif lo:
            parts.append(f"{label} ≥ {lo}{unit}")
        elif hi:
            parts.append(f"{label} ≤ {hi}{unit}")
    return "  ·  ".join(parts)
