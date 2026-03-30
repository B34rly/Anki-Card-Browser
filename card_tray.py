from __future__ import annotations

import json
import re
import time
from collections.abc import Sequence
from html import escape as _esc

from anki.cards import CardId
from anki.consts import (
    CARD_TYPE_NEW,
    CARD_TYPE_LRN,
    CARD_TYPE_REV,
    CARD_TYPE_RELEARNING,
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_LRN,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_DAY_LEARN_RELEARN,
    QUEUE_TYPE_SUSPENDED,
    QUEUE_TYPE_MANUALLY_BURIED,
    QUEUE_TYPE_SIBLING_BURIED,
)
from anki.decks import DeckId
from aqt import mw
from aqt.webview import AnkiWebView, AnkiWebViewKind
from aqt.qt import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    QInputDialog,
    pyqtSignal,
)


_TRAY_CSS = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
    margin: 0; padding: 0;
    background: Canvas; color: CanvasText;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.45;
}

/* ── Card frames ── */
.card-frame {
    position: relative;
    border: 1px solid color-mix(in srgb, CanvasText 14%, Canvas);
    border-radius: 8px;
    padding: 14px;
    padding-top: 34px;
    margin-bottom: 12px;
    break-inside: avoid;
    cursor: pointer;
    overflow: hidden;
    transition: box-shadow 0.2s ease, transform 0.2s ease, opacity 0.15s ease;
    transform-origin: center center;
    content-visibility: auto;
    contain-intrinsic-size: auto 200px;
}
.card-frame img { max-width: 100%; height: auto; display: block; }
.card-frame:hover {
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    transform: scale(1.03);
    z-index: 10;
}
.card-frame:active {
    transform: scale(0.98);
    transition: transform 0.1s ease;
}
.card-frame.suspended { opacity: 0.45; }

/* ── IO grouped card ── */
.io-container { position: relative; display: inline-block; max-width: 100%; overflow: hidden; line-height: 0; }
.io-container img { display: block; max-width: 100%; height: auto; }
.io-container svg { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; }
.io-badge {
    display: inline-block; font-size: 11px; color: GrayText;
    background: color-mix(in srgb, CanvasText 8%, Canvas); border-radius: 4px; padding: 2px 8px;
    margin-top: 8px;
}

/* ── 3-dot menu ── */
.card-menu-btn {
    position: absolute; top: 6px; right: 8px;
    background: none; border: none; cursor: pointer;
    font-size: 18px; color: GrayText; padding: 2px 6px;
    border-radius: 4px; line-height: 1;
    opacity: 0;
    transition: opacity 0.15s ease, background 0.15s ease, color 0.1s ease;
}
.card-frame:hover .card-menu-btn { opacity: 1; }
.card-menu-btn:hover { background: color-mix(in srgb, CanvasText 10%, Canvas); color: CanvasText; }

/* ── Card dropdown menu ── */
.card-menu {
    display: none; position: absolute; top: 30px; right: 8px;
    background: Canvas; color: CanvasText;
    border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas); border-radius: 6px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.18); z-index: 100;
    min-width: 160px; overflow: hidden;
    padding: 4px 0;
}
.card-menu.open { display: block; }
.card-menu button {
    display: block; width: 100%; padding: 7px 14px;
    border: none; background: none; text-align: left;
    cursor: pointer; font-size: 13px; color: CanvasText;
    transition: background 0.1s ease;
}
.card-menu button:hover { background: color-mix(in srgb, CanvasText 8%, Canvas); }

/* ── Overlay for expanded card ── */
#overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0);
    backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px);
    z-index: 200;
    justify-content: center; align-items: center;
    transition: background 0.3s ease, backdrop-filter 0.3s ease, -webkit-backdrop-filter 0.3s ease;
}
#overlay.open { display: flex; }
#overlay.visible {
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
}
#overlay-card {
    background: Canvas; color: CanvasText; border-radius: 12px;
    padding: 28px; max-width: 85vw; max-height: 85vh;
    overflow: auto; position: relative;
    box-shadow: 0 8px 40px rgba(0,0,0,0.3);
    transform: scale(0.9); opacity: 0;
    transition: transform 0.25s ease, opacity 0.25s ease;
}
#overlay.visible #overlay-card {
    transform: scale(1); opacity: 1;
}
#overlay-card img { max-width: 100%; height: auto; }
#overlay-close {
    position: absolute; top: 10px; right: 14px;
    font-size: 22px; cursor: pointer; background: none;
    border: none; color: GrayText;
    transition: color 0.1s ease;
}
#overlay-close:hover { color: CanvasText; }

/* Lock scroll when overlay is open */
body.overlay-open { overflow: hidden; padding-right: var(--scrollbar-w, 0px); }

/* ── Deck sections ── */
.deck-header {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px;
    background: color-mix(in srgb, CanvasText 4%, Canvas);
    border-bottom: 1px solid color-mix(in srgb, CanvasText 10%, Canvas);
    cursor: pointer; user-select: none;
    transition: background 0.15s ease;
    position: sticky; top: 0; z-index: 50;
}
.deck-header:hover {
    background: color-mix(in srgb, CanvasText 8%, Canvas);
}
.deck-header.highlight {
    background: color-mix(in srgb, Highlight 20%, Canvas);
    transition: background 0.5s;
}
.depth-0 { padding-left: 12px; font-weight: 600; font-size: 14px; }
.depth-1 { padding-left: 28px; font-weight: 600; font-size: 13px; }
.depth-2 { padding-left: 44px; font-size: 13px; }
.depth-3 { padding-left: 60px; font-size: 13px; }
.depth-4 { padding-left: 76px; font-size: 12px; }
.collapse-arrow {
    display: inline-block; font-size: 10px;
    transition: transform 0.2s ease;
    color: GrayText;
}
.collapse-arrow.collapsed { transform: rotate(-90deg); }
.deck-name { flex: 1; min-width: 0; }
.deck-path { color: GrayText; font-size: 0.85em; }
.deck-leaf { font-weight: 600; }
.deck-info { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.card-count {
    color: GrayText; font-size: 12px; white-space: nowrap;
}
.deck-btn {
    padding: 3px 10px; border: 1px solid color-mix(in srgb, CanvasText 15%, Canvas);
    border-radius: 4px; background: Canvas; color: CanvasText;
    font-size: 11px; cursor: pointer; white-space: nowrap;
    transition: background 0.1s ease, border-color 0.1s ease;
}
.deck-btn:hover {
    background: color-mix(in srgb, CanvasText 8%, Canvas);
    border-color: color-mix(in srgb, CanvasText 25%, Canvas);
}
.deck-body {
    overflow: visible;
    transition: height 0.3s ease;
}
.deck-body.collapsed {
    overflow: hidden;
}
.deck-cards {
    column-width: 320px; column-gap: 14px;
    padding: 14px;
}
.deck-cards:empty { display: none; }

/* ── Add-card button ── */
.add-card-btn {
    border: 2px dashed color-mix(in srgb, CanvasText 15%, Canvas);
    border-radius: 8px;
    padding: 24px 16px;
    margin-bottom: 12px;
    break-inside: avoid;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 28px; color: color-mix(in srgb, CanvasText 25%, Canvas);
    transition: border-color 0.15s, color 0.15s, background 0.15s,
               opacity 0.25s ease, visibility 0.25s ease;
    user-select: none;
}
.add-card-btn:hover {
    border-color: color-mix(in srgb, CanvasText 40%, Canvas);
    color: color-mix(in srgb, CanvasText 50%, Canvas);
    background: color-mix(in srgb, CanvasText 3%, Canvas);
}

/* ── Deck header context menu ── */
.deck-ctx-menu {
    display: none; position: fixed;
    background: Canvas; color: CanvasText;
    border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas); border-radius: 6px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.18); z-index: 300;
    min-width: 170px; overflow: hidden;
    padding: 4px 0;
}
.deck-ctx-menu.open { display: block; }
.deck-ctx-menu button {
    display: block; width: 100%; padding: 7px 14px;
    border: none; background: none; text-align: left;
    cursor: pointer; font-size: 13px; color: CanvasText;
    transition: background 0.1s ease;
}
.deck-ctx-menu button:hover { background: color-mix(in srgb, CanvasText 8%, Canvas); }

/* ── View mode: hide edit-only elements ── */
body.view-mode .add-card-btn {
    opacity: 0; visibility: hidden;
    pointer-events: none;
}
body.view-mode .card-menu-btn {
    opacity: 0; visibility: hidden;
    pointer-events: none;
}

/* ── Card state indicators ── */
.card-frame.state-new          { border-bottom: 3px solid var(--state-new-color); }
.card-frame.state-learn        { border-bottom: 3px solid var(--state-learn-color); }
.card-frame.state-review-due   { border-bottom: 3px solid var(--state-review-color); }
.card-frame.state-review-soon  { border-bottom: 2px dotted var(--state-review-70); }
.card-frame.state-review-mid   { border-bottom: 2px dotted var(--state-review-50); }
.card-frame.state-review-later { border-bottom: 2px dotted var(--state-review-30); }

.card-state-badge {
    position: absolute; top: 8px; left: 10px;
    display: flex; align-items: center; gap: 4px;
    font-size: 11px; line-height: 1;
    border-radius: 4px; padding: 2px 6px;
    pointer-events: none; z-index: 5;
}
.state-new .card-state-badge {
    color: var(--state-new-color);
    background: var(--state-new-bg);
}
.state-learn .card-state-badge {
    color: var(--state-learn-color);
    background: var(--state-learn-bg);
}
.state-review-due .card-state-badge {
    color: var(--state-review-color);
    background: var(--state-review-bg);
}
.state-review-soon .card-state-badge {
    color: var(--state-review-70);
    background: var(--state-review-soon-bg);
}
.state-review-mid .card-state-badge {
    color: var(--state-review-50);
    background: var(--state-review-mid-bg);
}
.state-review-later .card-state-badge {
    color: var(--state-review-30);
    background: var(--state-review-later-bg);
}
.card-state-icon { display: inline-flex; }
.card-state-text { font-weight: 600; white-space: nowrap; }

/* ── Lazy-load placeholders ── */
.card-placeholder {
    min-height: 80px;
    display: flex; align-items: center; justify-content: center;
}
.card-placeholder .placeholder-inner {
    color: GrayText; font-size: 12px;
}

/* ── Dark mode refinements ── */
@media (prefers-color-scheme: dark) {
    .card-frame:hover {
        box-shadow: 0 2px 16px rgba(0,0,0,0.35);
    }
    .card-menu, .deck-ctx-menu {
        box-shadow: 0 6px 24px rgba(0,0,0,0.4);
    }
    #overlay-card {
        box-shadow: 0 8px 48px rgba(0,0,0,0.5);
    }
}
"""

_TRAY_JS = """\
var _editMode = false;
function setEditMode(on) {
    _editMode = on;
    document.body.classList.toggle('view-mode', !on);
}
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
    var scrollbarW = window.innerWidth - document.documentElement.clientWidth;
    document.documentElement.style.setProperty('--scrollbar-w', scrollbarW + 'px');
    document.body.classList.add('overlay-open');
    /* Trigger animated entrance on next frame */
    requestAnimationFrame(function() {
        requestAnimationFrame(function() {
            overlay.classList.add('visible');
        });
    });
}
function closeOverlay() {
    const overlay = document.getElementById('overlay');
    overlay.classList.remove('visible');
    document.body.classList.remove('overlay-open');
    document.documentElement.style.removeProperty('--scrollbar-w');
    /* Wait for exit animation then hide */
    setTimeout(function() { overlay.classList.remove('open'); }, 280);
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeOverlay(); });

function deckAction(e, action, deckId) {
    e.stopPropagation();
    pycmd(action + ':' + deckId);
}
function addCard(e, deckId) {
    e.stopPropagation();
    pycmd('add_card:' + deckId);
}

/* ── Deck header context menu (right-click) ── */
var _ctxMenu = null;
function showDeckCtx(e, deckId) {
    if (!_editMode) return;
    e.preventDefault(); e.stopPropagation();
    closeDeckCtx();
    var menu = document.getElementById('ctx-' + deckId);
    if (!menu) return;
    menu.style.left = e.clientX + 'px';
    menu.style.top = e.clientY + 'px';
    menu.classList.add('open');
    _ctxMenu = menu;
}
function closeDeckCtx() {
    if (_ctxMenu) { _ctxMenu.classList.remove('open'); _ctxMenu = null; }
}
document.addEventListener('click', closeDeckCtx);
function ctxAction(e, action, deckId) {
    e.stopPropagation();
    closeDeckCtx();
    pycmd(action + ':' + deckId);
}
function toggleSection(deckId) {
    var body = document.getElementById('body-' + deckId);
    var arrow = document.getElementById('arrow-' + deckId);
    if (!body) return;
    if (body.style.height === '0px') {
        /* Expand */
        body.style.height = body.scrollHeight + 'px';
        body.addEventListener('transitionend', function handler() {
            body.style.height = 'auto';
            body.classList.remove('collapsed');
            body.removeEventListener('transitionend', handler);
        });
    } else {
        /* Collapse: set explicit height first so transition has a start value */
        body.classList.add('collapsed');
        body.style.height = body.scrollHeight + 'px';
        body.offsetHeight; /* force reflow */
        body.style.height = '0px';
    }
    if (arrow) arrow.classList.toggle('collapsed');
    pycmd('toggle_section:' + deckId);
}
function scrollToSection(deckId) {
    var el = document.querySelector('[data-deck-id="' + deckId + '"]');
    if (!el) return;
    var p = el.parentElement;
    while (p) {
        if (p.classList && p.classList.contains('deck-body') && p.style.height === '0px') {
            p.style.height = 'auto';
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

/* ── Lazy loading via IntersectionObserver ── */
var _lazyPending = new Set();
var _lazyTimer = null;
var _lazyObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
        if (entry.isIntersecting) {
            var el = entry.target;
            var key = el.getAttribute('data-lazy');
            if (key) _lazyPending.add(key);
            _lazyObserver.unobserve(el);
        }
    });
    if (_lazyPending.size > 0 && !_lazyTimer) {
        _lazyTimer = setTimeout(_flushLazy, 16);
    }
}, { rootMargin: '400px' });

function _flushLazy() {
    _lazyTimer = null;
    if (_lazyPending.size === 0) return;
    var batch = Array.from(_lazyPending).slice(0, 20);
    batch.forEach(function(k) { _lazyPending.delete(k); });
    pycmd('lazy_load:' + batch.join(','));
    /* If more remain, schedule next batch */
    if (_lazyPending.size > 0) {
        _lazyTimer = setTimeout(_flushLazy, 50);
    }
}

function fillCards(data) {
    for (var key in data) {
        var el = document.querySelector('[data-lazy="' + key + '"]');
        if (el) {
            var tmp = document.createElement('div');
            tmp.innerHTML = data[key].trim();
            var card = tmp.firstElementChild;
            if (card) {
                el.parentNode.replaceChild(card, el);
            }
        }
    }
}

function initLazy() {
    document.querySelectorAll('.card-placeholder[data-lazy]').forEach(function(el) {
        _lazyObserver.observe(el);
    });
}
initLazy();
"""

# ── Card state helpers ──

_STATE_ICONS = {
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

_STATE_PRIORITY = {
    "learn": 6, "review-due": 5, "review-soon": 4,
    "review-mid": 3, "review-later": 2, "new": 1, "": 0,
}


def _card_state_from_meta(meta: dict, today: int = 0) -> str:
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


def _card_countdown_from_meta(meta: dict, today: int) -> str:
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


def _build_state_badge(state: str, countdown: str) -> str:
    """Build the HTML for the state badge shown in the card corner."""
    if not state:
        return ""
    # Review sub-states all share the 'review' icon
    icon_key = "review" if state.startswith("review") else state
    icon = _STATE_ICONS.get(icon_key, "")
    text = f'<span class="card-state-text">{_esc(countdown)}</span>' if countdown else ""
    return f'<span class="card-state-badge"><span class="card-state-icon">{icon}</span>{text}</span>'


def _get_state_colors() -> dict[str, str]:
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


def _get_cards_metadata(col, card_ids: Sequence[int]) -> dict[int, dict]:
    """Bulk-fetch card metadata in one SQL query instead of N get_card() calls."""
    if not card_ids:
        return {}
    # Process in chunks to avoid SQLite variable limit
    result: dict[int, dict] = {}
    chunk_size = 500
    for i in range(0, len(card_ids), chunk_size):
        chunk = card_ids[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        rows = col.db.all(
            f"SELECT c.id, c.type, c.queue, c.due, c.nid, n.mid "
            f"FROM cards c JOIN notes n ON c.nid = n.id "
            f"WHERE c.id IN ({placeholders})",
            *chunk,
        )
        for r in rows:
            result[r[0]] = {
                "cid": r[0], "type": r[1], "queue": r[2],
                "due": r[3], "nid": r[4], "mid": r[5],
            }
    return result


# Cache IO notetype lookups per model id
_io_mid_cache: dict[int, bool] = {}


def _is_io_mid(col, mid: int) -> bool:
    """Check if a model id is an Image Occlusion notetype (cached)."""
    if mid in _io_mid_cache:
        return _io_mid_cache[mid]
    nt = col.models.get(mid)
    result = nt is not None and "image occlusion" in nt["name"].lower()
    _io_mid_cache[mid] = result
    return result


# Regex to extract mask data-attributes from cloze/cloze-inactive/cloze-highlight divs
_MASK_RE = re.compile(
    r'<div\s+class="cloze(?:-inactive|-highlight)?"\s+'
    r'(data-(?:ordinal|shape|left|top|width|height|rx|ry|angle|points|fill)="[^"]*"\s*)+',
    re.DOTALL,
)
_ATTR_RE = re.compile(r'data-(shape|left|top|width|height|rx|ry|angle|points|fill)="([^"]*)"')
_ACTIVE_ORDINAL_RE = re.compile(r'class="cloze"\s+data-ordinal="(\d+)"')
_IMG_RE = re.compile(r'<img\s[^>]*src="([^"]*)"[^>]*/?\s*>')


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
    state: str = "",
    countdown: str = "",
) -> str:
    """Build a single grouped IO card with image + SVG mask overlay."""
    cls_parts = ["card-frame"]
    if all_suspended:
        cls_parts.append("suspended")
    if state:
        cls_parts.append(f"state-{state}")
    cls = " ".join(cls_parts)
    cids_str = ",".join(str(c) for c in card_ids)
    menu_id = card_ids[0]
    toggle_action = "unsuspend_group" if all_suspended else "suspend_group"
    toggle_label = "Unsuspend all" if all_suspended else "Suspend all"

    svg_shapes = "\n".join(
        _build_svg_mask(m, suspended=m.get("ordinal", "") in suspended_ordinals)
        for m in masks
    )

    badge = _build_state_badge(state, countdown)

    return (
        f'<div class="{cls}" onclick="expandCard(this)">'
        f'  {badge}'
        f'  <button class="card-menu-btn" onclick="toggleMenu(event,\'{menu_id}\')">&#8942;</button>'
        f'  <div class="card-menu" id="menu-{menu_id}">'
        f'    <button onclick="cardAction(event,\'{toggle_action}\',\'{cids_str}\')">{toggle_label}</button>'
        f'    <button onclick="cardAction(event,\'review_now_group\',\'{cids_str}\')">Review all now</button>'
        f'  </div>'
        f'  <div class="card-content">'
        f'    <div class="io-container">'
        f'      <img src="{img_src}"/>'
        f'      <svg viewBox="0 0 1 1" preserveAspectRatio="none">'
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

    # Emits when a new subdeck is created (so the viewer can refresh the tree)
    subdeck_created = pyqtSignal()

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)

        self._edit_mode: bool = False
        self._collapsed_decks: set[int] = set()
        self._io_group_map: dict[int, list[int]] = {}  # lead_cid → [group cids]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel(title)
        self._header.setStyleSheet(
            "font-size: 14px; font-weight: 600; padding: 8px 12px;"
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

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool) -> None:
        self._edit_mode = value
        self._web.eval(f"setEditMode({'true' if value else 'false'})")

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

        if action == "lazy_load":
            self._on_lazy_load(col, payload)
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

        if action == "add_card":
            deck_id = int(payload)
            col.decks.set_current(DeckId(deck_id))
            from aqt.addcards import AddCards
            add = AddCards(mw)
            add.show()
            return

        if action == "add_subdeck":
            deck_id = int(payload)
            deck = col.decks.get(DeckId(deck_id))
            if not deck:
                return
            parent_name = deck["name"]
            name, ok = QInputDialog.getText(
                self, "New Subdeck", f"Subdeck name under {parent_name}:"
            )
            if ok and name.strip():
                full_name = f"{parent_name}::{name.strip()}"
                col.decks.id(full_name)
                if self._tree_root is not None:
                    from .decks import find_deck_node
                    new_root = find_deck_node(self._tree_root.deck_id)
                    if new_root:
                        self.set_deck_tree(new_root, self._tree_name)
                self.subdeck_created.emit()
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
        self._io_group_map.clear()

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
            body += (
                f'<div class="deck-cards">{root_cards}'
                f'<div class="add-card-btn" onclick="addCard(event,{root_node.deck_id})" title="Add card to this deck">+</div>'
                f'</div>'
            )
        else:
            body += (
                f'<div class="deck-cards">'
                f'<div class="add-card-btn" onclick="addCard(event,{root_node.deck_id})" title="Add card to this deck">+</div>'
                f'</div>'
            )
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
        body_style = ' style="height:0px"' if collapsed else ''
        name_html = self._format_deck_path(full_path)
        d = min(depth, 4)

        return (
            f'<div class="deck-section" data-deck-id="{deck_id}">'
            f'<div class="deck-header depth-{d}" onclick="toggleSection({deck_id})"'
            f' oncontextmenu="showDeckCtx(event,{deck_id})">'
            f'<span class="{arrow_cls}" id="arrow-{deck_id}">\u25bc</span>'
            f'<span class="deck-name">{name_html}</span>'
            f'<span class="deck-info">'
            f'<span class="card-count">{len(all_cids)} cards</span>'
            f'<button class="deck-btn" onclick="deckAction(event,\'review_due_deck\',{deck_id})">Review due</button>'
            f'<button class="deck-btn" onclick="deckAction(event,\'force_review_deck\',{deck_id})">Force review all</button>'
            f'</span>'
            f'</div>'
            f'<div class="deck-body{" collapsed" if collapsed else ""}" id="body-{deck_id}"{body_style}>'
            f'<div class="deck-cards">{cards_html}'
            f'<div class="add-card-btn" onclick="addCard(event,{deck_id})" title="Add card to this deck">+</div>'
            f'</div>'
            f'{children_html}'
            f'</div>'
            f'<div class="deck-ctx-menu" id="ctx-{deck_id}">'
            f'<button onclick="ctxAction(event,\'add_subdeck\',{deck_id})">Add subdeck\u2026</button>'
            f'<button onclick="ctxAction(event,\'add_card\',{deck_id})">Add card\u2026</button>'
            f'</div>'
            f'</div>'
        )

    def _build_cards_html(self, col, card_ids: Sequence[int]) -> str:
        """Build lightweight placeholder HTML for lazy-loaded cards."""
        if not card_ids:
            return ""

        meta = _get_cards_metadata(col, card_ids)
        today = col.sched.today

        # Group IO cards by note using bulk metadata
        note_groups: dict[int, list[int]] = {}
        order: list[tuple[str, int]] = []

        for cid in card_ids:
            m = meta.get(cid)
            if m is None:
                continue
            if _is_io_mid(col, m["mid"]):
                nid = m["nid"]
                if nid not in note_groups:
                    note_groups[nid] = []
                    order.append(("note", nid))
                note_groups[nid].append(cid)
            else:
                order.append(("card", cid))

        parts: list[str] = []
        for kind, eid in order:
            if kind == "note":
                group_cids = note_groups[eid]
                lead_cid = group_cids[0]
                self._io_group_map[lead_cid] = group_cids

                # Determine group state from metadata
                group_state = ""
                group_countdown = ""
                all_susp = True
                for gcid in group_cids:
                    gm = meta.get(gcid, {})
                    if gm.get("queue") != QUEUE_TYPE_SUSPENDED:
                        all_susp = False
                        st = _card_state_from_meta(gm, today)
                        if _STATE_PRIORITY.get(st, 0) > _STATE_PRIORITY.get(group_state, 0):
                            group_state = st
                            group_countdown = _card_countdown_from_meta(gm, today)

                cls_parts = ["card-frame", "card-placeholder"]
                if all_susp:
                    cls_parts.append("suspended")
                if group_state:
                    cls_parts.append(f"state-{group_state}")
                cls = " ".join(cls_parts)
                badge = _build_state_badge(group_state, group_countdown)
                n_cards = len(group_cids)
                parts.append(
                    f'<div class="{cls}" data-lazy="{lead_cid}">'
                    f'  {badge}'
                    f'  <div class="placeholder-inner">'
                    f'    <span class="io-badge">{n_cards} occlusion cards</span>'
                    f'  </div>'
                    f'</div>'
                )
            else:
                cid = eid
                m = meta.get(cid, {})
                state = _card_state_from_meta(m, today)
                countdown = _card_countdown_from_meta(m, today)
                suspended = m.get("queue") == QUEUE_TYPE_SUSPENDED

                cls_parts = ["card-frame", "card-placeholder"]
                if suspended:
                    cls_parts.append("suspended")
                if state:
                    cls_parts.append(f"state-{state}")
                cls = " ".join(cls_parts)
                badge = _build_state_badge(state, countdown)
                parts.append(
                    f'<div class="{cls}" data-lazy="{cid}">'
                    f'  {badge}'
                    f'  <div class="placeholder-inner"></div>'
                    f'</div>'
                )

        return "\n".join(parts)

    def _build_io_group(self, col, group_cids: list[int]) -> str:
        """Build full HTML for a group of IO cards (called during lazy load)."""
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
            group_state = ""
            group_countdown = ""
            today = col.sched.today
            for gcid in group_cids:
                gc = col.get_card(CardId(gcid))
                is_susp = gc.queue == QUEUE_TYPE_SUSPENDED
                if not is_susp:
                    all_susp = False
                    m = {"queue": gc.queue, "type": gc.type, "due": gc.due}
                    st = _card_state_from_meta(m, today)
                    if _STATE_PRIORITY.get(st, 0) > _STATE_PRIORITY.get(group_state, 0):
                        group_state = st
                        group_countdown = _card_countdown_from_meta(m, today)
                q_html = gc.question()
                mo = _ACTIVE_ORDINAL_RE.search(q_html)
                if mo and is_susp:
                    suspended_ords.add(mo.group(1))
            return _build_io_card_html(
                img_src, masks, group_cids, suspended_ords, all_susp,
                state=group_state, countdown=group_countdown,
            )
        else:
            return self._render_normal_card(col, group_cids[0])

    def scroll_to_deck(self, deck_id: int) -> None:
        """Scroll the webview to a specific deck section."""
        self._web.eval(f"scrollToSection({deck_id})")

    def _render_page(self, body_html: str) -> None:
        """Render the full page with CSS, body content, overlay, and JS."""
        color_map = _get_state_colors()
        color_vars = ":root { " + " ".join(
            f"{k}: {v};" for k, v in color_map.items()
        ) + " }"
        self._web.stdHtml(
            f"<style>{color_vars}\n{_TRAY_CSS}</style>"
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

    def _on_lazy_load(self, col, payload: str) -> None:
        """Handle lazy_load bridge command: render requested cards and inject."""
        cids_str = [c.strip() for c in payload.split(",") if c.strip()]
        results: dict[str, str] = {}
        for cid_s in cids_str:
            cid = int(cid_s)
            if cid in self._io_group_map:
                html = self._build_io_group(col, self._io_group_map[cid])
            else:
                html = self._render_normal_card(col, cid)
            results[cid_s] = html
        data_json = json.dumps(results)
        self._web.eval(f"fillCards({data_json})")

    def set_cards(self, card_ids: Sequence[int]) -> None:
        """Render a flat list of cards (legacy single-deck view)."""
        self._current_card_ids = card_ids
        self._tree_root = None
        self._io_group_map.clear()
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
    def _render_normal_card(col, cid: int) -> str:
        """Render full card HTML (called during lazy load)."""
        card = col.get_card(CardId(cid))
        suspended = card.queue == QUEUE_TYPE_SUSPENDED
        m = {"queue": card.queue, "type": card.type, "due": card.due}
        state = _card_state_from_meta(m, col.sched.today)
        countdown = _card_countdown_from_meta(m, col.sched.today)

        cls_parts = ["card-frame"]
        if suspended:
            cls_parts.append("suspended")
        if state:
            cls_parts.append(f"state-{state}")
        cls = " ".join(cls_parts)

        toggle_label = "Unsuspend" if suspended else "Suspend"
        toggle_action = "unsuspend" if suspended else "suspend"
        answer_html = card.answer()
        badge = _build_state_badge(state, countdown)
        return (
            f'<div class="{cls}" onclick="expandCard(this)">'
            f'  {badge}'
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
