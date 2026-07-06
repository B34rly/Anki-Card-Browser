"""External-change tracking: what did the last render show, what changed since.

ChangeTracker keeps the two per-render snapshots that let the tray answer
"what exactly changed" when Anki only says *that* something changed
(OpChanges carries no ids):

- ``known_cards``: cid → deck id for everything rendered, diffed against the
  live collection to spot adds / removals / moves between sections.
- ``mod_watermark``: epoch-seconds; cards/notes with ``mod`` at or past it
  changed since the last sweep.
"""
from __future__ import annotations

import time


class ChangeTracker:
    def __init__(self) -> None:
        self.known_cards: dict[int, int] = {}
        self.mod_watermark: int = int(time.time())

    def snapshot(self, meta: dict) -> None:
        """Record what a full render is about to show."""
        self.known_cards = {cid: m["did"] for cid, m in meta.items()}
        self.mod_watermark = int(time.time())


    def diff_membership(self, current: dict[int, int]):
        """Diff the live cid→deck map against the snapshot and adopt it.

        Returns (added, removed, moved, previous): sets of cids plus the old
        snapshot (used to find a moved card's source deck).
        """
        previous = self.known_cards
        self.known_cards = current
        added = current.keys() - previous.keys()
        removed = previous.keys() - current.keys()
        moved = {
            c for c in current.keys() & previous.keys()
            if current[c] != previous[c]
        }
        return added, removed, moved, previous

    def consume_modified(self, col, tree_deck_ids: list[int]):
        """In-tree cards/notes modified since the last sweep, then advance.

        Returns ``(card_rows, nids, changed_anywhere)``: ``card_rows`` is
        ``[(cid, nid), …]`` and ``nids`` note ids whose ``mod`` is at or past
        the watermark, restricted to the rendered tree via the indexed
        ``cards.did`` column (no full-table scan on the common path). This
        pinpoints *which* items an external op touched, regardless of where
        the edit came from. ``changed_anywhere`` is False only when the
        *whole collection* has no matching row — the undo signature (undo
        restores old mod times), which callers answer with a full re-render.
        Second-resolution overlap can re-report an item; refreshes are
        idempotent so that is harmless.
        """
        wm = self.mod_watermark
        self.mod_watermark = int(time.time())
        dids = tree_deck_ids
        if not dids or len(dids) > 900:
            # No tree, or too many decks for one IN clause (SQLite parameter
            # limit) — fall back to whole-table sweeps; callers filter by nid.
            cards = col.db.all("SELECT id, nid FROM cards WHERE mod >= ?", wm)
            nids = col.db.list("SELECT id FROM notes WHERE mod >= ?", wm)
            return cards, nids, True
        ph = ",".join("?" * len(dids))
        cards = col.db.all(
            f"SELECT id, nid FROM cards WHERE did IN ({ph}) AND mod >= ?",
            *dids, wm,
        )
        nids = col.db.list(
            f"SELECT id FROM notes WHERE mod >= ? AND id IN "
            f"(SELECT nid FROM cards WHERE did IN ({ph}))",
            wm, *dids,
        )
        if cards or nids:
            return cards, nids, True
        changed = col.db.scalar(
            "SELECT 1 FROM notes WHERE mod >= ? LIMIT 1", wm
        ) or col.db.scalar(
            "SELECT 1 FROM cards WHERE mod >= ? LIMIT 1", wm
        )
        return [], [], bool(changed)
