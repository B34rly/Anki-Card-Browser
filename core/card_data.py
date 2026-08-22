"""Data-access helpers for card metadata and Image Occlusion parsing.

Provides bulk SQL fetching of card metadata, content search, tag queries,
and regex-based extraction of IO mask data from Anki's card answer HTML.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Sequence

# SQLite limits the number of host parameters per statement (default 999), so
# `... WHERE c.id IN (?, ?, …)` queries are run over card ids in chunks.
_CHUNK_SIZE = 500


def _query_in_chunks(col, select_sql: str, card_ids: Sequence[int]) -> Iterator[tuple]:
    """Yield rows for ``select_sql`` run over *card_ids* in chunks.

    *select_sql* must contain a single ``{ph}`` placeholder for the
    comma-separated ``?`` markers of the ``IN (...)`` clause.
    """
    for i in range(0, len(card_ids), _CHUNK_SIZE):
        chunk = card_ids[i : i + _CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        yield from col.db.all(select_sql.format(ph=placeholders), *chunk)


def get_cards_metadata(col, card_ids: Sequence[int]) -> dict[int, dict]:
    """Bulk-fetch card metadata in one SQL query instead of N get_card() calls.

    Returns a dict keyed by card ID with keys:
      cid, type, queue, due, nid, mid, did, factor, ivl, lapses, reps, flags,
      mod, sfld
    """
    if not card_ids:
        return {}
    result: dict[int, dict] = {}
    rows = _query_in_chunks(
        col,
        "SELECT c.id, c.type, c.queue, c.due, c.nid, n.mid, c.did, "
        "c.factor, c.ivl, c.lapses, c.reps, c.flags, c.mod, n.sfld "
        "FROM cards c JOIN notes n ON c.nid = n.id "
        "WHERE c.id IN ({ph})",
        card_ids,
    )
    for r in rows:
        result[r[0]] = {
            "cid": r[0], "type": r[1], "queue": r[2],
            "due": r[3], "nid": r[4], "mid": r[5],
            "did": r[6], "factor": r[7], "ivl": r[8],
            "lapses": r[9], "reps": r[10], "flags": r[11],
            "mod": r[12], "sfld": r[13],
        }
    return result


def get_card_decks(col, card_ids: Sequence[int]) -> dict[int, int]:
    """Map card id → deck id for *card_ids* (one chunked query).

    Cheaper than get_cards_metadata when only deck membership is needed.
    """
    if not card_ids:
        return {}
    return {
        cid: did
        for cid, did in _query_in_chunks(
            col, "SELECT id, did FROM cards WHERE id IN ({ph})", card_ids
        )
    }


def get_deck_cards(col, deck_ids: Sequence[int]) -> dict[int, int]:
    """Map card id → deck id for every card in *deck_ids*.

    Walks the indexed ``cards.did`` column, so it is far cheaper than looking
    the same cards up by id (external-change membership diffing).
    """
    if not deck_ids:
        return {}
    return {
        cid: did
        for cid, did in _query_in_chunks(
            col, "SELECT id, did FROM cards WHERE did IN ({ph})", deck_ids
        )
    }


def get_note_cards(col, note_ids: Sequence[int]) -> dict[int, list[int]]:
    """Map note id → [card ids] (one chunked query, not one call per note)."""
    if not note_ids:
        return {}
    result: dict[int, list[int]] = {}
    for cid, nid in _query_in_chunks(
        col, "SELECT id, nid FROM cards WHERE nid IN ({ph}) ORDER BY ord", note_ids
    ):
        result.setdefault(nid, []).append(cid)
    return result


def get_flags_for_cards(col, card_ids: Sequence[int]) -> list[int]:
    """Return sorted distinct non-zero flag values present among the given cards."""
    if not card_ids:
        return []
    flag_set: set[int] = set()
    for (f,) in _query_in_chunks(
        col,
        "SELECT DISTINCT c.flags FROM cards c "
        "WHERE c.id IN ({ph}) AND c.flags != 0",
        card_ids,
    ):
        flag_set.add(f)
    return sorted(flag_set)


# ── Strip HTML tags for plain-text content search ──
_HTML_TAG_RE = re.compile(r"<[^>]+>")


# Search keywords that mark a query as Anki search syntax. Deliberately a
# fixed allowlist (not "any word:"), so literal text like "12:30" or
# "http://…" stays a plain substring search.
_ANKI_SEARCH_KEYWORD_RE = re.compile(
    r"(?:^|[\s(])-?(?:deck|tag|is|flag|prop|added|edited|introduced|rated|"
    r"resched|note|card|nid|cid|mid|re|nc|w|dupe|has-cd|preset):(?=\S)",
    re.IGNORECASE,
)


def search_cards_with_anki_query(
    col, card_ids: Sequence[int], query: str
) -> list[int] | None:
    """Try *query* as Anki search syntax, restricted to *card_ids*.

    A query is treated as Anki syntax when it uses a known search keyword
    (``tag:x``, ``is:due``, ``flag:1``, ``prop:ivl>=10``, …). Returns None
    when the query isn't Anki syntax or fails to parse, so the caller can
    fall back to plain substring search.
    """
    if not _ANKI_SEARCH_KEYWORD_RE.search(query):
        return None
    try:
        found = set(col.find_cards(query))
    except Exception:
        return None
    return [c for c in card_ids if c in found]


def search_cards_by_content(col, card_ids: Sequence[int], query: str) -> list[int]:
    """Return the subset of card_ids whose note fields contain *query* (case-insensitive).

    Searches against notes.flds with HTML tags stripped.
    """
    if not card_ids or not query:
        return list(card_ids)
    query_lower = query.lower()
    matched: list[int] = []
    for cid, flds in _query_in_chunks(
        col,
        "SELECT c.id, n.flds "
        "FROM cards c JOIN notes n ON c.nid = n.id "
        "WHERE c.id IN ({ph})",
        card_ids,
    ):
        plain = _HTML_TAG_RE.sub("", flds).lower()
        if query_lower in plain:
            matched.append(cid)
    return matched


def notetype_names(col, mids) -> list[tuple[int, str]]:
    """Name-sorted (mid, name) pairs for a set of notetype ids.

    Callers holding card metadata already have the mids
    (``{m["mid"] for m in meta.values()}``) — no SQL needed.
    """
    pairs: list[tuple[int, str]] = []
    for mid in mids:
        nt = col.models.get(mid)
        pairs.append((mid, nt["name"] if nt else f"Notetype {mid}"))
    return sorted(pairs, key=lambda p: p[1].lower())


def get_notetypes_for_cards(col, card_ids: Sequence[int]) -> list[tuple[int, str]]:
    """Sorted (mid, name) pairs of the notetypes present among *card_ids*."""
    if not card_ids:
        return []
    mids: set[int] = set()
    for (mid,) in _query_in_chunks(
        col,
        "SELECT DISTINCT n.mid FROM cards c JOIN notes n ON c.nid = n.id "
        "WHERE c.id IN ({ph})",
        card_ids,
    ):
        mids.add(mid)
    return notetype_names(col, mids)


def get_tags_for_cards(col, card_ids: Sequence[int]) -> list[str]:
    """Return sorted distinct tags from notes associated with the given cards."""
    if not card_ids:
        return []
    tag_set: set[str] = set()
    for (tags_str,) in _query_in_chunks(
        col,
        "SELECT DISTINCT n.tags "
        "FROM cards c JOIN notes n ON c.nid = n.id "
        "WHERE c.id IN ({ph})",
        card_ids,
    ):
        for t in tags_str.strip().split():
            if t:
                tag_set.add(t)
    return sorted(tag_set, key=str.lower)


def filter_cards_by_tag(col, card_ids: Sequence[int], tag: str) -> list[int]:
    """Return the subset of card_ids whose note has the given tag."""
    if not card_ids or not tag:
        return list(card_ids)
    tag_lower = tag.lower()
    matched: list[int] = []
    for cid, tags_str in _query_in_chunks(
        col,
        "SELECT c.id, n.tags "
        "FROM cards c JOIN notes n ON c.nid = n.id "
        "WHERE c.id IN ({ph})",
        card_ids,
    ):
        tags = [t.lower() for t in tags_str.strip().split() if t]
        if tag_lower in tags:
            matched.append(cid)
    return matched


# Cache IO notetype lookups per model id. Cleared on profile switch via
# clear_caches() so model ids from a previous collection are never reused.
_io_mid_cache: dict[int, bool] = {}


def clear_caches() -> None:
    """Reset module-level caches (call when the collection/profile changes)."""
    _io_mid_cache.clear()


def is_io_mid(col, mid: int) -> bool:
    """Check if a model id is an Image Occlusion notetype (cached)."""
    if mid in _io_mid_cache:
        return _io_mid_cache[mid]
    nt = col.models.get(mid)
    result = nt is not None and "image occlusion" in nt["name"].lower()
    _io_mid_cache[mid] = result
    return result


def get_note_fields(col, nid: int) -> list[tuple[str, str]]:
    """Return [(field_name, field_value), ...] for a note."""
    from anki.notes import NoteId

    note = col.get_note(NoteId(nid))
    model = col.models.get(note.mid)
    if model is None:
        return list(zip([f"Field {i}" for i in range(len(note.fields))], note.fields))
    field_names = [f["name"] for f in model["flds"]]
    return list(zip(field_names, note.fields))


def get_card_template_names(col, nid: int) -> list[tuple[int, str]]:
    """Return [(cid, template_name), ...] for all cards of a note."""
    from anki.notes import NoteId

    note = col.get_note(NoteId(nid))
    model = col.models.get(note.mid)
    cards = note.cards()
    result: list[tuple[int, str]] = []
    for card in cards:
        if model and card.ord < len(model["tmpls"]):
            name = model["tmpls"][card.ord]["name"]
        else:
            name = f"Card {card.ord + 1}"
        result.append((card.id, name))
    return result


# Regex to extract mask data-attributes from cloze/cloze-inactive/cloze-highlight divs
_MASK_RE = re.compile(
    r'<div\s+class="cloze(?:-inactive|-highlight)?"\s+'
    r'(data-(?:ordinal|shape|left|top|width|height|rx|ry|angle|points|fill)="[^"]*"\s*)+',
    re.DOTALL,
)
_ATTR_RE = re.compile(r'data-(ordinal|shape|left|top|width|height|rx|ry|angle|points|fill)="([^"]*)"')
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
