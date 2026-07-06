/* ── Targeted section refresh ── */
function replaceSection(deckId, html) {
    var old = document.querySelector('[data-deck-id="' + deckId + '"]');
    if (!old) return;
    var tmp = document.createElement('div');
    tmp.innerHTML = html.trim();
    var neo = tmp.firstElementChild;
    if (!neo) return;
    old.parentNode.replaceChild(neo, old);
    /* Re-register the scroll-spy observer for every header in the rebuilt subtree
       (_build_section is recursive, so child subsection headers are new too). */
    if (window._spyObserve) {
        neo.querySelectorAll('.deck-header').forEach(function(h) { window._spyObserve(h); });
    }
    /* Re-observe new placeholders inside the replaced section */
    neo.querySelectorAll('.card-placeholder[data-lazy]').forEach(function(el) {
        _lazyObserver.observe(el);
    });
    /* Re-layout grids inside the new section */
    neo.querySelectorAll('.deck-cards').forEach(function(c) {
        layoutGrid(c);
        layoutGridOnImages(c);
    });
}
function updateHeaderCounts(deckId, countsHtml) {
    var sec = document.querySelector('[data-deck-id="' + deckId + '"]');
    if (!sec) return;
    var hdr = sec.querySelector(':scope > .deck-header');
    if (!hdr) return;
    var cc = hdr.querySelector('.card-count');
    if (cc) cc.outerHTML = countsHtml;
}

/* ── Targeted unit refresh (single cards and groups) ──
   A rendered unit is found by its note-group lead (data-group-lead), its card
   id (data-cid), or — when it hasn't lazy-loaded yet — its placeholder
   (data-lazy). One lookup serves all shapes so the replace/remove logic can't
   diverge between cards and groups. */
function _unitEl(id) {
    return document.querySelector('[data-group-lead="' + id + '"]')
        || document.querySelector('[data-cid="' + id + '"]')
        || document.querySelector('[data-lazy="' + id + '"]');
}
function _swapUnit(id, html) {
    var old = _unitEl(id);
    if (!old) return;
    var tmp = document.createElement('div');
    tmp.innerHTML = html.trim();
    var neo = tmp.firstElementChild;
    if (!neo) return;
    var container = old.closest('.deck-cards');
    old.parentNode.replaceChild(neo, old);
    /* A replaced unit keeps its selection (targeted refreshes must not
       silently shrink the user's selection). */
    if (typeof _selected !== 'undefined' && _selected.has(String(id))) {
        neo.classList.add('selected');
    }
    if (container) {
        layoutGrid(container);
        layoutGridOnImages(container);
    }
}
function replaceCard(cid, html) { _swapUnit(cid, html); }
function replaceGroup(leadCid, html) { _swapUnit(leadCid, html); }
function removeCard(cid) {
    var old = _unitEl(cid);
    if (old) old.remove();
}
function removeGroup(leadCid) { removeCard(leadCid); }

/* ── Scroll position reporting + restore across full re-renders ──
   A raw pixel offset is meaningless across a re-render: cards lazy-load at
   variable heights, so the document grows as you scroll and the same offset maps
   to a different section. Instead we anchor to the deck *section* at the top of
   the viewport plus how far we've scrolled into it, then re-resolve that section's
   live position on restore. */
var _scrollReportTimer = null;
var _suppressScrollReport = false;

/* Deepest deck-section whose top edge is at or above the viewport top.
   Sections appear in document order and their tops only increase (children
   start at or below their parent), so stop at the first one below the line
   instead of measuring every section on each scroll tick. */
function _anchorSection() {
    var best = null;
    var secs = document.querySelectorAll('.deck-section');
    for (var i = 0; i < secs.length; i++) {
        if (secs[i].getBoundingClientRect().top <= 4) best = secs[i];
        else break;
    }
    return best;
}
window.addEventListener('scroll', function() {
    if (_suppressScrollReport || _scrollReportTimer) return;
    _scrollReportTimer = setTimeout(function() {
        _scrollReportTimer = null;
        var s = _anchorSection();
        if (s) {
            var depth = Math.round(-s.getBoundingClientRect().top);
            pycmd('scroll:' + s.getAttribute('data-deck-id') + ':' + depth);
        } else {
            pycmd('scroll:0:' + Math.round(window.scrollY));
        }
    }, 120);
}, { passive: true });

/* Called by Python (after a full render) to jump back to the saved anchor.
   deckId 0 means "no section anchor — use the raw offset". The section's live
   position is measured now (above content is still short placeholders), so the
   anchored section lands at the same spot regardless of lazy-load heights. The
   resulting scroll event is suppressed so it can't overwrite the saved value. */
function restoreScroll(deckId, depth) {
    _suppressScrollReport = true;
    if (deckId) {
        var s = document.querySelector('[data-deck-id="' + deckId + '"]');
        if (s) {
            var top = s.getBoundingClientRect().top + window.scrollY;
            window.scrollTo(0, Math.max(0, Math.round(top + depth)));
        } else {
            window.scrollTo(0, 0);
        }
    } else {
        window.scrollTo(0, depth);
    }
    requestAnimationFrame(function() {
        requestAnimationFrame(function() { _suppressScrollReport = false; });
    });
}
