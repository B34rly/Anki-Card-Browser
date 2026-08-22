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
    /* The rebuilt HTML comes from Python, which knows nothing of the live
       selection — re-mark the selected units it contains. */
    _reapplySelection(neo);
    highlightMatches(neo);
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
   Two lookups mirror how Python picked the call: card ops (replaceCard /
   removeCard) match a card frame — standalone, or inside an expanded note
   group — while group ops (replaceGroup / removeGroup) match the group
   frame. Both fall back to the unit's lazy placeholder (its data-lazy key
   is the lead cid). The shapes must stay separate: a note group's lead card
   repeats its cid inside the expanded list, so a card op that preferred
   data-group-lead would take the whole group with it. */
function _cardEl(cid) {
    return document.querySelector('[data-cid="' + cid + '"]')
        || document.querySelector('[data-lazy="' + cid + '"]');
}
function _groupEl(leadCid) {
    return document.querySelector('[data-group-lead="' + leadCid + '"]')
        || document.querySelector('[data-lazy="' + leadCid + '"]');
}
function _swapUnit(old, id, html) {
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
    highlightMatches(neo);
    if (container) {
        layoutGrid(container);
        layoutGridOnImages(container);
    }
}
function _removeUnit(el, id) {
    if (el) el.remove();
    /* Purge the vanished unit from the selection, or the bar keeps a wrong
       count, plain clicks stay in toggle mode, and a later drag would move
       a card that is no longer on the page. */
    if (typeof _selected !== 'undefined' && _selected.delete(String(id))) {
        updateSelectionBar();
    }
}
function replaceCard(cid, html) { _swapUnit(_cardEl(cid), cid, html); }
function replaceGroup(leadCid, html) { _swapUnit(_groupEl(leadCid), leadCid, html); }
function removeCard(cid) { _removeUnit(_cardEl(cid), cid); }
function removeGroup(leadCid) { _removeUnit(_groupEl(leadCid), leadCid); }

/* ── Silent cross-section moves ──
   Relocate a rendered unit's element into another section's card container
   instead of rebuilding both sections — a rebuild re-mounts every card and
   re-decodes images, which reads as a flash. *afterIds* are the cids that
   follow the unit in the target's render order; the unit lands before the
   first one that resolves to a rendered unit in that container (non-lead
   group members resolve to nothing and are skipped), or at the end. The
   moved node keeps its lazy observer and selection state for free. */
function moveUnit(id, kind, targetDid, afterIds) {
    var el = kind === 'group' ? _groupEl(id) : _cardEl(id);
    var sec = document.querySelector('[data-deck-id="' + targetDid + '"]');
    var target = sec ? sec.querySelector(':scope > .deck-body > .deck-cards') : null;
    if (!el || !target) return;  /* converges via the next targeted refresh */
    var source = el.closest('.deck-cards');
    var anchor = null;
    for (var i = 0; i < afterIds.length && !anchor; i++) {
        var cand = _cardEl(afterIds[i]) || _groupEl(afterIds[i]);
        if (cand && cand.parentNode === target) anchor = cand;
    }
    target.insertBefore(el, anchor);
    layoutGrid(target);
    layoutGridOnImages(target);
    if (source && source !== target) {
        layoutGrid(source);
        layoutGridOnImages(source);
    }
}

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
