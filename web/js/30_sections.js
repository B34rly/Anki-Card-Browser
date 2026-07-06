/* ── Header plus-button dropdown ── */
var _plusMenu = null;
var _plusMenuHeader = null;
function togglePlusMenu(e, deckId) {
    e.stopPropagation();
    var menu = document.getElementById('plus-menu-' + deckId);
    if (!menu) return;
    var wasOpen = (_plusMenu === menu);
    closePlusMenu();
    if (wasOpen) return;  /* second click on the same button closes it */
    var btn = e.currentTarget;
    var rect = btn.getBoundingClientRect();
    menu.classList.add('open');   /* display:block so we can measure it */
    _plusMenu = menu;
    /* The menu is position:fixed but lives inside a sticky .deck-header, which is
       its own stacking context — its z-index is confined there and later headers
       paint over it. Lift the enclosing header above its siblings while the menu
       is open (no effect for the root header, which isn't sticky). */
    var hdr = menu.closest('.deck-header');
    if (hdr) { hdr.classList.add('plus-open'); _plusMenuHeader = hdr; }
    /* Anchor below the button, flipping up / clamping in so it never opens
       off-screen for decks near the viewport edge. */
    var mh = menu.offsetHeight, mw = menu.offsetWidth;
    var top = rect.bottom + 2;
    if (top + mh + 4 > window.innerHeight) top = Math.max(4, rect.top - mh - 2);
    var left = Math.min(rect.left, window.innerWidth - mw - 6);
    if (left < 4) left = 4;
    menu.style.top = top + 'px';
    menu.style.left = left + 'px';
}
function closePlusMenu() {
    if (_plusMenu) { _plusMenu.classList.remove('open'); _plusMenu = null; }
    if (_plusMenuHeader) { _plusMenuHeader.classList.remove('plus-open'); _plusMenuHeader = null; }
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
    var collapsing;
    if (body.style.height === '0px') {
        /* Expand */
        collapsing = false;
        body.style.height = body.scrollHeight + 'px';
        body.addEventListener('transitionend', function handler() {
            body.style.height = 'auto';
            body.classList.remove('collapsed');
            body.removeEventListener('transitionend', handler);
        });
    } else {
        /* Collapse: set explicit height first so transition has a start value */
        collapsing = true;
        body.classList.add('collapsed');
        body.style.height = body.scrollHeight + 'px';
        body.offsetHeight; /* force reflow */
        body.style.height = '0px';
    }
    if (arrow) arrow.classList.toggle('collapsed');
    /* Report the explicit end state — a toggle could invert Python's persisted
       state if this message replayed or raced a re-render. */
    pycmd('set_collapsed:' + deckId + ':' + (collapsing ? 1 : 0));
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
            /* Keep Python's _collapsed_decks in sync so the next full render
               doesn't re-collapse the section the user just scrolled into.
               The explicit state is idempotent — it can't invert the persisted
               state if this message races a re-render. */
            pycmd('set_collapsed:' + id + ':0');
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
    /* Allow replaceSection() to re-observe headers it rebuilds. */
    window._spyObserve = function(h) { if (h) observer.observe(h); };
})();
