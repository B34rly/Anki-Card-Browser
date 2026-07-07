"""Card frames: the base building blocks of every rendered unit.

Pure functions from card data to HTML — no collection access beyond the
`col` handle render_normal_card needs to fetch one card.
"""

from __future__ import annotations

from html import escape as _esc

from anki.cards import CardId
from anki.consts import (
    CARD_TYPE_NEW,
    QUEUE_TYPE_MANUALLY_BURIED,
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_SIBLING_BURIED,
    QUEUE_TYPE_SUSPENDED,
)

from ..core.card_state import (
    build_state_badge,
    card_countdown_from_meta,
    card_state_from_meta,
)


def build_selection_bar() -> str:
    """The fixed bulk-action bar shown while a multiselect is active.

    Static page chrome: the selected cids are collected client-side, so every
    button goes through selectionAction (JS) rather than baked-in id lists.
    """
    swatches = "".join(
        f'<button class="flag-swatch" style="background:{c}" title="Flag {n}" '
        f'onclick="selectionAction(event,\'flag_{n}\')"></button>'
        for n, c in FLAG_COLORS.items()
    )

    def btn(action: str, label: str, extra_cls: str = "") -> str:
        return (
            f'<button class="sel-btn{extra_cls}" '
            f'onclick="selectionAction(event,\'{action}\')">{label}</button>'
        )

    return (
        f'<div id="selection-bar" onclick="event.stopPropagation()">'
        f'<span id="selection-count">0 selected</span>'
        f'<span class="flag-row">{swatches}'
        f'<button class="flag-swatch flag-clear" title="Clear flag" '
        f'onclick="selectionAction(event,\'flag_0\')">✕</button></span>'
        f'{btn("suspend", "Suspend")}'
        f'{btn("unsuspend", "Unsuspend")}'
        f'{btn("bury", "Bury")}'
        f'{btn("change_deck", "Change deck…")}'
        f'{btn("add_tag", "Add tag…")}'
        f'{btn("delete", "Delete", " sel-danger")}'
        f'<button class="sel-btn sel-close" onclick="clearSelection()" '
        f'title="Clear selection">✕</button>'
        f'</div>'
    )


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
    """Build an inline scrollable tag strip for the card top bar.

    Pills are clickable: they set the toolbar's tag filter (tagClicked).
    """
    if not tags:
        return ""
    pills = " ".join(
        f'<span class="card-tag" data-tag="{_esc(t)}" '
        f'onclick="tagClicked(event,this)" title="Filter by this tag">{_esc(t)}</span>'
        for t in tags
    )
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
    """Build the row of flag swatches (1-7 + clear), used by card menus and
    the detail overlay's action bar."""
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
        f'<div class="{cls}" data-cid="{cid}" draggable="true" onclick="expandCard(this)">'
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
