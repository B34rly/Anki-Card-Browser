"""Note-level rendering: field tables, cloze styling, note groups."""

from __future__ import annotations

import re
from html import escape as _esc

from ..core.card_state import build_state_badge
from .frames import (
    build_card_menu,
    build_flag_indicator,
    build_tag_strip,
    frame_classes,
)


# ── Cloze marker styling ──
_CLOZE_RE = re.compile(r'\{\{c(\d+)::(.+?)(?:::(.+?))?\}\}', re.DOTALL)


_HTML_STRIP_RE = re.compile(r'<[^>]+>')


def _style_cloze_markers(html: str) -> str:
    """Wrap cloze deletion markers in coloured spans for visibility."""
    def _cloze_replacer(m: re.Match) -> str:
        num = m.group(1)
        content = m.group(2)
        hint = m.group(3)
        if hint:
            return (
                f'<span class="cloze-marker">'
                f'<span class="cloze-num">c{num}::</span>'
                f'{content}'
                f'<span class="cloze-hint">::{_esc(hint)}</span>'
                f'</span>'
            )
        return (
            f'<span class="cloze-marker">'
            f'<span class="cloze-num">c{num}::</span>'
            f'{content}'
            f'</span>'
        )
    return _CLOZE_RE.sub(_cloze_replacer, html)


def build_note_fields_table(fields: list[tuple[str, str]]) -> str:
    """Build an HTML table of note fields with field names as labels."""
    rows: list[str] = []
    for name, value in fields:
        plain = _HTML_STRIP_RE.sub("", value).strip()
        if not plain:
            rows.append(
                f'<tr class="note-field-row note-field-empty">'
                f'<td class="note-field-name">{_esc(name)}</td>'
                f'<td class="note-field-value">'
                f'<span class="note-field-placeholder">empty</span>'
                f'</td></tr>'
            )
        else:
            styled = _style_cloze_markers(value)
            rows.append(
                f'<tr class="note-field-row">'
                f'<td class="note-field-name">{_esc(name)}</td>'
                f'<td class="note-field-value">{styled}</td>'
                f'</tr>'
            )
    return f'<table class="note-fields-table">{"  ".join(rows)}</table>'


def build_note_card_count(summary: dict) -> str:
    """Build the compact card-count span for a note group top bar."""
    total = summary["total"]
    parts = (
        f'<span class="sc sc-new">{summary["new"]}N</span> '
        f'<span class="sc sc-learn">{summary["learn"]}L</span> '
        f'<span class="sc sc-upcoming">{summary["upcoming"]}U</span> '
        f'<span class="sc sc-due">{summary["due"]}D</span>'
    )
    return (
        f'<span class="note-card-count">{total} '
        f'<span class="state-counts">({parts})</span> cards</span>'
    )


# ── Detail overlay (card / group inspector) ──


def build_note_group_html(
    nid: int,
    fields_table: str,
    card_ids: list[int],
    summary: dict,
    tags: list[str] | None = None,
    flag: int = 0,
) -> str:
    """Build full HTML for a multi-card note group block."""
    state = summary["dominant_state"]
    countdown = summary["dominant_countdown"]
    all_suspended = summary["all_suspended"]
    all_buried = summary.get("all_buried", False)
    cls = frame_classes(state, all_suspended, all_buried, "note-group")

    lead_cid = card_ids[0]
    cids_str = ",".join(str(c) for c in card_ids)

    badge = build_state_badge(state, countdown)
    flag_html = build_flag_indicator(flag)
    tag_strip = build_tag_strip(tags or [])
    count_html = build_note_card_count(summary)

    n_cards = len(card_ids)
    # The container is identified by data-group-lead = lead_cid, which is unique
    # per render (each lead cid appears once) even when one note has cards in two
    # different deck sections. A distinct attribute (not data-cid) also avoids
    # colliding with the expanded list's lead card (data-cid=lead_cid). Group-
    # level refresh/delete target it via replaceGroup/removeGroup(lead_cid).
    gk = lead_cid
    return (
        f'<div class="{cls}" data-group-lead="{gk}" data-nid="{nid}"'
        f' data-card-ids="{cids_str}"'
        f' draggable="true" onclick="expandNoteGroup(this)">'
        f'  <div class="card-top-bar">'
        f'    {flag_html}'
        f'    {badge}'
        f'    {count_html}'
        f'    {tag_strip}'
        f'    <div class="card-actions">'
        f'      <button class="edit-card-btn" onclick="editCard(event,{lead_cid})" title="Edit note">&#9998;</button>'
        f'      <button class="card-menu-btn" onclick="toggleMenu(event,\'grp-{gk}\')" >&#8942;</button>'
        f'    </div>'
        f'  </div>'
        f'  <div class="card-menu" id="menu-grp-{gk}" onclick="event.stopPropagation()">'
        f'    {build_card_menu(cids_str, suspended=all_suspended, buried=all_buried, is_group=True, can_reposition=False, delete_label="Delete note")}'
        f'  </div>'
        f'  <div class="card-content">'
        f'    {fields_table}'
        f'  </div>'
        f'  <div class="note-cards-toggle" onclick="toggleNoteCards(event,{gk})">'
        f'    Show {n_cards} cards &#9656;'
        f'  </div>'
        f'  <div class="note-cards-body" id="note-cards-{gk}">'
        f'  </div>'
        f'</div>'
    )
