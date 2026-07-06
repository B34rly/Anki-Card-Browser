"""Card mutations behind the tray's menus, detail overlay, and drag-drop.

Each helper applies (or prompts for, then applies) one mutation and reports
what happened; CardTray decides how to refresh the page afterwards. Nothing
here touches the webview.
"""
from __future__ import annotations

from anki.cards import CardId
from anki.decks import DeckId
from aqt.qt import QInputDialog, QMessageBox

from ..core.card_data import get_cards_metadata, get_note_cards, get_tags_for_cards

# Bridge actions handled by apply_card_action (plus any "flag_N").
CARD_ACTIONS = (
    "suspend", "unsuspend", "review_now", "bury", "unbury", "forget",
    "set_due", "reposition", "add_tag", "remove_tag", "change_deck",
)


def apply_scheduling_action(parent, col, action: str, cids) -> bool:
    """Apply a flag/scheduling action to *cids*; True when something changed.

    set_due and reposition prompt first; a cancelled prompt changes nothing.
    """
    if action.startswith("flag_"):
        col.set_user_flag_for_cards(int(action[5:]), cids)
    elif action == "suspend":
        col.sched.suspend_cards(cids)
    elif action == "unsuspend":
        col.sched.unsuspend_cards(cids)
    elif action == "review_now":
        col.sched.set_due_date(cids, "0")
    elif action == "bury":
        col.sched.bury_cards(cids)
    elif action == "unbury":
        col.sched.unbury_cards(cids)
    elif action == "forget":
        col.sched.schedule_cards_as_new(cids)
    elif action == "set_due":
        spec, ok = QInputDialog.getText(
            parent, "Set Due Date",
            "Days from today (e.g. 0, 3, 1-7), or a date (YYYY-MM-DD):",
        )
        spec = spec.strip()
        if not ok or not spec:
            return False
        try:
            col.sched.set_due_date(cids, spec)
        except Exception as e:
            QMessageBox.warning(parent, "Set Due Date Failed", str(e))
            return False
    elif action == "reposition":
        pos, ok = QInputDialog.getInt(
            parent, "Reposition New Cards", "New position:", 1, 0, 9999999
        )
        if not ok:
            return False
        try:
            col.sched.reposition_new_cards(cids, pos, 1, False, False)
        except Exception as e:
            QMessageBox.warning(parent, "Reposition Failed", str(e))
            return False
    else:
        return False
    return True


def prompt_tag_action(parent, col, action: str, cids) -> dict[int, list[int]] | None:
    """Prompt for and apply an add/remove tag on the note(s) behind *cids*.

    Returns nid → [cids] for every affected note (tags show on every card of
    a note, so the caller refreshes each), or None when nothing changed.
    """
    from anki.notes import NoteId

    card_ids = [int(c) for c in cids]
    note_cards = get_note_cards(
        col, list({m["nid"] for m in get_cards_metadata(col, card_ids).values()})
    )
    note_ids = [NoteId(n) for n in note_cards]
    if not note_ids:
        return None
    if action == "add_tag":
        tag, ok = QInputDialog.getText(
            parent, "Add Tag", "Tag(s) to add (space-separated):"
        )
        tag = tag.strip()
        if not ok or not tag:
            return None
        col.tags.bulk_add(note_ids, tag)
    else:
        current = set(get_tags_for_cards(col, card_ids))
        if not current:
            QMessageBox.information(parent, "Remove Tag", "There are no tags to remove.")
            return None
        tag, ok = QInputDialog.getItem(
            parent, "Remove Tag", "Tag to remove:",
            sorted(current, key=str.lower), 0, False,
        )
        if not ok or not tag:
            return None
        col.tags.bulk_remove(note_ids, tag)
    return note_cards


def prompt_change_deck(parent, col, cids) -> int | None:
    """Prompt for a target deck for *cids*; returns its id or None."""
    choices = [d.name for d in col.decks.all_names_and_ids(include_filtered=False)]
    choices.sort(key=str.lower)
    if not choices:
        return None
    try:
        cur_name = col.decks.name(col.get_card(cids[0]).did)
    except Exception:
        cur_name = ""
    start = choices.index(cur_name) if cur_name in choices else 0
    name, ok = QInputDialog.getItem(
        parent, "Change Deck", "Move to deck:", choices, start, False
    )
    if not ok or not name:
        return None
    did = col.decks.id(name)
    return int(did) if did is not None else None


def resolve_normal_deck(col, deck_id: int):
    """The deck for *deck_id*, or None when missing or filtered (dyn).

    Cards can't live in a filtered deck — moving them there directly would
    corrupt scheduling, so move targets must be normal decks.
    """
    try:
        deck = col.decks.get(DeckId(deck_id), default=False)
    except Exception:  # newer Anki raises NotFoundError for unknown ids
        return None
    if not deck or deck.get("dyn"):
        return None
    return deck


def move_cards(col, cids, deck_id: int) -> bool:
    """Move exactly *cids* to *deck_id*; True when the move was applied."""
    if resolve_normal_deck(col, deck_id) is None:
        return False
    col.set_deck([CardId(int(c)) for c in cids], DeckId(deck_id))
    return True


def confirm_delete(parent, count: int) -> bool:
    """Ask before deleting *count* card(s); True to proceed."""
    label = f"{count} cards" if count > 1 else "this card"
    confirm = QMessageBox.question(
        parent, "Delete Card",
        f"Are you sure you want to delete {label}?\n\nThis cannot be undone.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return confirm == QMessageBox.StandardButton.Yes
