from __future__ import annotations

from aqt.qt import (
    QIcon,
    QPixmap,
)

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
QLabel#matchCount {
    font-size: 12px;
    font-weight: 600;
    color: palette(highlight);
    padding: 0 4px;
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
QPushButton#activeChip {
    padding: 2px 8px;
    border: 1px solid palette(highlight);
    border-radius: 10px;
    background: palette(base);
    color: palette(highlight);
    font-size: 11px;
    min-height: 18px;
}
QPushButton#activeChip:hover {
    background: palette(highlight);
    color: palette(highlighted-text);
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
_SVG_UNDO = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M9 14 4 9l5-5"/>'
    '<path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/></svg>'
)
_SVG_REDO = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="m15 14 5-5-5-5"/>'
    '<path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/></svg>'
)
_SVG_ARROW_DOWN = '<path d="M12 5v14"/><path d="M19 12l-7 7-7-7"/>'
_SVG_ARROW_UP = '<path d="M12 19V5"/><path d="M5 12l7-7 7 7"/>'


def _svg_icon(svg: str) -> QIcon:
    """Build a QIcon from an inline SVG string."""
    pm = QPixmap()
    pm.loadFromData(svg.encode("utf-8"))
    return QIcon(pm)
