"""Data-access helpers for card metadata and Image Occlusion parsing.

Provides bulk SQL fetching of card metadata, content search, tag queries,
and regex-based extraction of IO mask data from Anki's card answer HTML.
"""
from __future__ import annotations

import re
from collections.abc import Sequence


def get_cards_metadata(col, card_ids: Sequence[int]) -> dict[int, dict]:
    """Bulk-fetch card metadata in one SQL query instead of N get_card() calls.

    Returns a dict keyed by card ID with keys:
      cid, type, queue, due, nid, mid, factor, ivl, lapses, reps, flags, mod, sfld
    """
    if not card_ids:
        return {}
    # Process in chunks to avoid SQLite variable limit
    result: dict[int, dict] = {}
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT c.id, c.type, c.queue, c.due, c.nid, n.mid, "
            f"c.factor, c.ivl, c.lapses, c.reps, c.flags, c.mod, n.sfld "
            f"FROM cards c JOIN notes n ON c.nid = n.id "
            f"WHERE c.id IN ({placeholders})",
            *chunk,
        )
        for r in rows:
            result[r[0]] = {
                "cid": r[0], "type": r[1], "queue": r[2],
                "due": r[3], "nid": r[4], "mid": r[5],
                "factor": r[6], "ivl": r[7], "lapses": r[8],
                "reps": r[9], "flags": r[10], "mod": r[11],
                "sfld": r[12],
            }
    return result


def get_flags_for_cards(col, card_ids: Sequence[int]) -> list[int]:
    """Return sorted distinct non-zero flag values present among the given cards."""
    if not card_ids:
        return []
    flag_set: set[int] = set()
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT DISTINCT c.flags FROM cards c "
            f"WHERE c.id IN ({placeholders}) AND c.flags != 0",
            *chunk,
        )
        for (f,) in rows:
            flag_set.add(f)
    return sorted(flag_set)


# ── Strip HTML tags for plain-text content search ──
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def search_cards_by_content(col, card_ids: Sequence[int], query: str) -> list[int]:
    """Return the subset of card_ids whose note fields contain *query* (case-insensitive).

    Searches against notes.flds with HTML tags stripped.
    """
    if not card_ids or not query:
        return list(card_ids)
    query_lower = query.lower()
    matched: list[int] = []
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT c.id, n.flds "
            f"FROM cards c JOIN notes n ON c.nid = n.id "
            f"WHERE c.id IN ({placeholders})",
            *chunk,
        )
        for cid, flds in rows:
            plain = _HTML_TAG_RE.sub("", flds).lower()
            if query_lower in plain:
                matched.append(cid)
    return matched


def get_tags_for_cards(col, card_ids: Sequence[int]) -> list[str]:
    """Return sorted distinct tags from notes associated with the given cards."""
    if not card_ids:
        return []
    tag_set: set[str] = set()
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT DISTINCT n.tags "
            f"FROM cards c JOIN notes n ON c.nid = n.id "
            f"WHERE c.id IN ({placeholders})",
            *chunk,
        )
        for (tags_str,) in rows:
            for t in tags_str.strip().split():
                if t:
                    tag_set.add(t)
    return sorted(tag_set, key=str.lower)


def get_card_tags_map(col, card_ids: Sequence[int]) -> dict[int, list[str]]:
    """Return {cid: [tag, ...]} for the given cards."""
    if not card_ids:
        return {}
    result: dict[int, list[str]] = {}
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT c.id, n.tags "
            f"FROM cards c JOIN notes n ON c.nid = n.id "
            f"WHERE c.id IN ({placeholders})",
            *chunk,
        )
        for cid, tags_str in rows:
            result[cid] = [t for t in tags_str.strip().split() if t]
    return result


def filter_cards_by_tag(col, card_ids: Sequence[int], tag: str) -> list[int]:
    """Return the subset of card_ids whose note has the given tag."""
    if not card_ids or not tag:
        return list(card_ids)
    tag_lower = tag.lower()
    matched: list[int] = []
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT c.id, n.tags "
            f"FROM cards c JOIN notes n ON c.nid = n.id "
            f"WHERE c.id IN ({placeholders})",
            *chunk,
        )
        for cid, tags_str in rows:
            tags = [t.lower() for t in tags_str.strip().split() if t]
            if tag_lower in tags:
                matched.append(cid)
    return matched


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
