"""The deck side of the browser: tree queries, mutations, sidebar widget.

data: pure helpers over col.decks (used by the viewer's deck dropdown).
ops: prompt-driven deck mutations shared by the sidebar and tray menus.
sidebar: the DeckTree navigation widget.
"""
from .data import find_deck_node, get_top_level_decks
from .sidebar import DeckTree

__all__ = ["DeckTree", "find_deck_node", "get_top_level_decks"]
