"""Card state classification, countdown formatting, filtering, sorting, and theme color helpers.

Determines the visual state of a card (new, learn, review-due, etc.)
based on its queue/type/due metadata, and provides the corresponding
badge HTML, CSS color variables, and bulk filter/sort operations.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from html import escape as _esc

from anki.consts import (
    CARD_TYPE_NEW,
    CARD_TYPE_LRN,
    CARD_TYPE_RELEARNING,
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_LRN,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_DAY_LEARN_RELEARN,
    QUEUE_TYPE_SUSPENDED,
    QUEUE_TYPE_MANUALLY_BURIED,
    QUEUE_TYPE_SIBLING_BURIED,
)

# ── Filter chip names → internal state strings ──
# Used by the UI filter chips.
FILTER_CHIP_STATES: dict[str, list[str]] = {
    "new": ["new"],
    "learning": ["learn"],
    "due": ["review-due"],
    "upcoming": ["review-soon", "review-mid", "review-later"],
    "suspended": [],  # special: matches queue == QUEUE_TYPE_SUSPENDED
}

# ── SVG icons for the state badge ──

STATE_ICONS = {
    "new": (
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">'
        '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 '
        '3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>'
    ),
    "learn": (
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
        'stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>'
    ),
    "review": (
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
        'stroke-linejoin="round"><circle cx="12" cy="12" r="10"/>'
        '<path d="M12 6v6l4 2"/></svg>'
    ),
}

STATE_PRIORITY = {
    "learn": 6, "review-due": 5, "review-soon": 4,
    "review-mid": 3, "review-later": 2, "new": 1, "": 0,
}


def card_state_from_meta(meta: dict, today: int = 0) -> str:
    """Return the card's visual state string.

    Review cards are split into sub-states based on days until due:
      'review-due'   — due today or overdue
      'review-soon'  — due in 1-3 days
      'review-mid'   — due in 4-14 days
      'review-later'  — due in 15+ days
    """
    q = meta["queue"]
    if q == QUEUE_TYPE_SUSPENDED or q in (QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED):
        return ""
    if q == QUEUE_TYPE_NEW or meta["type"] == CARD_TYPE_NEW:
        return "new"
    if q in (QUEUE_TYPE_LRN, QUEUE_TYPE_DAY_LEARN_RELEARN) or meta["type"] in (CARD_TYPE_LRN, CARD_TYPE_RELEARNING):
        return "learn"
    # Review card — determine urgency sub-state
    days = meta["due"] - today if today else 0
    if days <= 0:
        return "review-due"
    if days <= 3:
        return "review-soon"
    if days <= 14:
        return "review-mid"
    return "review-later"


def card_countdown_from_meta(meta: dict, today: int) -> str:
    """Return a succinct countdown string from a metadata row dict."""
    q = meta["queue"]
    if q in (QUEUE_TYPE_NEW, QUEUE_TYPE_SUSPENDED, QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED):
        return ""
    if q == QUEUE_TYPE_LRN:
        secs = int(meta["due"] - time.time())
        return _fmt_seconds(secs) if secs > 0 else ""
    if q in (QUEUE_TYPE_REV, QUEUE_TYPE_DAY_LEARN_RELEARN):
        days = meta["due"] - today
        if days <= 0:
            return "Due"
        return _fmt_days(days)
    return ""


def _fmt_seconds(secs: int) -> str:
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return _fmt_days(secs // 86400)


def _fmt_days(days: int) -> str:
    if days <= 0:
        return ""
    if days == 1:
        return "1 day"
    if days < 30:
        return f"{days} days"
    if days < 365:
        mo = days // 30
        return f"{mo} mo"
    yr = days // 365
    return f"{yr} yr"


def build_state_badge(state: str, countdown: str) -> str:
    """Build the HTML for the state badge shown in the card corner."""
    if not state:
        return ""
    # Review sub-states all share the 'review' icon
    icon_key = "review" if state.startswith("review") else state
    icon = STATE_ICONS.get(icon_key, "")
    text = f'<span class="card-state-text">{_esc(countdown)}</span>' if countdown else ""
    return f'<span class="card-state-badge"><span class="card-state-icon">{icon}</span>{text}</span>'


def get_state_colors() -> dict[str, str]:
    """Return a dict of CSS variable values for state colors, including bg variants."""
    try:
        from aqt import colors as c
        from aqt.theme import theme_manager as tm
        new_hex = tm.var(c.STATE_NEW)
        learn_hex = tm.var(c.STATE_LEARN)
        review_hex = tm.var(c.STATE_REVIEW)
    except Exception:
        new_hex, learn_hex, review_hex = "#3b82f6", "#dc2626", "#16a34a"

    def _hex_to_rgba(h: str, alpha: float) -> str:
        h = h.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    return {
        "--state-new-color": new_hex,
        "--state-learn-color": learn_hex,
        "--state-review-color": review_hex,
        "--state-review-70": _hex_to_rgba(review_hex, 0.70),
        "--state-review-50": _hex_to_rgba(review_hex, 0.50),
        "--state-review-30": _hex_to_rgba(review_hex, 0.30),
        "--state-new-bg": _hex_to_rgba(new_hex, 0.12),
        "--state-learn-bg": _hex_to_rgba(learn_hex, 0.12),
        "--state-review-bg": _hex_to_rgba(review_hex, 0.12),
        "--state-review-soon-bg": _hex_to_rgba(review_hex, 0.08),
        "--state-review-mid-bg": _hex_to_rgba(review_hex, 0.06),
        "--state-review-later-bg": _hex_to_rgba(review_hex, 0.04),
    }


# ── Bulk filtering by state ──

def filter_cards_by_states(
    meta: dict[int, dict],
    today: int,
    active_chips: set[str],
) -> set[int]:
    """Return the set of card IDs that match any of the active filter chip names.

    active_chips is a set of keys from FILTER_CHIP_STATES (e.g. {"new", "due"}).
    An empty set means "show all" (no filtering).
    """
    if not active_chips:
        return set(meta.keys())

    # Expand chip names into allowed state strings
    allowed_states: set[str] = set()
    include_suspended = "suspended" in active_chips
    for chip in active_chips:
        if chip in FILTER_CHIP_STATES:
            allowed_states.update(FILTER_CHIP_STATES[chip])

    result: set[int] = set()
    for cid, m in meta.items():
        is_susp = m["queue"] == QUEUE_TYPE_SUSPENDED
        if include_suspended and is_susp:
            result.add(cid)
            continue
        if not include_suspended and is_susp:
            # When suspended chip is not active, suspended cards are still
            # shown (they're visually dimmed). But if *any* state chip is
            # active, only show suspended cards if "suspended" is toggled.
            continue
        state = card_state_from_meta(m, today)
        if state in allowed_states:
            result.add(cid)
    return result


# ── Sorting ──

SORT_KEYS = [
    "deck", "due", "state", "sort_field", "ease", "interval",
    "lapses", "reps", "created", "modified",
]


def sort_cards(
    card_ids: Sequence[int],
    meta: dict[int, dict],
    today: int,
    sort_key: str,
    reverse: bool = False,
) -> list[int]:
    """Return card_ids sorted according to sort_key.

    When reverse=False (default):
      'deck'       — original order (no-op).
      'due'        — soonest due first; new cards last.
      'state'      — most urgent first.
      'sort_field'  — alphabetical A→Z.
      'ease'       — lowest first (struggling).
      'interval'   — shortest first (youngest).
      'lapses'     — most failed first.
      'reps'       — most reviewed first.
      'created'    — newest first.
      'modified'   — recently changed first.

    When reverse=True the order is flipped.
    """
    if sort_key == "deck" or sort_key not in SORT_KEYS:
        return list(reversed(card_ids)) if reverse else list(card_ids)

    if sort_key == "due":
        def due_key(cid: int) -> tuple[int, int]:
            m = meta.get(cid)
            if not m:
                return (1, 0)
            if m["queue"] == QUEUE_TYPE_NEW or m["type"] == CARD_TYPE_NEW:
                return (1, cid)
            return (0, m["due"])
        return sorted(card_ids, key=due_key, reverse=reverse)

    if sort_key == "state":
        def state_key(cid: int) -> int:
            m = meta.get(cid)
            if not m:
                return 0
            st = card_state_from_meta(m, today)
            return -STATE_PRIORITY.get(st, 0)
        return sorted(card_ids, key=state_key, reverse=reverse)

    if sort_key == "sort_field":
        def sfld_key(cid: int) -> str:
            m = meta.get(cid)
            return (m.get("sfld") or "").lower() if m else ""
        return sorted(card_ids, key=sfld_key, reverse=reverse)

    if sort_key == "ease":
        def ease_key(cid: int) -> int:
            m = meta.get(cid)
            return m["factor"] if m else 0
        return sorted(card_ids, key=ease_key, reverse=reverse)

    if sort_key == "interval":
        def ivl_key(cid: int) -> int:
            m = meta.get(cid)
            return m["ivl"] if m else 0
        return sorted(card_ids, key=ivl_key, reverse=reverse)

    if sort_key == "lapses":
        def lapses_key(cid: int) -> int:
            m = meta.get(cid)
            return -(m["lapses"] if m else 0)
        return sorted(card_ids, key=lapses_key, reverse=reverse)

    if sort_key == "reps":
        def reps_key(cid: int) -> int:
            m = meta.get(cid)
            return -(m["reps"] if m else 0)
        return sorted(card_ids, key=reps_key, reverse=reverse)

    if sort_key == "created":
        return sorted(card_ids, reverse=not reverse)

    if sort_key == "modified":
        def mod_key(cid: int) -> int:
            m = meta.get(cid)
            return -(m["mod"] if m else 0)
        return sorted(card_ids, key=mod_key, reverse=reverse)

    return list(card_ids)


# ── Advanced criteria-based filtering ──

def filter_cards_by_criteria(
    meta: dict[int, dict],
    criteria: dict,
) -> set[int]:
    """Filter cards by advanced criteria dict.

    Supported keys (all optional):
      flag       — int, exact flag match (1-7). 0 or absent = any flag.
      min_ease   — int, minimum ease factor (permille, e.g. 1500 = 150%).
      max_ease   — int, maximum ease factor.
      min_ivl    — int, minimum interval in days.
      max_ivl    — int, maximum interval in days.
      min_lapses — int, minimum lapse count.
      max_lapses — int, maximum lapse count.
      min_reps   — int, minimum review count.
      max_reps   — int, maximum review count.

    Returns the set of matching card IDs.
    """
    if not criteria:
        return set(meta.keys())

    flag = criteria.get("flag", 0)
    min_ease = criteria.get("min_ease")
    max_ease = criteria.get("max_ease")
    min_ivl = criteria.get("min_ivl")
    max_ivl = criteria.get("max_ivl")
    min_lapses = criteria.get("min_lapses")
    max_lapses = criteria.get("max_lapses")
    min_reps = criteria.get("min_reps")
    max_reps = criteria.get("max_reps")

    result: set[int] = set()
    for cid, m in meta.items():
        if flag and m.get("flags", 0) != flag:
            continue
        f = m.get("factor", 0)
        if min_ease is not None and f < min_ease:
            continue
        if max_ease is not None and f > max_ease:
            continue
        iv = m.get("ivl", 0)
        if min_ivl is not None and iv < min_ivl:
            continue
        if max_ivl is not None and iv > max_ivl:
            continue
        lp = m.get("lapses", 0)
        if min_lapses is not None and lp < min_lapses:
            continue
        if max_lapses is not None and lp > max_lapses:
            continue
        rp = m.get("reps", 0)
        if min_reps is not None and rp < min_reps:
            continue
        if max_reps is not None and rp > max_reps:
            continue
        result.add(cid)
    return result
