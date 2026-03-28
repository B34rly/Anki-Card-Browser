from __future__ import annotations

from aqt import mw


def get_leaf_decks() -> list[tuple[int, str]]:
    """Return (deck_id, full_name) for every leaf deck (no children)."""
    col = mw.col
    if col is None:
        return []

    tree = col.decks.deck_tree()
    leaves: list[tuple[int, str]] = []

    def walk(node, parent_path: str = ""):
        name = f"{parent_path}::{node.name}" if parent_path else node.name
        if not node.children:
            if node.deck_id != 0:  # skip the virtual root
                leaves.append((node.deck_id, name))
        for child in node.children:
            walk(child, name)

    # The root node returned by deck_tree() is virtual; iterate its children
    for child in tree.children:
        walk(child, "")
    return leaves


def get_top_level_decks() -> list[tuple[int, str]]:
    """Return (deck_id, name) for each top-level deck."""
    col = mw.col
    if col is None:
        return []
    tree = col.decks.deck_tree()
    return [(child.deck_id, child.name) for child in tree.children]


def find_deck_node(deck_id: int):
    """Find and return the DeckTreeNode for a given deck_id, or None."""
    col = mw.col
    if col is None:
        return None
    tree = col.decks.deck_tree()
    return _find_in_tree(tree, deck_id)


def _find_in_tree(node, deck_id: int):
    if node.deck_id == deck_id:
        return node
    for child in node.children:
        result = _find_in_tree(child, deck_id)
        if result is not None:
            return result
    return None
