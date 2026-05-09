"""Note-level grouping and summarisation for notes display mode.

Groups cards by their parent note, computes per-note state summaries,
and provides aggregate counts for section/title headers.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from .card_data import get_cards_metadata, is_io_mid
from .card_state import (
    card_state_from_meta,
    card_countdown_from_meta,
    STATE_PRIORITY,
)


class NoteGroup(NamedTuple):
    nid: int
    mid: int
    cids: list[int]
    is_io: bool


def group_cards_by_note(col, card_ids: Sequence[int]) -> list[NoteGroup]:
    """Group card IDs by their parent note, preserving first-card order.

    Returns an ordered list of NoteGroup tuples. IO notes are flagged
    so the caller can use existing IO rendering.
    """
    if not card_ids:
        return []

    meta = get_cards_metadata(col, card_ids)

    seen: dict[int, list[int]] = {}
    mid_map: dict[int, int] = {}
    order: list[int] = []

    for cid in card_ids:
        m = meta.get(cid)
        if m is None:
            continue
        nid = m["nid"]
        mid = m["mid"]
        if nid not in seen:
            seen[nid] = [cid]
            mid_map[nid] = mid
            order.append(nid)
        else:
            seen[nid].append(cid)

    return [
        NoteGroup(
            nid=nid,
            mid=mid_map[nid],
            cids=seen[nid],
            is_io=is_io_mid(col, mid_map[nid]),
        )
        for nid in order
    ]


def note_state_summary(meta: dict[int, dict], cids: list[int], today: int) -> dict:
    """Compute state summary for a note's cards.

    Returns dict with keys: total, new, learn, due, upcoming, suspended,
    dominant_state, dominant_countdown, all_suspended.
    """
    from anki.consts import QUEUE_TYPE_SUSPENDED

    counts = {"total": 0, "new": 0, "learn": 0, "due": 0, "upcoming": 0, "suspended": 0}
    dominant_state = ""
    dominant_countdown = ""

    for cid in cids:
        m = meta.get(cid)
        if m is None:
            continue
        counts["total"] += 1

        if m.get("queue") == QUEUE_TYPE_SUSPENDED:
            counts["suspended"] += 1
            continue

        st = card_state_from_meta(m, today)
        if st == "new":
            counts["new"] += 1
        elif st == "learn":
            counts["learn"] += 1
        elif st == "review-due":
            counts["due"] += 1
        elif st in ("review-soon", "review-mid", "review-later"):
            counts["upcoming"] += 1

        if STATE_PRIORITY.get(st, 0) > STATE_PRIORITY.get(dominant_state, 0):
            dominant_state = st
            dominant_countdown = card_countdown_from_meta(m, today)

    return {
        **counts,
        "dominant_state": dominant_state,
        "dominant_countdown": dominant_countdown,
        "all_suspended": counts["suspended"] == counts["total"] and counts["total"] > 0,
    }


def note_summary_counts(meta: dict[int, dict], card_ids: Sequence[int], today: int) -> dict:
    """Aggregate note-level and card-level counts for title/section headers.

    Returns dict with: notes, cards, new, learn, due, upcoming.
    """
    from anki.consts import QUEUE_TYPE_SUSPENDED

    note_nids: set[int] = set()
    total_cards = 0
    new = learn = due = upcoming = 0

    for cid in card_ids:
        m = meta.get(cid)
        if m is None:
            continue
        total_cards += 1
        note_nids.add(m["nid"])

        if m.get("queue") == QUEUE_TYPE_SUSPENDED:
            continue

        st = card_state_from_meta(m, today)
        if st == "new":
            new += 1
        elif st == "learn":
            learn += 1
        elif st == "review-due":
            due += 1
        elif st in ("review-soon", "review-mid", "review-later"):
            upcoming += 1

    return {
        "notes": len(note_nids),
        "cards": total_cards,
        "new": new,
        "learn": learn,
        "due": due,
        "upcoming": upcoming,
    }
