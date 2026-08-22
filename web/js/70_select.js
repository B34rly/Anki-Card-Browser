/* ── Multiselect: Ctrl/Cmd-click to select units, bulk actions on the bar ──
   Selection holds unit ids (data-cid or data-group-lead) as strings. While a
   selection exists, plain clicks toggle membership instead of opening the
   detail overlay; Shift-click selects the range from the last toggled unit.
   Bulk actions send `bulk:<action>:<leads>` — Python expands group leads to
   their members, applies the action, refreshes the units, and calls
   clearSelection(). */
var _selected = new Set();
var _selectAnchor = null;

function _selId(el) {
    /* data-lazy last: a placeholder's key is its unit's lead cid, so
       not-yet-loaded units participate in selection like loaded ones. */
    return el.getAttribute('data-cid') || el.getAttribute('data-group-lead')
        || el.getAttribute('data-lazy');
}

/* Called from expandCard/expandNoteGroup with the click event; returns true
   when the click was consumed as a selection gesture. */
function maybeSelect(ev, el) {
    if (!_editMode) return false;
    if (ev && ev.shiftKey && _selectAnchor !== null) {
        _selectRangeTo(el);
        return true;
    }
    if ((ev && (ev.ctrlKey || ev.metaKey)) || _selected.size > 0) {
        toggleSelect(el);
        return true;
    }
    return false;
}

function toggleSelect(el) {
    var id = _selId(el);
    if (!id) return;
    if (_selected.has(id)) {
        _selected.delete(id);
        el.classList.remove('selected');
    } else {
        _selected.add(id);
        el.classList.add('selected');
    }
    _selectAnchor = id;
    updateSelectionBar();
}

function _selectRangeTo(el) {
    var units = _detailUnits();
    var ids = units.map(function(u) { return _unitDetailId(u); });
    var from = ids.indexOf(_selectAnchor);
    var to = ids.indexOf(_selId(el));
    if (from < 0 || to < 0) { toggleSelect(el); return; }
    var lo = Math.min(from, to), hi = Math.max(from, to);
    for (var i = lo; i <= hi; i++) {
        var id = _selId(units[i]);
        if (id && !_selected.has(id)) {
            _selected.add(id);
            units[i].classList.add('selected');
        }
    }
    _selectAnchor = _selId(el);
    updateSelectionBar();
}

/* Ctrl/Cmd+A selects every visible rendered unit: filtered-out cards aren't
   in the DOM, and units inside a collapsed section are skipped so "select
   all" matches what the user can actually see. (.collapsed covers persisted
   collapse, mid-animation collapse, and initial height:0 renders alike.) */
function selectAll() {
    if (!_editMode) return;
    _detailUnits().forEach(function(el) {
        if (el.closest('.deck-body.collapsed')) return;
        var id = _selId(el);
        if (id && !_selected.has(id)) {
            _selected.add(id);
            el.classList.add('selected');
        }
    });
    updateSelectionBar();
}
document.addEventListener('keydown', function(e) {
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'a') return;
    var t = document.activeElement;
    if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return;
    var overlay = document.getElementById('overlay');
    if (overlay && overlay.classList.contains('open')) return;
    if (!_editMode) return;
    e.preventDefault();
    selectAll();
});

function clearSelection() {
    if (!_selected || _selected.size === 0) { updateSelectionBar(); return; }
    _selected.clear();
    _selectAnchor = null;
    document.querySelectorAll('.selected').forEach(function(el) {
        el.classList.remove('selected');
    });
    updateSelectionBar();
}

/* Re-mark selected units inside *root* after a targeted DOM rebuild
   (replaceSection) — fresh elements arrive without the .selected class.
   Placeholders count too (a rebuild may collapse a selected card into one);
   inner cards of an expanded note group are not units and never match. */
function _reapplySelection(root) {
    if (_selected.size === 0) return;
    root.querySelectorAll('[data-cid], [data-group-lead], [data-lazy]')
        .forEach(function(el) {
            if (el.closest('.note-cards-body')) return;
            var id = _selId(el) || el.getAttribute('data-lazy');
            if (id && _selected.has(id)) el.classList.add('selected');
        });
}

function updateSelectionBar() {
    var bar = document.getElementById('selection-bar');
    if (!bar) return;
    var n = _selected ? _selected.size : 0;
    bar.classList.toggle('open', n > 0);
    /* Reserve space below the grid so the bar can't cover the last row. */
    document.body.classList.toggle('selection-open', n > 0);
    var count = document.getElementById('selection-count');
    if (count) count.textContent = n + ' selected';
}

function selectionAction(e, action) {
    e.stopPropagation();
    if (!_editMode || _selected.size === 0) return;
    pycmd('bulk:' + action + ':' + Array.from(_selected).join(','));
}
