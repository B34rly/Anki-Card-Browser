from __future__ import annotations

import re
from collections.abc import Sequence
from html import escape as _esc

from anki.cards import CardId
from anki.consts import QUEUE_TYPE_SUSPENDED
from anki.decks import DeckId
from aqt import mw
from aqt.webview import AnkiWebView, AnkiWebViewKind
from aqt.qt import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    pyqtSignal,
)


_TRAY_CSS = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
    margin: 0; padding: 0;
    background: Canvas; color: CanvasText;
}
.card-frame {
    position: relative;
    border: 1px solid color-mix(in srgb, CanvasText 20%, Canvas);
    border-radius: 6px;
    padding: 16px;
    padding-top: 32px;
    margin-bottom: 12px;
    break-inside: avoid;
    cursor: pointer;
    transition: box-shadow 0.15s ease, transform 0.15s ease, opacity 0.15s ease;
}
.card-frame img { max-width: 100%; height: auto; display: block; }
.card-frame:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.18);
    transform: translateY(-2px);
}
.card-frame.suspended { opacity: 0.45; }

/* ── IO grouped card ── */
.io-container { position: relative; display: block; width: 100%; overflow: hidden; line-height: 0; }
.io-container img { display: block; width: 100%; height: auto; }
.io-overlay {
    position: absolute; inset: 0; pointer-events: none;
}
.io-badge {
    display: inline-block; font-size: 11px; color: GrayText;
    background: color-mix(in srgb, CanvasText 10%, Canvas); border-radius: 4px; padding: 1px 6px;
    margin-top: 6px;
}

/* ── 3-dot menu ── */
.card-menu-btn {
    position: absolute; top: 6px; right: 8px;
    background: none; border: none; cursor: pointer;
    font-size: 18px; color: #888; padding: 2px 6px;
    border-radius: 4px; line-height: 1;
}
.card-menu-btn:hover { background: color-mix(in srgb, CanvasText 10%, Canvas); }
.card-menu {
    display: none; position: absolute; top: 28px; right: 8px;
    background: Canvas; color: CanvasText;
    border: 1px solid color-mix(in srgb, CanvasText 25%, Canvas); border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25); z-index: 100;
    min-width: 150px; overflow: hidden;
}
.card-menu.open { display: block; }
.card-menu button {
    display: block; width: 100%; padding: 8px 14px;
    border: none; background: none; text-align: left;
    cursor: pointer; font-size: 13px; color: CanvasText;
}
.card-menu button:hover { background: color-mix(in srgb, CanvasText 10%, Canvas); }

/* ── Overlay for expanded card ── */
#overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.5); z-index: 200;
    justify-content: center; align-items: center;
}
#overlay.open { display: flex; }
#overlay-card {
    background: Canvas; color: CanvasText; border-radius: 10px;
    padding: 24px; max-width: 85vw; max-height: 85vh;
    overflow: auto; position: relative;
}
#overlay-card img { max-width: 100%; height: auto; }
#overlay-close {
    position: absolute; top: 8px; right: 12px;
    font-size: 22px; cursor: pointer; background: none;
    border: none; color: GrayText;
}
#overlay-close:hover { color: CanvasText; }

/* ── Deck sections ── */
.deck-header {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 12px;
    background: color-mix(in srgb, CanvasText 5%, Canvas);
    border-bottom: 1px solid color-mix(in srgb, CanvasText 12%, Canvas);
    cursor: pointer; user-select: none;
}
.deck-header:hover {
    background: color-mix(in srgb, CanvasText 10%, Canvas);
}
.deck-header.highlight {
    background: color-mix(in srgb, Highlight 25%, Canvas);
    transition: background 0.5s;
}
.depth-0 { padding-left: 12px; font-weight: bold; font-size: 15px; }
.depth-1 { padding-left: 28px; font-weight: 600; font-size: 14px; }
.depth-2 { padding-left: 44px; font-size: 13px; }
.depth-3 { padding-left: 60px; font-size: 13px; }
.depth-4 { padding-left: 76px; font-size: 12px; }
.collapse-arrow {
    display: inline-block; font-size: 11px;
    transition: transform 0.2s ease;
}
.collapse-arrow.collapsed { transform: rotate(-90deg); }
.deck-name { flex: 1; min-width: 0; }
.deck-path { color: GrayText; font-size: 0.85em; }
.deck-leaf { font-weight: bold; }
.deck-info { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.card-count {
    color: GrayText; font-size: 12px; white-space: nowrap;
}
.deck-btn {
    padding: 2px 8px; border: 1px solid color-mix(in srgb, CanvasText 20%, Canvas);
    border-radius: 4px; background: Canvas; color: CanvasText;
    font-size: 11px; cursor: pointer; white-space: nowrap;
}
.deck-btn:hover { background: color-mix(in srgb, CanvasText 10%, Canvas); }
.deck-body.collapsed { display: none; }
.deck-cards {
    column-width: 320px; column-gap: 12px;
    padding: 12px;
}
.deck-cards:empty { display: none; }
"""

_TRAY_JS = """\
function toggleMenu(e, id) {
    e.stopPropagation();
    document.querySelectorAll('.card-menu.open').forEach(m => {
        if (m.id !== 'menu-' + id) m.classList.remove('open');
    });
    document.getElementById('menu-' + id).classList.toggle('open');
}
document.addEventListener('click', () => {
    document.querySelectorAll('.card-menu.open').forEach(m => m.classList.remove('open'));
});
function cardAction(e, action, cid) {
    e.stopPropagation();
    document.querySelectorAll('.card-menu.open').forEach(m => m.classList.remove('open'));
    pycmd(action + ':' + cid);
}
function expandCard(el) {
    const overlay = document.getElementById('overlay');
    const inner = document.getElementById('overlay-card-content');
    inner.innerHTML = el.querySelector('.card-content').innerHTML;
    overlay.classList.add('open');
}
function closeOverlay() {
    document.getElementById('overlay').classList.remove('open');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeOverlay(); });

function deckAction(e, action, deckId) {
    e.stopPropagation();
    pycmd(action + ':' + deckId);
}
function toggleSection(deckId) {
    var body = document.getElementById('body-' + deckId);
    var arrow = document.getElementById('arrow-' + deckId);
    if (body) body.classList.toggle('collapsed');
    if (arrow) arrow.classList.toggle('collapsed');
    pycmd('toggle_section:' + deckId);
}
function scrollToSection(deckId) {
    var el = document.querySelector('[data-deck-id="' + deckId + '"]');
    if (!el) return;
    var p = el.parentElement;
    while (p) {
        if (p.classList && p.classList.contains('deck-body') && p.classList.contains('collapsed')) {
            p.classList.remove('collapsed');
            var id = p.id.replace('body-', '');
            var a = document.getElementById('arrow-' + id);
            if (a) a.classList.remove('collapsed');
        }
        p = p.parentElement;
    }
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    var hdr = el.querySelector('.deck-header');
    if (hdr) {
        hdr.classList.add('highlight');
        setTimeout(function(){ hdr.classList.remove('highlight'); }, 1500);
    }
}

/* ── Scroll-spy: track which section header is near the top ── */
(function() {
    var lastId = null;
    var observer = new IntersectionObserver(function(entries) {
        /* Find the topmost visible header */
        var best = null;
        document.querySelectorAll('.deck-header').forEach(function(h) {
            var r = h.getBoundingClientRect();
            if (r.top < window.innerHeight * 0.35) best = h;
        });
        if (!best) return;
        var sec = best.closest('.deck-section');
        if (!sec) return;
        var id = sec.getAttribute('data-deck-id');
        if (id && id !== lastId) {
            lastId = id;
            pycmd('visible_section:' + id);
        }
    }, { threshold: 0 });
    /* Observe all headers once DOM is ready */
    document.querySelectorAll('.deck-header').forEach(function(h) {
        observer.observe(h);
    });
})();
"""

# Regex to extract mask data-attributes from cloze/cloze-inactive/cloze-highlight divs
_MASK_RE = re.compile(
    r'<div\s+class="cloze(?:-inactive|-highlight)?"\s+'
    r'(data-(?:ordinal|shape|left|top|width|height|rx|ry|angle|points|fill)="[^"]*"\s*)+',
    re.DOTALL,
)
_ATTR_RE = re.compile(r'data-(shape|left|top|width|height|rx|ry|angle|points|fill)="([^"]*)"')
_ACTIVE_ORDINAL_RE = re.compile(r'class="cloze"\s+data-ordinal="(\d+)"')
_IMG_RE = re.compile(r'<img\s[^>]*src="([^"]*)"[^>]*/?\s*>')


def _is_image_occlusion_note(col, note_id: int) -> bool:
    """Check if a note uses the Image Occlusion notetype."""
    note = col.get_note(note_id)
    nt = col.models.get(note.mid)
    if nt is None:
        return False
    return "image occlusion" in nt["name"].lower()


def _extract_io_data(answer_html: str) -> tuple[str | None, list[dict]]:
    """Extract the image src and all mask shapes from an IO card's answer HTML."""
    img_match = _IMG_RE.search(answer_html)
    img_src = img_match.group(1) if img_match else None

    masks: list[dict] = []
    for m in _MASK_RE.finditer(answer_html):
        attrs: dict[str, str] = {}
        for a in _ATTR_RE.finditer(m.group(0)):
            attrs[a.group(1)] = a.group(2)
        if "shape" in attrs:
            masks.append(attrs)
    return img_src, masks


def _build_svg_mask(mask: dict, suspended: bool = False) -> str:
    """Build an SVG element for a single mask shape."""
    shape = mask.get("shape", "rect")
    if suspended:
        fill = "rgba(150, 150, 150, 0.5)"
    else:
        fill = "rgba(255, 100, 100, 0.4)"

    if shape == "rect":
        l = float(mask.get("left", 0))
        t = float(mask.get("top", 0))
        w = float(mask.get("width", 0))
        h = float(mask.get("height", 0))
        return f'<rect x="{l}" y="{t}" width="{w}" height="{h}" fill="{fill}" rx="0.005"/>'
    elif shape == "ellipse":
        l = float(mask.get("left", 0))
        t = float(mask.get("top", 0))
        w = float(mask.get("width", 0))
        h = float(mask.get("height", 0))
        cx = l + w / 2
        cy = t + h / 2
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{w / 2}" ry="{h / 2}" fill="{fill}"/>'
    elif shape == "polygon":
        pts = mask.get("points", "")
        svg_pts = " ".join(
            f"{float(x)},{float(y)}"
            for pair in pts.strip().split()
            if len(pair.split(",")) == 2
            for x, y in [pair.split(",")]
        )
        return f'<polygon points="{svg_pts}" fill="{fill}"/>'
    return ""


def _build_io_card_html(
    img_src: str,
    masks: list[dict],
    card_ids: list[int],
    suspended_ordinals: set[str],
    all_suspended: bool,
) -> str:
    """Build a single grouped IO card with image + SVG mask overlay."""
    cls = "card-frame suspended" if all_suspended else "card-frame"
    cids_str = ",".join(str(c) for c in card_ids)
    menu_id = card_ids[0]
    toggle_action = "unsuspend_group" if all_suspended else "suspend_group"
    toggle_label = "Unsuspend all" if all_suspended else "Suspend all"

    svg_shapes = "\n".join(
        _build_svg_mask(m, suspended=m.get("ordinal", "") in suspended_ordinals)
        for m in masks
    )

    return (
        f'<div class="{cls}" onclick="expandCard(this)">'
        f'  <button class="card-menu-btn" onclick="toggleMenu(event,\'{menu_id}\')">&#8942;</button>'
        f'  <div class="card-menu" id="menu-{menu_id}">'
        f'    <button onclick="cardAction(event,\'{toggle_action}\',\'{cids_str}\')">{toggle_label}</button>'
        f'    <button onclick="cardAction(event,\'review_now_group\',\'{cids_str}\')">Review all now</button>'
        f'  </div>'
        f'  <div class="card-content">'
        f'    <div class="io-container">'
        f'      <img src="{img_src}"/>'
        f'      <svg class="io-overlay" viewBox="0 0 1 1" preserveAspectRatio="none">'
        f'        {svg_shapes}'
        f'      </svg>'
        f'    </div>'
        f'    <span class="io-badge">{len(card_ids)} occlusion cards</span>'
        f'  </div>'
        f'</div>'
    )


class CardTray(QWidget):
    """Displays cards in a single AnkiWebView with hover, expand, and menu."""

    # Emits deck_id of the section currently visible at the top of the scroll
    visible_section_changed = pyqtSignal(object)

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)

        self._collapsed_decks: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel(title)
        self._header.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 8px 4px;"
        )
        layout.addWidget(self._header, 0)

        self._web = AnkiWebView(parent=self, kind=AnkiWebViewKind.DEFAULT)
        self._web.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._web.set_bridge_command(self._on_bridge_cmd, self)
        layout.addWidget(self._web, 1)

    @property
    def title(self) -> str:
        return self._header.text()

    @title.setter
    def title(self, value: str):
        self._header.setText(value)

    # ── Bridge commands from JS ──

    def _on_bridge_cmd(self, cmd: str) -> None:
        col = mw.col
        if col is None:
            return
        if ":" not in cmd:
            return
        action, payload = cmd.split(":", 1)

        if action == "visible_section":
            self.visible_section_changed.emit(int(payload))
            return

        # Collapse/expand state — no re-render needed
        if action == "toggle_section":
            deck_id = int(payload)
            self._collapsed_decks.symmetric_difference_update({deck_id})
            return

        if action == "review_due_deck":
            # Open Anki's reviewer filtered to this deck (due cards only)
            deck_id = int(payload)
            deck = col.decks.get(DeckId(deck_id))
            if deck:
                col.decks.set_current(DeckId(deck_id))
                mw.moveToState("review")
            return

        if action == "force_review_deck":
            # Set all cards in the deck to due today, then start review
            deck_id = int(payload)
            cids = col.decks.cids(DeckId(deck_id), children=True)
            if cids:
                col.sched.set_due_date([CardId(c) for c in cids], "0")
                col.decks.set_current(DeckId(deck_id))
                mw.moveToState("review")
            return

        if action in ("suspend", "unsuspend", "review_now"):
            cid = CardId(int(payload))
            if action == "suspend":
                col.sched.suspend_cards([cid])
            elif action == "unsuspend":
                col.sched.unsuspend_cards([cid])
            elif action == "review_now":
                col.sched.set_due_date([cid], "0")
        elif action in ("suspend_group", "unsuspend_group", "review_now_group"):
            cids = [CardId(int(c)) for c in payload.split(",") if c]
            if action == "suspend_group":
                col.sched.suspend_cards(cids)
            elif action == "unsuspend_group":
                col.sched.unsuspend_cards(cids)
            elif action == "review_now_group":
                col.sched.set_due_date(cids, "0")

        if self._tree_root is not None:
            self.set_deck_tree(self._tree_root, self._tree_name)
        elif self._current_card_ids is not None:
            self.set_cards(self._current_card_ids)

    # ── Render ──

    _current_card_ids: Sequence[int] | None = None
    _tree_root = None
    _tree_name: str = ""

    def set_deck_tree(self, root_node, root_name: str) -> None:
        """Render all subdecks as collapsible sections in one webview."""
        self._tree_root = root_node
        self._tree_name = root_name
        self._current_card_ids = None

        col = mw.col
        if col is None:
            self._web.stdHtml("<p>No collection loaded.</p>")
            return

        all_cids = col.decks.cids(DeckId(root_node.deck_id), children=True)
        self.title = f"{root_name}  ({len(all_cids)} cards)"

        # Root deck's own cards at the top (the header label already names the deck)
        root_own = col.decks.cids(DeckId(root_node.deck_id), children=False)
        root_cards = self._build_cards_html(col, root_own) if root_own else ""

        child_sections = ""
        for child in root_node.children:
            child_path = f"{root_name}::{child.name}"
            child_sections += self._build_section(col, child, full_path=child_path, depth=0)

        body = ""
        if root_cards:
            body += f'<div class="deck-cards">{root_cards}</div>'
        body += child_sections

        self._render_page(body)

    @staticmethod
    def _format_deck_path(full_path: str) -> str:
        """Return a truncated path-style label with the leaf part bolded."""
        parts = full_path.split("::")
        leaf = _esc(parts[-1])
        if len(parts) <= 2:
            prefix_parts = [_esc(p) for p in parts[:-1]]
        else:
            # total chars in last 3 parts (including separators)
            tail3 = parts[-3:]
            tail2 = parts[-2:]
            if sum(len(p) for p in tail3) + 4 <= 50:  # 2 separators
                prefix_parts = ["..."] + [_esc(p) for p in tail3[:-1]]
            else:
                prefix_parts = ["..."] + [_esc(p) for p in tail2[:-1]]
        prefix = "::".join(prefix_parts)
        if prefix:
            return f'<span class="deck-path">{prefix}::</span><span class="deck-leaf">{leaf}</span>'
        return f'<span class="deck-leaf">{leaf}</span>'

    def _build_section(self, col, node, full_path: str, depth: int) -> str:
        """Recursively build HTML for a collapsible deck section."""
        deck_id = node.deck_id
        own_cids = col.decks.cids(DeckId(deck_id), children=False)
        all_cids = col.decks.cids(DeckId(deck_id), children=True)

        cards_html = self._build_cards_html(col, own_cids) if own_cids else ""

        children_html = ""
        for child in node.children:
            child_path = f"{full_path}::{child.name}"
            children_html += self._build_section(col, child, full_path=child_path, depth=depth + 1)

        if not own_cids and not children_html:
            return ""

        collapsed = deck_id in self._collapsed_decks
        arrow_cls = "collapse-arrow collapsed" if collapsed else "collapse-arrow"
        body_cls = "deck-body collapsed" if collapsed else "deck-body"
        name_html = self._format_deck_path(full_path)
        d = min(depth, 4)

        return (
            f'<div class="deck-section" data-deck-id="{deck_id}">'
            f'<div class="deck-header depth-{d}" onclick="toggleSection({deck_id})">'
            f'<span class="{arrow_cls}" id="arrow-{deck_id}">\u25bc</span>'
            f'<span class="deck-name">{name_html}</span>'
            f'<span class="deck-info">'
            f'<span class="card-count">{len(all_cids)} cards</span>'
            f'<button class="deck-btn" onclick="deckAction(event,\'review_due_deck\',{deck_id})">Review due</button>'
            f'<button class="deck-btn" onclick="deckAction(event,\'force_review_deck\',{deck_id})">Force review all</button>'
            f'</span>'
            f'</div>'
            f'<div class="{body_cls}" id="body-{deck_id}">'
            f'<div class="deck-cards">{cards_html}</div>'
            f'{children_html}'
            f'</div>'
            f'</div>'
        )

    def _build_cards_html(self, col, card_ids: Sequence[int]) -> str:
        """Build card HTML fragments for a list of card IDs (with IO grouping)."""
        if not card_ids:
            return ""

        note_groups: dict[int, list[int]] = {}
        io_notes: set[int] = set()
        order: list[tuple[str, int]] = []

        for cid in card_ids:
            card = col.get_card(CardId(cid))
            nid = card.nid
            if _is_image_occlusion_note(col, nid):
                io_notes.add(nid)
                if nid not in note_groups:
                    note_groups[nid] = []
                    order.append(("note", nid))
                note_groups[nid].append(cid)
            else:
                order.append(("card", cid))

        parts: list[str] = []
        for kind, eid in order:
            if kind == "note":
                parts.append(self._build_io_group(col, note_groups[eid]))
            else:
                parts.append(self._build_normal_card(col, eid))

        return "\n".join(parts)

    def _build_io_group(self, col, group_cids: list[int]) -> str:
        """Build HTML for a group of IO cards sharing the same note."""
        first_card = col.get_card(CardId(group_cids[0]))
        answer_html = first_card.answer()
        img_src, masks = _extract_io_data(answer_html)

        if not img_src or not masks:
            all_masks: list[dict] = []
            found_src = img_src
            for gcid in group_cids:
                gc = col.get_card(CardId(gcid))
                src, ms = _extract_io_data(gc.answer())
                if src and not found_src:
                    found_src = src
                all_masks.extend(ms)
            if found_src and all_masks:
                img_src, masks = found_src, all_masks

        if img_src and masks:
            suspended_ords: set[str] = set()
            all_susp = True
            for gcid in group_cids:
                gc = col.get_card(CardId(gcid))
                is_susp = gc.queue == QUEUE_TYPE_SUSPENDED
                if not is_susp:
                    all_susp = False
                q_html = gc.question()
                m = _ACTIVE_ORDINAL_RE.search(q_html)
                if m and is_susp:
                    suspended_ords.add(m.group(1))
            return _build_io_card_html(
                img_src, masks, group_cids, suspended_ords, all_susp
            )
        else:
            return self._build_normal_card(col, group_cids[0])

    def scroll_to_deck(self, deck_id: int) -> None:
        """Scroll the webview to a specific deck section."""
        self._web.eval(f"scrollToSection({deck_id})")

    def _render_page(self, body_html: str) -> None:
        """Render the full page with CSS, body content, overlay, and JS."""
        self._web.stdHtml(
            f"<style>{_TRAY_CSS}</style>"
            f"{body_html}"
            f'<div id="overlay" onclick="closeOverlay()">'
            f'  <div id="overlay-card" onclick="event.stopPropagation()">'
            f'    <button id="overlay-close" onclick="closeOverlay()">&times;</button>'
            f'    <div id="overlay-card-content"></div>'
            f'  </div>'
            f'</div>'
            f"<script>{_TRAY_JS}</script>",
            context=self,
        )

    def set_cards(self, card_ids: Sequence[int]) -> None:
        """Render a flat list of cards (legacy single-deck view)."""
        self._current_card_ids = card_ids
        self._tree_root = None
        col = mw.col
        if col is None:
            self._web.stdHtml("<p>No collection loaded.</p>")
            return
        if not card_ids:
            self._web.stdHtml("<p>No cards in this deck.</p>")
            return

        body = f'<div class="deck-cards">{self._build_cards_html(col, card_ids)}</div>'
        self._render_page(body)

    @staticmethod
    def _build_normal_card(col, cid: int) -> str:
        card = col.get_card(CardId(cid))
        suspended = card.queue == QUEUE_TYPE_SUSPENDED
        cls = "card-frame suspended" if suspended else "card-frame"
        toggle_label = "Unsuspend" if suspended else "Suspend"
        toggle_action = "unsuspend" if suspended else "suspend"
        answer_html = card.answer()
        return (
            f'<div class="{cls}" onclick="expandCard(this)">'
            f'  <button class="card-menu-btn" onclick="toggleMenu(event,{cid})">&#8942;</button>'
            f'  <div class="card-menu" id="menu-{cid}">'
            f'    <button onclick="cardAction(event,\'{toggle_action}\',{cid})">{toggle_label}</button>'
            f'    <button onclick="cardAction(event,\'review_now\',{cid})">Review now</button>'
            f'  </div>'
            f'  <div class="card-content">{answer_html}</div>'
            f'</div>'
        )

    def cleanup(self) -> None:
        self._web.cleanup()
