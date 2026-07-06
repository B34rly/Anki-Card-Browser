/* ── Drag & drop: move cards onto a deck section header ──
   Delegated listeners so units rebuilt by targeted refreshes keep working.
   _dragCids doubles as the "this drag is ours" flag: external drags (files,
   text from other apps) are refused so a stray drop can never navigate the
   page (drops are only enabled at the Qt level for this to work at all). */
var _dragCids = null;
document.addEventListener('dragstart', function(e) {
    var t = e.target;
    var unit = t && t.closest
        ? t.closest('.card-frame[data-cid], .note-group[data-group-lead]') : null;
    if (!_editMode || !unit || unit.closest('.note-cards-body')) {
        e.preventDefault();  /* also stops native image/text drags */
        return;
    }
    var unitId = unit.getAttribute('data-cid') || unit.getAttribute('data-group-lead');
    /* Dragging a selected unit drags the whole selection. */
    if (typeof _selected !== 'undefined' && _selected.has(unitId) && _selected.size > 1) {
        _dragCids = Array.from(_selected).join(',');
    } else {
        _dragCids = unitId;
    }
    e.dataTransfer.setData('text/plain', _dragCids);
    e.dataTransfer.effectAllowed = 'move';
    document.body.classList.add('dragging-card');
});
document.addEventListener('dragend', function() {
    _dragCids = null;
    document.body.classList.remove('dragging-card');
    document.querySelectorAll('.drop-target').forEach(function(h) {
        h.classList.remove('drop-target');
    });
});
function _dropHeader(e) {
    var hdr = e.target && e.target.closest
        ? e.target.closest('.deck-header, .root-header') : null;
    return hdr;
}
document.addEventListener('dragover', function(e) {
    e.preventDefault();  /* claim the drag so we control the drop effect */
    if (_dragCids === null) { e.dataTransfer.dropEffect = 'none'; return; }
    var hdr = _dropHeader(e);
    document.querySelectorAll('.drop-target').forEach(function(h) {
        if (h !== hdr) h.classList.remove('drop-target');
    });
    if (hdr) {
        e.dataTransfer.dropEffect = 'move';
        hdr.classList.add('drop-target');
    } else {
        e.dataTransfer.dropEffect = 'none';
    }
});
document.addEventListener('drop', function(e) {
    e.preventDefault();  /* never let Chromium act on a drop itself */
    if (_dragCids === null) return;
    var hdr = _dropHeader(e);
    if (!hdr) return;
    var sec = hdr.closest('.deck-section');
    var did = sec ? sec.getAttribute('data-deck-id')
                  : hdr.getAttribute('data-root-did');
    if (did) pycmd('move_cards:' + did + ':' + _dragCids);
});
