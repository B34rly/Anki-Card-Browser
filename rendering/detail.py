"""Detail-overlay markup: content toggle, action bar, chrome + stats."""

from __future__ import annotations

import time
from html import escape as _esc

from ..core.card_state import build_state_badge
from .frames import build_flag_indicator, build_flag_row, build_tag_strip

# revlog.type / ease button labels (Anki's fixed encodings).
_REVLOG_KINDS = {0: "Learn", 1: "Review", 2: "Relearn", 3: "Filtered",
                 4: "Manual", 5: "Resched"}
_EASE_LABELS = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}


def build_revlog_table(rows: list[tuple]) -> str:
    """Review-history table for the card detail overlay.

    *rows* are revlog tuples ``(id_ms, ease, ivl, type, time_ms)``, newest
    first. A negative ivl is seconds (learning steps), positive is days.
    """
    if not rows:
        return ""
    body = ""
    for rid, ease, ivl, rtype, time_ms in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(rid / 1000))
        ivl_txt = f"{ivl}d" if ivl >= 0 else f"{max(1, -ivl // 60)}m"
        body += (
            f"<tr><td>{when}</td>"
            f"<td>{_esc(_REVLOG_KINDS.get(rtype, '?'))}</td>"
            f"<td>{_esc(_EASE_LABELS.get(ease, '–'))}</td>"
            f"<td>{ivl_txt}</td>"
            f"<td>{time_ms / 1000:.1f}s</td></tr>"
        )
    return (
        f'<div class="detail-history">'
        f'<div class="dh-title">Review history</div>'
        f'<table><tr><th>When</th><th>Kind</th><th>Rating</th>'
        f'<th>Interval</th><th>Took</th></tr>{body}</table>'
        f'</div>'
    )


def build_qa_content(
    question_html: str, answer_html: str, fields_html: str = ""
) -> str:
    """Build the card content block with a side toggle.

    The answer side is shown initially (matching the tray cards). When
    *fields_html* is given it becomes a third tab (edit mode only), so the
    rendered card and its raw editable fields never show at once — for
    templated notetypes (cloze, conditional fields) the two genuinely
    differ, and for simple ones a stacked layout would just repeat itself.
    """
    fields_tab = fields_pane = ""
    if fields_html:
        fields_tab = (
            '<button class="ds-toggle edit-only" data-side="f" '
            'onclick="detailShowSide(event,\'f\')">Fields</button>'
        )
        fields_pane = f'<div class="detail-side detail-f">{fields_html}</div>'
    return (
        f'<div class="detail-side-toggle">'
        f'  <button class="ds-toggle" data-side="q" onclick="detailShowSide(event,\'q\')">Question</button>'
        f'  <button class="ds-toggle active" data-side="a" onclick="detailShowSide(event,\'a\')">Answer</button>'
        f'  {fields_tab}'
        f'</div>'
        f'<div class="detail-content show-a" id="detail-content">'
        f'  <div class="detail-side detail-q">{question_html}</div>'
        f'  <div class="detail-side detail-a">{answer_html}</div>'
        f'  {fields_pane}'
        f'</div>'
    )


def build_editable_fields(
    *, nid: int, unit_id: int, fields: list[tuple[str, str]]
) -> str:
    """The detail overlay's in-place field editor (edit mode only).

    Lives inside the same detail view as the stats/actions/history — one
    contenteditable block per field, raw field HTML rendering inside it
    (images and markup included). Typing marks the section dirty, which
    reveals the Revert/Save bar and makes refresh pushes back off (see
    showCardDetail in 20_overlay.js). Save wires to saveNoteEdit; the unit
    id lets Revert re-request this same detail.
    """
    field_blocks = "".join(
        f'<div class="edit-field-label">{_esc(name)}</div>'
        f'<div class="edit-field" contenteditable="true">{value}</div>'
        for name, value in fields
    )
    return (
        f'<div id="detail-fields" class="edit-only" '
        f'data-unit="{unit_id}" data-nid="{nid}">'
        f'{field_blocks}'
        f'<div class="edit-form-actions">'
        f'<button class="detail-btn" onclick="revertNoteEdit()">Revert</button>'
        f'<button class="detail-btn edit-save" onclick="saveNoteEdit()">'
        f'Save <span class="edit-save-hint">Ctrl+Enter</span></button>'
        f'</div>'
        f'</div>'
    )


def build_detail_actions(
    cids_str: str,
    *,
    edit_cid: int,
    suspended: bool,
    buried: bool,
    can_reposition: bool,
    delete_label: str,
    inline_edit: bool = True,
) -> str:
    """Build the horizontal action bar for the detail overlay.

    Actions go through cardAction like the card menus; the tray tracks the
    open overlay and pushes a refreshed detail after each action. With
    *inline_edit* the ✎ button just focuses the detail's own field editor;
    without it (IO groups — occlusion JSON fields) it routes to editCard.
    """
    susp_action = "unsuspend" if suspended else "suspend"
    susp_label = "Unsuspend" if suspended else "Suspend"
    bury_action = "unbury" if buried else "bury"
    bury_label = "Unbury" if buried else "Bury"

    def btn(action: str, label: str) -> str:
        return (
            f'<button class="detail-btn" '
            f'onclick="cardAction(event,\'{action}\',\'{cids_str}\')">{label}</button>'
        )

    edit_btn = (
        '<button class="detail-btn" onclick="focusDetailFields(event)">✎ Edit</button>'
        if inline_edit else
        f'<button class="detail-btn" onclick="editCard(event,{edit_cid})">✎ Edit</button>'
    )
    return (
        f'<div class="detail-actions edit-only">'
        f'{edit_btn}'
        f'{build_flag_row(cids_str)}'
        f'{btn(susp_action, susp_label)}'
        f'{btn(bury_action, bury_label)}'
        f'{btn("review_now", "Review now")}'
        f'{btn("set_due", "Set due…")}'
        f'{btn("forget", "Forget")}'
        f'{btn("reposition", "Reposition…") if can_reposition else ""}'
        f'{btn("add_tag", "Add tag…")}'
        f'{btn("change_deck", "Change deck…")}'
        f'<button class="detail-btn detail-btn-danger" '
        f'onclick="deleteCard(event,\'{cids_str}\')">{delete_label}</button>'
        f'</div>'
    )


def build_detail_html(
    *,
    deck_path: str,
    type_line: str,
    state: str,
    countdown: str,
    flag: int,
    stats: list[tuple[str, str]],
    tags: list[str],
    content_html: str,
    actions_html: str,
    history_html: str = "",
) -> str:
    """Assemble the full detail-overlay body.

    *stats* is a list of (label, value_html) pairs — labels are escaped here,
    values are trusted HTML prepared by the caller. Navigation arrows sit on
    the overlay edges and step through the rendered units in page order.
    """
    # The badge colour rules are scoped under .state-* ancestors (card frames),
    # so give it one here too.
    badge = build_state_badge(state, countdown)
    if state:
        badge = f'<span class="state-{state}">{badge}</span>'
    flag_html = build_flag_indicator(flag)
    stat_cells = "".join(
        f'<div class="detail-stat"><span class="ds-label">{_esc(label)}</span>'
        f'<span class="ds-value">{value}</span></div>'
        for label, value in stats
    )
    tag_strip = build_tag_strip(tags)

    # The nav arrows live in the overlay shell (see tray/render.py), pinned
    # to the card's edges — inside this scrolling content they'd scroll away.
    return (
        f'<div class="detail-header">'
        f'  <div class="detail-title">'
        f'    {flag_html}'
        f'    <span class="detail-deck-path">{_esc(deck_path)}</span>'
        f'    {badge}'
        f'  </div>'
        f'  <div class="detail-type-line">{_esc(type_line)}</div>'
        f'  {tag_strip}'
        f'</div>'
        f'{actions_html}'
        f'<div class="detail-body">{content_html}</div>'
        f'<div class="detail-stats">{stat_cells}</div>'
        f'{history_html}'
    )
