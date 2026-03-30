"""HTML rendering helpers for card frames and Image Occlusion cards.

Pure functions that take card data and return HTML strings. No Anki
collection access — all needed data is passed in as arguments.
"""
from __future__ import annotations

from html import escape as _esc

from .card_state import build_state_badge


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
) -> str:
    """Build a single grouped IO card with image + SVG mask overlay."""
    cls_parts = ["card-frame"]
    if all_suspended:
        cls_parts.append("suspended")
    if state:
        cls_parts.append(f"state-{state}")
    cls = " ".join(cls_parts)
    cids_str = ",".join(str(c) for c in card_ids)
    menu_id = card_ids[0]
    toggle_action = "unsuspend_group" if all_suspended else "suspend_group"
    toggle_label = "Unsuspend all" if all_suspended else "Suspend all"

    svg_shapes = "\n".join(
        build_svg_mask(m, suspended=m.get("ordinal", "") in suspended_ordinals)
        for m in masks
    )

    badge = build_state_badge(state, countdown)

    return (
        f'<div class="{cls}" onclick="expandCard(this)">'
        f'  {badge}'
        f'  <button class="card-menu-btn" onclick="toggleMenu(event,\'{menu_id}\')">&#8942;</button>'
        f'  <div class="card-menu" id="menu-{menu_id}">'
        f'    <button onclick="cardAction(event,\'{toggle_action}\',\'{cids_str}\')">{toggle_label}</button>'
        f'    <button onclick="cardAction(event,\'review_now_group\',\'{cids_str}\')">Review all now</button>'
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
    from anki.cards import CardId
    from anki.consts import QUEUE_TYPE_SUSPENDED
    from .card_state import card_state_from_meta, card_countdown_from_meta

    card = col.get_card(CardId(cid))
    suspended = card.queue == QUEUE_TYPE_SUSPENDED
    m = {"queue": card.queue, "type": card.type, "due": card.due}
    state = card_state_from_meta(m, col.sched.today)
    countdown = card_countdown_from_meta(m, col.sched.today)

    cls_parts = ["card-frame"]
    if suspended:
        cls_parts.append("suspended")
    if state:
        cls_parts.append(f"state-{state}")
    cls = " ".join(cls_parts)

    toggle_label = "Unsuspend" if suspended else "Suspend"
    toggle_action = "unsuspend" if suspended else "suspend"
    answer_html = card.answer()
    badge = build_state_badge(state, countdown)
    return (
        f'<div class="{cls}" onclick="expandCard(this)">'
        f'  {badge}'
        f'  <button class="card-menu-btn" onclick="toggleMenu(event,{cid})">&#8942;</button>'
        f'  <div class="card-menu" id="menu-{cid}">'
        f'    <button onclick="cardAction(event,\'{toggle_action}\',{cid})">{toggle_label}</button>'
        f'    <button onclick="cardAction(event,\'review_now\',{cid})">Review now</button>'
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
