"""Card mutations behind the tray's menus, detail overlay, and drag-drop.

Every mutation runs through CollectionOp, so Anki's undo stack and the
`operation_did_execute` hook fire exactly as they do for Anki's own UI —
the tray's op handler then refreshes the page. One pipeline serves our own
changes and external ones alike; nothing here touches the webview.

Helpers prompt where needed, start the op, and report whether an op was
started (False = cancelled prompt / invalid target), so callers know
whether to clear the selection. Success feedback goes through _toast →
CardTray.show_toast (an in-page toast, styled with the browser).
"""
from __future__ import annotations

from anki.cards import CardId
from anki.decks import DeckId
from aqt.operations import CollectionOp
from aqt.qt import QInputDialog, QMessageBox

from ..core.card_data import get_cards_metadata, get_tags_for_cards

# Bridge actions handled by apply_scheduling_action / the tag & deck prompts
# (plus any "flag_N").
CARD_ACTIONS = (
    "suspend", "unsuspend", "review_now", "bury", "unbury", "forget",
    "set_due", "reposition", "add_tag", "remove_tag", "change_deck",
)


def _toast(parent, msg: str) -> None:
    """Success feedback as an in-page toast (*parent* is the CardTray)."""
    try:
        parent.show_toast(msg)
    except Exception:
        pass  # never let feedback break the op's success path


def _start_op(parent, op, msg: str | None = None) -> None:
    """Run *op* through CollectionOp (undo + op hook), toasting on success."""
    collection_op = CollectionOp(parent, op)
    if msg:
        collection_op.success(lambda _res: _toast(parent, msg))
    collection_op.run_in_background(initiator=parent)


def _cards_label(n: int) -> str:
    return f"{n} cards" if n != 1 else "1 card"


def apply_scheduling_action(parent, col, action: str, cids) -> bool:
    """Start the op for a flag/scheduling action.

    Returns True when an op was started (False = cancelled prompt). The
    page refresh arrives via the tray's operation_did_execute handler.
    """
    label = _cards_label(len(cids))
    if action.startswith("flag_"):
        flag = int(action[5:])
        msg = f"Cleared flag on {label}" if flag == 0 else f"Flagged {label}"
        _start_op(parent, lambda c: c.set_user_flag_for_cards(flag, cids), msg)
    elif action == "suspend":
        _start_op(parent, lambda c: c.sched.suspend_cards(cids), f"Suspended {label}")
    elif action == "unsuspend":
        _start_op(parent, lambda c: c.sched.unsuspend_cards(cids), f"Unsuspended {label}")
    elif action == "review_now":
        _start_op(parent, lambda c: c.sched.set_due_date(cids, "0"), f"{label} due now")
    elif action == "bury":
        _start_op(parent, lambda c: c.sched.bury_cards(cids), f"Buried {label}")
    elif action == "unbury":
        _start_op(parent, lambda c: c.sched.unbury_cards(cids), f"Unburied {label}")
    elif action == "forget":
        _start_op(
            parent, lambda c: c.sched.schedule_cards_as_new(cids),
            f"Reset {label} to new",
        )
    elif action == "set_due":
        # Anki's own dialog: validates the spec, remembers the last input,
        # and runs its own CollectionOp.
        from anki.config import Config
        from aqt.operations.scheduling import set_due_date_dialog

        set_due_date_dialog(
            parent=parent, card_ids=cids,
            config_key=Config.String.SET_DUE_BROWSER,
        )
    elif action == "reposition":
        pos, ok = QInputDialog.getInt(
            parent, "Reposition New Cards", "New position:", 1, 0, 9999999
        )
        if not ok:
            return False
        _start_op(
            parent,
            lambda c: c.sched.reposition_new_cards(cids, pos, 1, False, False),
            f"Repositioned {label}",
        )
    else:
        return False
    return True


def prompt_tag_action(parent, col, action: str, cids) -> bool:
    """Prompt for and start an add/remove tag op on the note(s) behind *cids*."""
    from anki.notes import NoteId

    card_ids = [int(c) for c in cids]
    note_ids = [
        NoteId(n)
        for n in {m["nid"] for m in get_cards_metadata(col, card_ids).values()}
    ]
    if not note_ids:
        return False
    n_label = f"{len(note_ids)} notes" if len(note_ids) != 1 else "1 note"
    if action == "add_tag":
        tag, ok = QInputDialog.getText(
            parent, "Add Tag", "Tag(s) to add (space-separated):"
        )
        tag = tag.strip()
        if not ok or not tag:
            return False
        _start_op(
            parent, lambda c: c.tags.bulk_add(note_ids, tag),
            f"Tagged {n_label}",
        )
    else:
        current = set(get_tags_for_cards(col, card_ids))
        if not current:
            QMessageBox.information(parent, "Remove Tag", "There are no tags to remove.")
            return False
        tag, ok = QInputDialog.getItem(
            parent, "Remove Tag", "Tag to remove:",
            sorted(current, key=str.lower), 0, False,
        )
        if not ok or not tag:
            return False
        _start_op(
            parent, lambda c: c.tags.bulk_remove(note_ids, tag),
            f"Untagged {n_label}",
        )
    return True


def undo_redo(parent, redo: bool = False) -> None:
    """Start the undo (or redo) op; the page refresh arrives via the op
    pipeline like any other change. UndoEmpty is swallowed — callers keep
    the buttons disabled in that state anyway, this is just a race guard."""
    from anki.errors import UndoEmpty

    verb = "Redid" if redo else "Undid"

    def op(c):
        return c.redo() if redo else c.undo()

    def on_failure(exc):
        if not isinstance(exc, UndoEmpty):
            QMessageBox.warning(parent, "Undo", str(exc))

    (
        CollectionOp(parent, op)
        .success(lambda out: _toast(parent, f"{verb} {out.operation}"))
        .failure(on_failure)
        .run_in_background(initiator=parent)
    )


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


def move_cards(parent, col, cids, deck_id: int) -> bool:
    """Start the op moving exactly *cids* to *deck_id* (False = bad target)."""
    deck = resolve_normal_deck(col, deck_id)
    if deck is None:
        return False
    card_ids = [CardId(int(c)) for c in cids]
    _start_op(
        parent, lambda c: c.set_deck(card_ids, DeckId(deck_id)),
        f"Moved {_cards_label(len(card_ids))} to {deck['name']}",
    )
    return True


def confirm_delete(parent, count: int) -> bool:
    """Ask before deleting *count* card(s); True to proceed."""
    label = _cards_label(count)
    confirm = QMessageBox.question(
        parent, "Delete Cards",
        f"Delete {label}? (This can be undone with Ctrl+Z.)",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return confirm == QMessageBox.StandardButton.Yes


def delete_cards(parent, col, cids) -> bool:
    """Confirm, then start the op removing card(s) + newly orphaned notes."""
    if not confirm_delete(parent, len(cids)):
        return False
    card_ids = [CardId(int(c)) for c in cids]
    _start_op(
        parent, lambda c: c.remove_cards_and_orphaned_notes(card_ids),
        f"Deleted {_cards_label(len(card_ids))}",
    )
    return True
