"""Detail-overlay markup: content toggle, action bar, chrome + stats."""

from __future__ import annotations

from html import escape as _esc

from ..core.card_state import build_state_badge
from .frames import build_flag_indicator, build_flag_row, build_tag_strip


def build_qa_content(question_html: str, answer_html: str) -> str:
    """Build the question/answer content block with a side toggle.

    The answer side is shown initially (matching the tray cards); the toggle
    switches the .show-q / .show-a class on the container.
    """
    return (
        f'<div class="detail-side-toggle">'
        f'  <button class="ds-toggle" onclick="detailShowSide(event,\'q\')">Question</button>'
        f'  <button class="ds-toggle active" onclick="detailShowSide(event,\'a\')">Answer</button>'
        f'</div>'
        f'<div class="detail-content show-a" id="detail-content">'
        f'  <div class="detail-side detail-q">{question_html}</div>'
        f'  <div class="detail-side detail-a">{answer_html}</div>'
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
) -> str:
    """Build the horizontal action bar for the detail overlay.

    Actions go through cardAction like the card menus; the tray tracks the
    open overlay and pushes a refreshed detail after each action.
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

    return (
        f'<div class="detail-actions edit-only">'
        f'<button class="detail-btn" onclick="editCard(event,{edit_cid});closeOverlay()">✎ Edit</button>'
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

    return (
        f'<button class="detail-nav detail-nav-prev" onclick="overlayNav(-1)" title="Previous card">&#8249;</button>'
        f'<button class="detail-nav detail-nav-next" onclick="overlayNav(1)" title="Next card">&#8250;</button>'
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
    )
