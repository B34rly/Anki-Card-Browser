"""Image Occlusion rendering: SVG masks and the grouped IO card."""

from __future__ import annotations

from ..core.card_state import build_state_badge
from .frames import (
    build_card_menu,
    build_flag_indicator,
    build_tag_strip,
    frame_classes,
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


def build_io_container(img_src: str, masks: list[dict],
                       suspended_ordinals: set[str]) -> str:
    """Build the image + SVG mask overlay block for a group of IO cards."""
    svg_shapes = "\n".join(
        build_svg_mask(m, suspended=m.get("ordinal", "") in suspended_ordinals)
        for m in masks
    )
    return (
        f'<div class="io-container">'
        f'  <img src="{img_src}"/>'
        f'  <svg viewBox="0 0 1 1" preserveAspectRatio="none">'
        f'    {svg_shapes}'
        f'  </svg>'
        f'</div>'
    )


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

    badge = build_state_badge(state, countdown)
    flag_html = build_flag_indicator(flag)
    tag_strip = build_tag_strip(tags or [])

    return (
        f'<div class="{cls}" data-cid="{menu_id}" draggable="true" onclick="expandCard(this)">'
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
        f'    {build_io_container(img_src, masks, suspended_ordinals)}'
        f'    <span class="io-badge">{len(card_ids)} occlusion cards</span>'
        f'  </div>'
        f'</div>'
    )
