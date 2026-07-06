"""Filter/sort state and the per-render filter pass."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..core.card_data import (
    filter_cards_by_tag,
    search_cards_by_content,
    search_cards_with_anki_query,
)
from ..core.card_state import (
    filter_cards_by_criteria,
    filter_cards_by_states,
    sort_cards,
)


@dataclass
class FilterState:
    """The toolbar's filter/sort settings (set via CardTray.set_filters)."""

    search_text: str = ""
    active_chips: set[str] = field(default_factory=set)
    tag_filter: str = ""
    sort_key: str = "deck"
    sort_reverse: bool = False
    criteria: dict = field(default_factory=dict)

    @property
    def active(self) -> bool:
        """True when any content/tag/state/criteria filter is set."""
        return bool(
            self.search_text or self.active_chips
            or self.tag_filter or self.criteria
        )


def compute_allowed(
    col, card_ids: Sequence[int], meta, today, filters: FilterState
) -> set[int] | None:
    """Card ids from *card_ids* passing the active filters.

    Returns None when no filters are active (= everything allowed), so a
    full render computes this once for the whole subtree and each section
    just intersects its own ids — no per-section SQL. *meta* must cover
    *card_ids*. Sorting is separate (order_cids), applied per section.
    """
    if not filters.active:
        return None
    cids = list(card_ids)
    if filters.search_text:
        # Known-keyword colon queries run through Anki's own search syntax
        # (tag:/is:/flag:/prop:/…) scoped to the subtree; anything else is a
        # plain substring match over the note fields.
        anki_hits = search_cards_with_anki_query(col, cids, filters.search_text)
        if anki_hits is not None:
            cids = anki_hits
        else:
            cids = search_cards_by_content(col, cids, filters.search_text)
    if filters.tag_filter:
        cids = filter_cards_by_tag(col, cids, filters.tag_filter)
    allowed = set(cids)
    if filters.active_chips:
        allowed &= filter_cards_by_states(meta, today, filters.active_chips)
    if filters.criteria:
        allowed &= filter_cards_by_criteria(meta, filters.criteria)
    return allowed


def order_cids(cids: list[int], meta, today, filters: FilterState) -> list[int]:
    """Apply the active sort to *cids* (deck order + ascending is a no-op)."""
    if filters.sort_key != "deck" or filters.sort_reverse:
        return sort_cards(cids, meta, today, filters.sort_key, filters.sort_reverse)
    return cids
