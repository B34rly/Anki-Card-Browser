"""JavaScript for the CardTray webview.

Handles edit-mode toggle, card/deck menus, overlay expand/close,
scroll-spy, lazy-load IntersectionObserver, and deck section collapse.
"""

TRAY_JS = """\
var _editMode = false;
function setEditMode(on) {
    _editMode = on;
    document.body.classList.toggle('view-mode', !on);
}
setEditMode(false);
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
function editCard(e, cid) {
    e.stopPropagation();
    pycmd('edit_card:' + cid);
}
function deleteCard(e, cid) {
    e.stopPropagation();
    document.querySelectorAll('.card-menu.open').forEach(m => m.classList.remove('open'));
    pycmd('delete_card:' + cid);
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

/* ── Note group: expand overlay with fields + card template dropdown ── */
function expandNoteGroup(el) {
    var overlay = document.getElementById('overlay');
    var inner = document.getElementById('overlay-card-content');
    /* Fields table (full size in overlay) */
    var fieldsHtml = '<div class="overlay-note-header">'
        + el.querySelector('.card-content').innerHTML
        + '</div>';
    /* Card template dropdown */
    var namesAttr = el.getAttribute('data-card-names') || '';
    var entries = namesAttr.split('|').filter(function(x){ return x; });
    if (entries.length > 0) {
        fieldsHtml += '<select class="overlay-card-select" onchange="onNoteCardSelect(this)">';
        fieldsHtml += '<option value="">Select a card to preview\u2026</option>';
        entries.forEach(function(entry) {
            var sep = entry.indexOf(':');
            var cid = entry.substring(0, sep);
            var name = entry.substring(sep + 1);
            fieldsHtml += '<option value="' + cid + '">' + name + '</option>';
        });
        fieldsHtml += '</select>';
        fieldsHtml += '<div class="overlay-card-preview" id="overlay-card-preview"></div>';
    }
    inner.innerHTML = fieldsHtml;
    overlay.classList.add('open');
    var scrollbarW = window.innerWidth - document.documentElement.clientWidth;
    document.documentElement.style.setProperty('--scrollbar-w', scrollbarW + 'px');
    document.body.classList.add('overlay-open');
    requestAnimationFrame(function() {
        requestAnimationFrame(function() {
            overlay.classList.add('visible');
        });
    });
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
function toggleNoteCards(e, nid) {
    e.stopPropagation();
    var body = document.getElementById('note-cards-' + nid);
    if (!body) return;
    var toggle = e.currentTarget;
    if (body.classList.contains('open')) {
        body.classList.remove('open');
        toggle.classList.remove('expanded');
        toggle.innerHTML = toggle.innerHTML.replace('\u25be', '\u25b8');
    } else {
        body.classList.add('open');
        toggle.classList.add('expanded');
        toggle.innerHTML = toggle.innerHTML.replace('\u25b8', '\u25be');
        /* Load cards if empty */
        if (!body.hasChildNodes() || body.innerHTML.trim() === '') {
            var parent = body.closest('.note-group');
            var cidsAttr = parent ? parent.getAttribute('data-card-ids') : '';
            if (cidsAttr) pycmd('lazy_load_note_cards:' + cidsAttr);
        }
    }
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

/* ── Header plus-button dropdown ── */
var _plusMenu = null;
function togglePlusMenu(e, deckId) {
    e.stopPropagation();
    closePlusMenu();
    var menu = document.getElementById('plus-menu-' + deckId);
    if (!menu) return;
    var btn = e.currentTarget;
    var rect = btn.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.top = rect.bottom + 2 + 'px';
    menu.classList.add('open');
    _plusMenu = menu;
}
function closePlusMenu() {
    if (_plusMenu) { _plusMenu.classList.remove('open'); _plusMenu = null; }
}
document.addEventListener('click', closePlusMenu);
function plusAction(e, action, deckId) {
    e.stopPropagation();
    closePlusMenu();
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
    var affectedContainers = new Set();
    for (var key in data) {
        var el = document.querySelector('[data-lazy="' + key + '"]');
        if (el) {
            var tmp = document.createElement('div');
            tmp.innerHTML = data[key].trim();
            var card = tmp.firstElementChild;
            if (card) {
                el.parentNode.replaceChild(card, el);
                var container = card.closest('.deck-cards');
                if (container) affectedContainers.add(container);
            }
        }
    }
    affectedContainers.forEach(function(c) {
        layoutGrid(c);
        layoutGridOnImages(c);
    });
}

function fillNoteCards(nid, html) {
    var body = document.getElementById('note-cards-' + nid);
    if (body) body.innerHTML = html;
}

function initLazy() {
    document.querySelectorAll('.card-placeholder[data-lazy]').forEach(function(el) {
        _lazyObserver.observe(el);
    });
}
initLazy();

/* ── Grid layout: measure cards and set row/column spans ── */
var _gridRowH = 10;   /* matches grid-auto-rows */
var _gridGap  = 14;   /* matches gap */
var _gridColSpan2 = 400;  /* height threshold for 2-column span */
var _gridColSpan3 = 700;  /* height threshold for 3-column span */
var _gridShrinkMin = 0.25; /* card must shrink ≥25% to keep wider span */

function layoutGrid(container) {
    if (!container) return;
    var cards = container.querySelectorAll('.card-frame, .note-group, .card-placeholder');

    /* ── Pass 1: reset to 1-col, measure natural heights ── */
    cards.forEach(function(card) {
        card.style.gridRow = '';
        card.style.gridColumn = '';
    });
    container.offsetHeight; /* reflow at 1-column width */

    var measurements = [];
    cards.forEach(function(card) {
        var h1 = card.scrollHeight;
        var colSpan = 1;
        if (h1 > _gridColSpan3) colSpan = 3;
        else if (h1 > _gridColSpan2) colSpan = 2;
        measurements.push({ el: card, h1: h1, colSpan: colSpan });
    });

    /* ── Pass 2: apply candidate column spans, re-measure, validate ── */
    measurements.forEach(function(m) {
        if (m.colSpan > 1) {
            m.el.style.gridColumn = 'span ' + m.colSpan;
        }
    });
    if (measurements.some(function(m) { return m.colSpan > 1; })) {
        container.offsetHeight; /* reflow at wider widths */
    }

    measurements.forEach(function(m) {
        var hFinal = m.h1;
        if (m.colSpan > 1) {
            var h2 = m.el.scrollHeight;
            var shrink = (m.h1 - h2) / m.h1;
            if (shrink < _gridShrinkMin) {
                /* Widening didn't help — content is just text-tall, revert */
                m.colSpan = 1;
                m.el.style.gridColumn = '';
                hFinal = m.h1;
            } else {
                hFinal = h2;
            }
        }
        var rowSpan = Math.ceil((hFinal + _gridGap) / (_gridRowH + _gridGap));
        m.el.style.gridRow = 'span ' + rowSpan;
    });

    /* ── Pass 3: final reflow for any reverted cards ── */
    if (measurements.some(function(m) { return m.colSpan === 1; })) {
        container.offsetHeight;
        measurements.forEach(function(m) {
            if (m.colSpan === 1) {
                var h = m.el.scrollHeight;
                var rowSpan = Math.ceil((h + _gridGap) / (_gridRowH + _gridGap));
                m.el.style.gridRow = 'span ' + rowSpan;
            }
        });
    }
}

function layoutAllGrids() {
    document.querySelectorAll('.deck-cards').forEach(layoutGrid);
}

/* Run layout after images load (they change card height) */
function layoutGridOnImages(container) {
    if (!container) return;
    var imgs = container.querySelectorAll('img');
    if (imgs.length === 0) return;
    var remaining = imgs.length;
    function onLoad() {
        remaining--;
        if (remaining <= 0) layoutGrid(container);
    }
    imgs.forEach(function(img) {
        if (img.complete) { remaining--; }
        else { img.addEventListener('load', onLoad); img.addEventListener('error', onLoad); }
    });
    if (remaining <= 0) return; /* all already loaded */
}

/* Initial layout + resize handler */
layoutAllGrids();
document.querySelectorAll('.deck-cards').forEach(layoutGridOnImages);
var _resizeTimer = null;
window.addEventListener('resize', function() {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(layoutAllGrids, 100);
});

/* ── Targeted section refresh ── */
function replaceSection(deckId, html) {
    var old = document.querySelector('[data-deck-id="' + deckId + '"]');
    if (!old) return;
    var tmp = document.createElement('div');
    tmp.innerHTML = html.trim();
    var neo = tmp.firstElementChild;
    if (!neo) return;
    old.parentNode.replaceChild(neo, old);
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

/* ── Single-card targeted refresh ── */
function replaceCard(cid, html) {
    var old = document.querySelector('[data-cid="' + cid + '"]')
           || document.querySelector('[data-lazy="' + cid + '"]');
    if (!old) return;
    var tmp = document.createElement('div');
    tmp.innerHTML = html.trim();
    var neo = tmp.firstElementChild;
    if (!neo) return;
    var container = old.closest('.deck-cards');
    old.parentNode.replaceChild(neo, old);
    if (container) {
        layoutGrid(container);
        layoutGridOnImages(container);
    }
}
function removeCard(cid) {
    var old = document.querySelector('[data-cid="' + cid + '"]')
           || document.querySelector('[data-lazy="' + cid + '"]');
    if (old) old.remove();
}
"""
