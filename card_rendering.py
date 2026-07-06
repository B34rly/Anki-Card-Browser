"""HTML rendering helpers for card frames, Image Occlusion, and note groups.

Pure functions that take card data and return HTML strings. No Anki
collection access — all needed data is passed in as arguments.
"""
from __future__ import annotations

import re
from html import escape as _esc

from anki.cards import CardId
from anki.consts import (
    QUEUE_TYPE_SUSPENDED,
    QUEUE_TYPE_MANUALLY_BURIED,
    QUEUE_TYPE_SIBLING_BURIED,
    QUEUE_TYPE_NEW,
    CARD_TYPE_NEW,
)

from .card_state import (
    build_state_badge,
    card_state_from_meta,
    card_countdown_from_meta,
)

# ── Cloze marker styling ──
_CLOZE_RE = re.compile(r'\{\{c(\d+)::(.+?)(?:::(.+?))?\}\}', re.DOTALL)
_HTML_STRIP_RE = re.compile(r'<[^>]+>')


def frame_classes(state: str, suspended: bool, buried: bool = False, *extra: str) -> str:
    """Class list for a card frame; suspended outranks buried, then the state."""
    parts = ["card-frame", *extra]
    if suspended:
        parts.append("suspended")
    elif buried:
        parts.append("buried")
    if state:
        parts.append(f"state-{state}")
    return " ".join(parts)


def build_tag_strip(tags: list[str]) -> str:
    """Build an inline scrollable tag strip for the card top bar."""
    if not tags:
        return ""
    pills = " ".join(f'<span class="card-tag">{_esc(t)}</span>' for t in tags)
    return f'<div class="card-tag-strip">{pills}</div>'


# Flag colours (1-7) matching Anki's flag palette.
FLAG_COLORS = {
    1: "#e74c3c", 2: "#e67e22", 3: "#2ecc71", 4: "#3498db",
    5: "#e84393", 6: "#1abc9c", 7: "#9b59b6",
}


def build_flag_indicator(flag: int) -> str:
    """Build a small coloured dot showing a card's flag (empty if unflagged)."""
    color = FLAG_COLORS.get(flag)
    if not color:
        return ""
    return f'<span class="card-flag" style="background:{color}" title="Flag {flag}"></span>'


def build_flag_row(cids_str: str) -> str:
    """Build the row of flag swatches (1-7 + clear) for a card menu."""
    swatches = "".join(
        f'<button class="flag-swatch" style="background:{c}" title="Flag {n}" '
        f'onclick="cardAction(event,\'flag_{n}\',\'{cids_str}\')"></button>'
        for n, c in FLAG_COLORS.items()
    )
    return (
        f'<div class="flag-row">{swatches}'
        f'<button class="flag-swatch flag-clear" title="Clear flag" '
        f'onclick="cardAction(event,\'flag_0\',\'{cids_str}\')">✕</button>'
        f'</div>'
    )


def build_card_menu(
    cids_str: str,
    *,
    suspended: bool,
    buried: bool,
    is_group: bool,
    can_reposition: bool,
    delete_label: str,
) -> str:
    """Build the inner buttons of a card / group dropdown menu.

    All actions operate on *cids_str* (a comma-separated card-id list), so the
    same menu serves single cards, IO groups and note groups.
    """
    suffix = " all" if is_group else ""
    susp_action = "unsuspend" if suspended else "suspend"
    susp_label = ("Unsuspend" if suspended else "Suspend") + suffix
    bury_action = "unbury" if buried else "bury"
    bury_label = ("Unbury" if buried else "Bury") + suffix
    bury_btn = f'<button onclick="cardAction(event,\'{bury_action}\',\'{cids_str}\')">{bury_label}</button>'

    reposition_btn = (
        f'<button onclick="cardAction(event,\'reposition\',\'{cids_str}\')">Reposition…</button>'
        if can_reposition else ""
    )

    return (
        f'{build_flag_row(cids_str)}'
        f'<hr class="card-menu-sep">'
        f'<button onclick="cardAction(event,\'{susp_action}\',\'{cids_str}\')">{susp_label}</button>'
        f'{bury_btn}'
        f'<button onclick="cardAction(event,\'review_now\',\'{cids_str}\')">Review{suffix} now</button>'
        f'<button onclick="cardAction(event,\'set_due\',\'{cids_str}\')">Set due date…</button>'
        f'<button onclick="cardAction(event,\'forget\',\'{cids_str}\')">Forget{suffix}</button>'
        f'{reposition_btn}'
        f'<hr class="card-menu-sep">'
        f'<button onclick="cardAction(event,\'add_tag\',\'{cids_str}\')">Add tag…</button>'
        f'<button onclick="cardAction(event,\'remove_tag\',\'{cids_str}\')">Remove tag…</button>'
        f'<button onclick="cardAction(event,\'change_deck\',\'{cids_str}\')">Change deck…</button>'
        f'<hr class="card-menu-sep">'
        f'<button class="card-menu-danger edit-only" onclick="deleteCard(event,\'{cids_str}\')">{delete_label}</button>'
    )


def build_svg_mask(mask: dict, suspended: bool = False) -> str:
    """Build an SVG element for a single mask shape."""
    shape = mask.get("shape", "rect")
    if suspended:
        fill = "rgba(150, 150, 150, 0.5)"
    else:
        fill = "rgba(255, 100, 100, 0.4)"

    if shape == "rect":
        l = float(mask.get("left", 0))
        t = float(mask.get("top", 0))
        w = float(mask.get("width", 0))
        h = float(mask.get("height", 0))
        return f'<rect x="{l}" y="{t}" width="{w}" height="{h}" fill="{fill}" rx="0.005"/>'
    elif shape == "ellipse":
        l = float(mask.get("left", 0))
        t = float(mask.get("top", 0))
        w = float(mask.get("width", 0))
        h = float(mask.get("height", 0))
        cx = l + w / 2
        cy = t + h / 2
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{w / 2}" ry="{h / 2}" fill="{fill}"/>'
    elif shape == "polygon":
        pts = mask.get("points", "")
        svg_pts = " ".join(
            f"{float(x)},{float(y)}"
            for pair in pts.strip().split()
            if len(pair.split(",")) == 2
            for x, y in [pair.split(",")]
        )
        return f'<polygon points="{svg_pts}" fill="{fill}"/>'
    return ""


def build_io_card_html(
    img_src: str,
    masks: list[dict],
    card_ids: list[int],
    suspended_ordinals: set[str],
    all_suspended: bool,
    state: str = "",
    countdown: str = "",
    tags: list[str] | None = None,
    all_buried: bool = False,
    flag: int = 0,
) -> str:
    """Build a single grouped IO card with image + SVG mask overlay."""
    cls = frame_classes(state, all_suspended, all_buried)
    cids_str = ",".join(str(c) for c in card_ids)
    menu_id = card_ids[0]

    svg_shapes = "\n".join(
        build_svg_mask(m, suspended=m.get("ordinal", "") in suspended_ordinals)
        for m in masks
    )

    badge = build_state_badge(state, countdown)
    flag_html = build_flag_indicator(flag)
    tag_strip = build_tag_strip(tags or [])

    return (
        f'<div class="{cls}" data-cid="{menu_id}" onclick="expandCard(this)">'
        f'  <div class="card-top-bar">'
        f'    {flag_html}'
        f'    {badge}'
        f'    {tag_strip}'
        f'    <div class="card-actions">'
        f'      <button class="edit-card-btn" onclick="editCard(event,{card_ids[0]})" title="Edit card">&#9998;</button>'
        f'      <button class="card-menu-btn" onclick="toggleMenu(event,\'{menu_id}\')">&#8942;</button>'
        f'    </div>'
        f'  </div>'
        f'  <div class="card-menu" id="menu-{menu_id}" onclick="event.stopPropagation()">'
        f'    {build_card_menu(cids_str, suspended=all_suspended, buried=all_buried, is_group=True, can_reposition=False, delete_label="Delete cards")}'
        f'  </div>'
        f'  <div class="card-content">'
        f'    <div class="io-container">'
        f'      <img src="{img_src}"/>'
        f'      <svg viewBox="0 0 1 1" preserveAspectRatio="none">'
        f'        {svg_shapes}'
        f'      </svg>'
        f'    </div>'
        f'    <span class="io-badge">{len(card_ids)} occlusion cards</span>'
        f'  </div>'
        f'</div>'
    )


def render_normal_card(col, cid: int) -> str:
    """Render full card HTML for a single non-IO card (called during lazy load)."""
    card = col.get_card(CardId(cid))
    suspended = card.queue == QUEUE_TYPE_SUSPENDED
    buried = card.queue in (QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED)
    is_new = card.queue == QUEUE_TYPE_NEW or card.type == CARD_TYPE_NEW
    m = {"queue": card.queue, "type": card.type, "due": card.due}
    state = card_state_from_meta(m, col.sched.today)
    countdown = card_countdown_from_meta(m, col.sched.today)
    cls = frame_classes(state, suspended, buried)

    answer_html = card.answer()
    badge = build_state_badge(state, countdown)
    flag_html = build_flag_indicator(card.user_flag())
    try:
        tags = card.note().tags
    except Exception:
        tags = []
    tag_strip = build_tag_strip(tags)
    menu = build_card_menu(
        str(cid), suspended=suspended, buried=buried, is_group=False,
        can_reposition=is_new, delete_label="Delete card",
    )
    return (
        f'<div class="{cls}" data-cid="{cid}" onclick="expandCard(this)">'
        f'  <div class="card-top-bar">'
        f'    {flag_html}'
        f'    {badge}'
        f'    {tag_strip}'
        f'    <div class="card-actions">'
        f'      <button class="edit-card-btn" onclick="editCard(event,{cid})" title="Edit card">&#9998;</button>'
        f'      <button class="card-menu-btn" onclick="toggleMenu(event,{cid})">&#8942;</button>'
        f'    </div>'
        f'  </div>'
        f'  <div class="card-menu" id="menu-{cid}" onclick="event.stopPropagation()">'
        f'    {menu}'
        f'  </div>'
        f'  <div class="card-content">{answer_html}</div>'
        f'</div>'
    )


def format_deck_path(full_path: str) -> str:
    """Return a truncated path-style label with the leaf part bolded."""
    parts = full_path.split("::")
    leaf = _esc(parts[-1])
    if len(parts) <= 2:
        prefix_parts = [_esc(p) for p in parts[:-1]]
    else:
        tail3 = parts[-3:]
        tail2 = parts[-2:]
        if sum(len(p) for p in tail3) + 4 <= 50:
            prefix_parts = ["..."] + [_esc(p) for p in tail3[:-1]]
        else:
            prefix_parts = ["..."] + [_esc(p) for p in tail2[:-1]]
    prefix = "::".join(prefix_parts)
    if prefix:
        return f'<span class="deck-path">{prefix}::</span><span class="deck-leaf">{leaf}</span>'
    return f'<span class="deck-leaf">{leaf}</span>'


# ── Note group rendering ──

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


def build_note_group_html(
    nid: int,
    fields_table: str,
    card_ids: list[int],
    card_names: list[tuple[int, str]],
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

    # Card names for the overlay dropdown (embedded as data attributes)
    card_names_str = "|".join(f"{cid}:{_esc(name)}" for cid, name in card_names)

    n_cards = len(card_ids)
    # The container is identified by data-group-lead = lead_cid, which is unique
    # per render (each lead cid appears once) even when one note has cards in two
    # different deck sections. A distinct attribute (not data-cid) also avoids
    # colliding with the expanded list's lead card (data-cid=lead_cid). Group-
    # level refresh/delete target it via replaceGroup/removeGroup(lead_cid).
    gk = lead_cid
    return (
        f'<div class="{cls}" data-group-lead="{gk}" data-nid="{nid}"'
        f' data-card-ids="{cids_str}" data-card-names="{card_names_str}"'
        f' onclick="expandNoteGroup(this)">'
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
