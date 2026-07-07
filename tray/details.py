"""Detail-overlay HTML for single cards, IO groups, and note groups.

Pure builders: they read the collection and return HTML strings; CardTray
decides when to push them into the overlay (see tray.py's detail
orchestration).
"""
from __future__ import annotations

import time
from html import escape as _esc

from anki.cards import CardId
from anki.consts import (
    QUEUE_TYPE_SUSPENDED, QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED,
)
from anki.decks import DeckId

from ..core.card_data import (
    get_card_template_names,
    get_cards_metadata,
    get_note_fields,
)
from ..rendering import (
    build_detail_actions,
    build_detail_html,
    build_editable_fields,
    build_io_container,
    build_note_fields_table,
    build_qa_content,
    build_revlog_table,
)
from ..core.card_state import (
    card_countdown_from_meta,
    card_state_from_meta,
    group_flag,
)
from ..core.note_grouping import note_state_summary
from .builder import cards_state_summary, extract_group_io, io_suspended_ordinals


def _fmt_date(secs: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(secs))


def _due_text(card, state: str, countdown: str, today: int) -> str:
    """Human-readable due description for the detail stats."""
    if card.queue == QUEUE_TYPE_SUSPENDED:
        return "Suspended"
    if card.queue in (QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED):
        return "Buried"
    if state == "new":
        return f"New · position {card.due}"
    if state == "learn":
        return countdown or "Learning"
    date = _fmt_date(time.time() + (card.due - today) * 86400)
    return f"{date} ({countdown})" if countdown else date


def _template_name(nt, ord_: int) -> str:
    """Template name for a card ordinal (cloze ordinals share one template)."""
    try:
        if nt and nt.get("type") == 1:  # cloze notetype
            return f"{nt['tmpls'][0]['name']} {ord_ + 1}"
        return nt["tmpls"][ord_]["name"]
    except Exception:
        return f"Card {ord_ + 1}"


def _group_stats(note, summary: dict) -> list[tuple[str, str]]:
    """Shared stats rows for IO-group and note-group details."""
    return [
        ("Cards", str(summary["total"])),
        ("States", f"{summary['new']}N · {summary['learn']}L · "
                   f"{summary['due']}D · {summary['upcoming']}U"),
        ("Suspended", str(summary["suspended"])),
        ("Created", _fmt_date(note.id / 1000)),
        ("Modified", _fmt_date(note.mod)),
    ]


def build_card_detail(col, cid: int) -> str:
    """Detail-overlay HTML for a single (non-grouped) card."""
    card = col.get_card(CardId(cid))
    note = card.note()
    today = col.sched.today
    m = {"queue": card.queue, "type": card.type, "due": card.due}
    state = card_state_from_meta(m, today)
    countdown = card_countdown_from_meta(m, today)
    suspended = card.queue == QUEUE_TYPE_SUSPENDED
    buried = card.queue in (QUEUE_TYPE_MANUALLY_BURIED, QUEUE_TYPE_SIBLING_BURIED)

    nt = col.models.get(note.mid)
    nt_name = nt["name"] if nt else "?"

    stats = [
        ("Due", _esc(_due_text(card, state, countdown, today))),
        ("Interval", f"{card.ivl} days" if card.ivl else "–"),
        ("Ease", f"{card.factor / 10:.0f}%" if card.factor else "–"),
        ("Reviews", str(card.reps)),
        ("Lapses", str(card.lapses)),
        ("Created", _fmt_date(cid / 1000)),
        ("Modified", _fmt_date(card.mod)),
    ]
    actions = build_detail_actions(
        str(cid), edit_cid=cid, suspended=suspended, buried=buried,
        can_reposition=(state == "new"), delete_label="Delete card",
    )
    return build_detail_html(
        deck_path=col.decks.name(card.did),
        type_line=f"{nt_name} · {_template_name(nt, card.ord)}",
        state=state, countdown=countdown, flag=card.user_flag(),
        stats=stats, tags=note.tags,
        content_html=build_qa_content(
            card.question(), card.answer(),
            fields_html=build_editable_fields(
                nid=note.id, unit_id=cid,
                fields=get_note_fields(col, note.id),
            ),
        ),
        actions_html=actions,
        history_html=build_revlog_table(_revlog_rows(col, cid)),
    )


def _revlog_rows(col, cid: int, limit: int = 8) -> list[tuple]:
    """The card's most recent reviews, newest first (empty on any db error)."""
    try:
        return col.db.all(
            "select id, ease, ivl, type, time from revlog"
            " where cid = ? order by id desc limit ?",
            cid, limit,
        )
    except Exception:
        return []


def build_io_detail(col, group_cids: list[int]) -> str:
    """Detail-overlay HTML for an Image Occlusion group."""
    cards = [col.get_card(CardId(c)) for c in group_cids]
    lead = cards[0]
    note = lead.note()
    summary = cards_state_summary(cards, col.sched.today)

    img_src, masks = extract_group_io(cards)
    if img_src and masks:
        content = build_io_container(img_src, masks, io_suspended_ordinals(cards))
    else:
        content = lead.answer()

    nt = col.models.get(note.mid)
    cids_str = ",".join(str(c) for c in group_cids)
    actions = build_detail_actions(
        cids_str, edit_cid=lead.id, suspended=summary["all_suspended"],
        buried=summary["all_buried"], can_reposition=False,
        delete_label="Delete cards", inline_edit=False,
    )
    return build_detail_html(
        deck_path=col.decks.name(lead.did),
        type_line=f"{nt['name'] if nt else '?'} · {len(cards)} occlusion cards",
        state=summary["dominant_state"],
        countdown=summary["dominant_countdown"],
        flag=group_flag(gc.user_flag() for gc in cards),
        stats=_group_stats(note, summary),
        tags=note.tags,
        content_html=content,
        actions_html=actions,
    )


def build_note_detail(col, note_groups: dict[int, list[int]], lead_cid: int) -> str:
    """Detail-overlay HTML for a multi-card note group."""
    from anki.notes import NoteId

    group_cids = note_groups.get(lead_cid, [lead_cid])
    meta = get_cards_metadata(col, group_cids)
    today = col.sched.today
    m = meta[lead_cid]
    note = col.get_note(NoteId(m["nid"]))
    summary = note_state_summary(meta, group_cids, today)

    options = "".join(
        f'<option value="{cid}">{_esc(name)}</option>'
        for cid, name in get_card_template_names(col, note.id)
    )
    # The fields ARE the note detail's content: directly editable in edit
    # mode, a read-only table in view mode — never both at once.
    note_fields = get_note_fields(col, note.id)
    content = (
        f"{build_editable_fields(nid=note.id, unit_id=lead_cid, fields=note_fields)}"
        f'<div class="view-only">{build_note_fields_table(note_fields)}</div>'
        f'<select class="overlay-card-select" onchange="onNoteCardSelect(this)">'
        f'<option value="">Preview a card…</option>{options}</select>'
        f'<div class="overlay-card-preview" id="overlay-card-preview"></div>'
    )

    nt = col.models.get(note.mid)
    cids_str = ",".join(str(c) for c in group_cids)
    actions = build_detail_actions(
        cids_str, edit_cid=lead_cid, suspended=summary["all_suspended"],
        buried=summary["all_buried"], can_reposition=False,
        delete_label="Delete note",
    )
    return build_detail_html(
        deck_path=col.decks.name(DeckId(m["did"])),
        type_line=f"{nt['name'] if nt else '?'} · {len(group_cids)} cards",
        state=summary["dominant_state"],
        countdown=summary["dominant_countdown"],
        flag=group_flag(mm.get("flags", 0) for mm in meta.values()),
        stats=_group_stats(note, summary),
        tags=note.tags,
        content_html=content,
        actions_html=actions,
    )
