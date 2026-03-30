"""Data-access helpers for card metadata and Image Occlusion parsing.

Provides bulk SQL fetching of card metadata and regex-based extraction
of IO mask data from Anki's card answer HTML.
"""
from __future__ import annotations

import re
from collections.abc import Sequence


def get_cards_metadata(col, card_ids: Sequence[int]) -> dict[int, dict]:
    """Bulk-fetch card metadata in one SQL query instead of N get_card() calls."""
    if not card_ids:
        return {}
    # Process in chunks to avoid SQLite variable limit
    result: dict[int, dict] = {}
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT c.id, c.type, c.queue, c.due, c.nid, n.mid "
            f"FROM cards c JOIN notes n ON c.nid = n.id "
            f"WHERE c.id IN ({placeholders})",
            *chunk,
        )
        for r in rows:
            result[r[0]] = {
                "cid": r[0], "type": r[1], "queue": r[2],
                "due": r[3], "nid": r[4], "mid": r[5],
            }
    return result


# Cache IO notetype lookups per model id
_io_mid_cache: dict[int, bool] = {}


def is_io_mid(col, mid: int) -> bool:
    """Check if a model id is an Image Occlusion notetype (cached)."""
    if mid in _io_mid_cache:
        return _io_mid_cache[mid]
    nt = col.models.get(mid)
    result = nt is not None and "image occlusion" in nt["name"].lower()
    _io_mid_cache[mid] = result
    return result


# Regex to extract mask data-attributes from cloze/cloze-inactive/cloze-highlight divs
_MASK_RE = re.compile(
    r'<div\s+class="cloze(?:-inactive|-highlight)?"\s+'
    r'(data-(?:ordinal|shape|left|top|width|height|rx|ry|angle|points|fill)="[^"]*"\s*)+',
    re.DOTALL,
)
_ATTR_RE = re.compile(r'data-(shape|left|top|width|height|rx|ry|angle|points|fill)="([^"]*)"')
ACTIVE_ORDINAL_RE = re.compile(r'class="cloze"\s+data-ordinal="(\d+)"')
_IMG_RE = re.compile(r'<img\s[^>]*src="([^"]*)"[^>]*/?\s*>')


def extract_io_data(answer_html: str) -> tuple[str | None, list[dict]]:
    """Extract the image src and all mask shapes from an IO card's answer HTML."""
    img_match = _IMG_RE.search(answer_html)
    img_src = img_match.group(1) if img_match else None

    masks: list[dict] = []
    for m in _MASK_RE.finditer(answer_html):
        attrs: dict[str, str] = {}
        for a in _ATTR_RE.finditer(m.group(0)):
            attrs[a.group(1)] = a.group(2)
        if "shape" in attrs:
            masks.append(attrs)
    return img_src, masks
