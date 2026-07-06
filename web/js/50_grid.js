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
