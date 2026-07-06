"""Deck mutation flows (prompt → mutate) shared by the sidebar tree and the
card tray's header menus.

Each prompt/confirm helper returns True when the collection actually changed,
so the caller knows to refresh its views.
"""
from __future__ import annotations

from anki.decks import DeckId
from aqt import mw, dialogs
from aqt.qt import QInputDialog, QMessageBox


def open_add_cards(deck_id: int) -> None:
    """Open Anki's Add Cards dialog targeting *deck_id*.

    Routed through Anki's dialog manager (single instance, tracked for
    profile close) rather than instantiating AddCards directly.
    """
    col = mw.col
    if col is None:
        return
    col.decks.set_current(DeckId(deck_id))
    dialogs.open("AddCards", mw)


def prompt_new_subdeck(parent, parent_name: str, title: str = "New Subdeck") -> bool:
    """Prompt for a name and create a subdeck under *parent_name*."""
    col = mw.col
    if col is None:
        return False
    name, ok = QInputDialog.getText(
        parent, title, f"Subdeck name under {parent_name}:"
    )
    if not ok or not name.strip():
        return False
    col.decks.id(f"{parent_name}::{name.strip()}")
    return True


def prompt_rename_deck(parent, deck_id: int) -> bool:
    """Prompt for a new leaf name and rename the deck (its subtree follows)."""
    col = mw.col
    if col is None:
        return False
    deck = col.decks.get(DeckId(deck_id))
    if not deck:
        return False
    full_name = deck["name"]
    leaf = full_name.split("::")[-1]
    new_leaf, ok = QInputDialog.getText(parent, "Rename Deck", "New name:", text=leaf)
    new_leaf = new_leaf.strip()
    if not ok or not new_leaf or new_leaf == leaf:
        return False
    if "::" in new_leaf:
        QMessageBox.warning(parent, "Invalid Name", "A deck name can't contain '::'.")
        return False
    parent_name = "::".join(full_name.split("::")[:-1])
    new_full = f"{parent_name}::{new_leaf}" if parent_name else new_leaf
    try:
        col.decks.rename(DeckId(deck_id), new_full)
    except Exception as e:
        QMessageBox.warning(parent, "Rename Failed", str(e))
        return False
    return True


def confirm_delete_deck(parent, deck_id: int) -> bool:
    """Delete *deck_id* if it is empty (warn otherwise), after confirmation."""
    col = mw.col
    if col is None:
        return False
    deck = col.decks.get(DeckId(deck_id))
    if not deck:
        return False
    deck_name = deck["name"]
    own_cids = col.decks.cids(DeckId(deck_id), children=False)
    children = col.decks.children(DeckId(deck_id))
    if own_cids or children:
        QMessageBox.warning(
            parent, "Cannot Delete",
            f'The deck "{deck_name}" is not empty.\n\n'
            "Move or delete all cards and child subdecks first.",
        )
        return False
    confirm = QMessageBox.question(
        parent, "Delete Deck",
        f'Are you sure you want to delete "{deck_name}"?',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if confirm != QMessageBox.StandardButton.Yes:
        return False
    col.decks.remove([DeckId(deck_id)])
    return True
