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
    return el.getAttribute('data-cid') || el.getAttribute('data-group-lead');
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
    var count = document.getElementById('selection-count');
    if (count) count.textContent = n + ' selected';
}

function selectionAction(e, action) {
    e.stopPropagation();
    if (!_editMode || _selected.size === 0) return;
    pycmd('bulk:' + action + ':' + Array.from(_selected).join(','));
}
