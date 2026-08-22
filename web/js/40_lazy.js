/* ── Lazy loading via IntersectionObserver ── */
var _lazyPending = new Set();
var _lazySentAt = {};  /* key → epoch-ms of last request (rescue dedup) */
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
    /* The Python bridge (pycmd) is connected asynchronously by a QWebChannel
       handshake after page load. A placeholder can scroll into view before
       that — sending would throw and the batch (already unobserved) would
       stay blank forever. Keep the keys and retry instead. */
    if (typeof pycmd !== 'function') {
        _lazyTimer = setTimeout(_flushLazy, 100);
        return;
    }
    var batch = Array.from(_lazyPending).slice(0, 20);
    var now = Date.now();
    batch.forEach(function(k) { _lazyPending.delete(k); _lazySentAt[k] = now; });
    pycmd('lazy_load:' + batch.join(','));
    /* If more remain, schedule next batch */
    if (_lazyPending.size > 0) {
        _lazyTimer = setTimeout(_flushLazy, 50);
    }
}

/* Safety net: re-queue any placeholder still unfilled near the viewport.
   A lazy_load request or its fillCards response can be lost when a re-render
   races the bridge (e.g. typing in the search box replaces the page while a
   batch is in flight); without this sweep those cards stayed blank until a
   manual refresh. Collapsed sections are skipped — their contents are clipped,
   not visible. Requests are idempotent, so a duplicate is harmless. */
setInterval(function() {
    if (typeof pycmd !== 'function') return;
    var queued = false;
    var now = Date.now();
    document.querySelectorAll('.card-placeholder[data-lazy]').forEach(function(el) {
        if (el.closest('.deck-body.collapsed')) return;
        var key = el.getAttribute('data-lazy');
        /* A recent request may legitimately still be in flight — don't
           re-send it (Python answers every request with fillCards or
           removeCard, so anything older really was lost). */
        if (!key || now - (_lazySentAt[key] || 0) < 5000) return;
        var r = el.getBoundingClientRect();
        if (r.bottom > -400 && r.top < window.innerHeight + 400) {
            _lazyPending.add(key);
            queued = true;
        }
    });
    if (queued && !_lazyTimer) _lazyTimer = setTimeout(_flushLazy, 16);
}, 1500);

function fillCards(data) {
    var affectedContainers = new Set();
    for (var key in data) {
        var el = document.querySelector('[data-lazy="' + key + '"]');
        if (el) {
            var tmp = document.createElement('div');
            tmp.innerHTML = data[key].trim();
            var card = tmp.firstElementChild;
            if (card) {
                /* A selected placeholder fills into a selected unit (the
                   data-lazy key IS the unit id). */
                if (typeof _selected !== 'undefined' && _selected.has(key)) {
                    card.classList.add('selected');
                }
                highlightMatches(card);
                _reapplyKbFocus(card);
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

function fillNoteCards(gk, html) {
    var body = document.getElementById('note-cards-' + gk);
    if (body) {
        body.innerHTML = html;
        highlightMatches(body);
    }
}

function initLazy() {
    document.querySelectorAll('.card-placeholder[data-lazy]').forEach(function(el) {
        _lazyObserver.observe(el);
    });
}
initLazy();
