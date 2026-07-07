/* ── Detail overlay ──
   Clicking a card / group asks Python for a full detail view (content, stats,
   action bar); Python answers with showCardDetail(html, id, isRefresh). While
   it is open, actions re-push a fresh detail (isRefresh=true) and left/right
   arrows step through units. */
var _overlayId = null;

function expandCard(el) {
    if (maybeSelect(window.event, el)) return;  /* selection gesture */
    if (typeof pycmd !== 'function') return;  /* bridge still connecting */
    var cid = el.getAttribute('data-cid');
    if (cid) pycmd('card_detail:' + cid);
}
var _overlayCloseTimer = null;
function _openOverlay() {
    var overlay = document.getElementById('overlay');
    if (_overlayCloseTimer) {
        /* Re-opened during the close animation — cancel the pending hide and
           re-assert the visible state (the 280ms timeout would otherwise
           strip 'open' from the overlay we just filled). */
        clearTimeout(_overlayCloseTimer);
        _overlayCloseTimer = null;
        overlay.classList.add('visible');
        document.body.classList.add('overlay-open');
        return;
    }
    if (overlay.classList.contains('open')) return;  /* refresh in place */
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
var _overlayNavDir = 0;
var _overlaySwapTimer = null;
function showCardDetail(html, id, isRefresh) {
    /* A refresh push can land mid-close (Escape while an op was rebuilding
       the open detail): accepting it would reopen an overlay Python already
       believes is closed — never refreshed, never closable from its side.
       Only pushes for the unit currently shown may refresh; user-initiated
       opens (isRefresh falsy) always win. Refreshes also back off while the
       detail's fields hold unsaved edits (DOM-only text a swap would wipe;
       our own save re-pushes with isRefresh=false, so it still lands). */
    if (isRefresh && (id !== _overlayId || _fieldsDirty())) return;
    _overlayId = id;
    var overlay = document.getElementById('overlay');
    var inner = document.getElementById('overlay-card-content');
    var dir = _overlayNavDir;
    _overlayNavDir = 0;
    /* Arrow navigation between units slides the old content out and the new
       content in from the travel direction; everything else swaps in place. */
    if (dir && overlay.classList.contains('open')) {
        if (_overlaySwapTimer) { clearTimeout(_overlaySwapTimer); _overlaySwapTimer = null; }
        inner.classList.remove('slide-in-left', 'slide-in-right');
        inner.classList.add(dir > 0 ? 'slide-out-left' : 'slide-out-right');
        _overlaySwapTimer = setTimeout(function() {
            _overlaySwapTimer = null;
            inner.innerHTML = html;
            inner.classList.remove('slide-out-left', 'slide-out-right');
            inner.classList.add(dir > 0 ? 'slide-in-right' : 'slide-in-left');
            requestAnimationFrame(function() {
                requestAnimationFrame(function() {
                    inner.classList.remove('slide-in-right', 'slide-in-left');
                });
            });
        }, 130);
        return;
    }
    inner.innerHTML = html;
    _openOverlay();
}
/* Sides: 'q'/'a' (rendered card) and 'f' (the editable raw fields) — one
   pane at a time, so the render and its source never repeat each other. */
function _showDetailSide(side) {
    var c = document.getElementById('detail-content');
    if (!c) return;
    ['q', 'a', 'f'].forEach(function(s) {
        c.classList.toggle('show-' + s, s === side);
    });
    document.querySelectorAll('.ds-toggle').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-side') === side);
    });
}
function detailShowSide(e, side) {
    e.stopPropagation();
    _showDetailSide(side);
}
/* Detail-overlay actions reuse cardAction; Python re-pushes the open detail
   after applying the action, so the overlay refreshes itself. */
/* Units in page order: loaded cards/groups AND lazy placeholders (their
   data-lazy key is the unit's lead cid, so a detail can be requested before
   the card has filled in). Inner cards of an expanded note group don't
   qualify. */
function _detailUnits() {
    return Array.prototype.filter.call(
        document.querySelectorAll(
            '.card-frame[data-cid], .note-group[data-group-lead], .card-placeholder[data-lazy]'),
        function(el) { return !el.closest('.note-cards-body'); }
    );
}
function _unitDetailId(el) {
    return el.getAttribute('data-cid') || el.getAttribute('data-group-lead')
        || el.getAttribute('data-lazy');
}
function overlayNav(dir) {
    if (_overlayId === null) return;
    var units = _detailUnits();
    var idx = -1;
    for (var i = 0; i < units.length; i++) {
        if (_unitDetailId(units[i]) == _overlayId) { idx = i; break; }
    }
    if (idx < 0) return;
    var next = units[idx + dir];
    if (!next) return;
    _overlayNavDir = dir;  /* consumed by showCardDetail for the slide */
    if (next.hasAttribute('data-group-lead')) {
        pycmd('note_detail:' + _unitDetailId(next));
    } else {
        /* Python re-dispatches group leads to the right detail kind. */
        pycmd('card_detail:' + _unitDetailId(next));
    }
}

/* ── Note group: detail overlay (fields + card template dropdown) ── */
function expandNoteGroup(el) {
    if (maybeSelect(window.event, el)) return;  /* selection gesture */
    if (typeof pycmd !== 'function') return;  /* bridge still connecting */
    var lead = el.getAttribute('data-group-lead');
    if (lead) pycmd('note_detail:' + lead);
}
function onNoteCardSelect(sel) {
    var cid = sel.value;
    if (!cid) {
        document.getElementById('overlay-card-preview').innerHTML = '';
        return;
    }
    pycmd('preview_card:' + cid);
}
function fillCardPreview(html) {
    var el = document.getElementById('overlay-card-preview');
    if (el) el.innerHTML = html;
}

/* ── Note group: show/hide individual cards in-place ── */
function toggleNoteCards(e, gk) {
    e.stopPropagation();
    var body = document.getElementById('note-cards-' + gk);
    if (!body) return;
    var toggle = e.currentTarget;
    if (body.classList.contains('open')) {
        body.classList.remove('open');
        toggle.classList.remove('expanded');
        toggle.innerHTML = toggle.innerHTML.replace('▾', '▸');
    } else {
        body.classList.add('open');
        toggle.classList.add('expanded');
        toggle.innerHTML = toggle.innerHTML.replace('▸', '▾');
        /* Load cards if empty */
        if (!body.hasChildNodes() || body.innerHTML.trim() === '') {
            var parent = body.closest('.note-group');
            var cidsAttr = parent ? parent.getAttribute('data-card-ids') : '';
            if (cidsAttr) pycmd('lazy_load_note_cards:' + cidsAttr);
        }
    }
}
/* ── In-place field editing (part of the detail view itself) ──
   Every card/note detail carries a #detail-fields section: contenteditable
   blocks inside the same popup as the stats/actions/history. Typing marks
   it dirty, which reveals the Revert/Save bar and makes refresh pushes
   back off (see showCardDetail) so an op landing mid-edit can't wipe the
   text. Save round-trips through save_note; Revert re-requests this same
   detail. Unsaved text is deliberately DOM-only. */
function _detailFields() {
    return document.getElementById('detail-fields');
}
function _fieldsDirty() {
    var f = _detailFields();
    return !!(f && f.classList.contains('dirty'));
}
document.addEventListener('input', function(e) {
    var f = e.target && e.target.closest ? e.target.closest('#detail-fields') : null;
    if (f) f.classList.add('dirty');
});
function saveNoteEdit() {
    var f = _detailFields();
    if (!f || !_fieldsDirty() || typeof pycmd !== 'function') return;
    var fields = [];
    f.querySelectorAll('.edit-field').forEach(function(el) {
        fields.push(el.innerHTML);
    });
    pycmd('save_note:' + JSON.stringify({
        nid: f.getAttribute('data-nid'),
        unit: f.getAttribute('data-unit'),
        fields: fields,
    }));
}
function revertNoteEdit() {
    var f = _detailFields();
    if (!f || typeof pycmd !== 'function') return;
    pycmd('card_detail:' + f.getAttribute('data-unit'));
}
function focusDetailFields(e) {
    if (e) e.stopPropagation();
    var f = _detailFields();
    if (!f) return;
    /* In a card detail the fields live in the toggle's Fields pane — bring
       that to front first (a hidden field can't take focus). */
    var content = document.getElementById('detail-content');
    if (content && content.contains(f)) _showDetailSide('f');
    var first = f.querySelector('.edit-field');
    if (!first) return;
    first.scrollIntoView({block: 'nearest'});
    first.focus();
}

function closeOverlay() {
    const overlay = document.getElementById('overlay');
    overlay.classList.remove('visible');
    document.body.classList.remove('overlay-open');
    document.documentElement.style.removeProperty('--scrollbar-w');
    if (_overlayId !== null) {
        _overlayId = null;
        /* Tell Python so it stops refreshing a closed detail view. */
        if (typeof pycmd === 'function') pycmd('detail_closed:1');
    }
    /* Wait for exit animation then hide */
    _overlayCloseTimer = setTimeout(function() {
        _overlayCloseTimer = null;
        overlay.classList.remove('open');
    }, 280);
}
document.addEventListener('keydown', function(e) {
    var overlay = document.getElementById('overlay');
    var overlayOpen = overlay && overlay.classList.contains('open');
    if (e.key === 'Escape') {
        var focused = document.activeElement;
        if (overlayOpen && focused && focused.classList
                && focused.classList.contains('edit-field')) {
            focused.blur();  /* step out of the field; second Esc closes */
        } else if (overlayOpen) {
            closeOverlay();
        } else {
            clearSelection();
        }
        return;
    }
    if (!overlayOpen) return;
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && _fieldsDirty()) {
        e.preventDefault();
        saveNoteEdit();
        return;
    }
    /* Don't steal arrows from a focused form control (the card-preview
       select uses them for options; the editor's fields for the caret). */
    var focused = document.activeElement;
    if (focused && (/^(select|input|textarea)$/i.test(focused.tagName)
        || focused.isContentEditable)) return;
    if (e.key === 'ArrowLeft') overlayNav(-1);
    else if (e.key === 'ArrowRight') overlayNav(1);
});

function deckAction(e, action, deckId) {
    e.stopPropagation();
    pycmd(action + ':' + deckId);
}
