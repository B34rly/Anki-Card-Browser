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
