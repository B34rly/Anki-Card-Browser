/* ── Keyboard-first grid navigation ──
   Arrows move a focus ring across the visible rendered units, Enter opens
   the focused unit's detail, Space toggles selection, and single-key
   actions (s/b/e/0-7/Del) act on the focused unit through the same bulk
   bridge path as the selection bar (so group leads expand to their members
   in Python). `?` shows a shortcut cheat-sheet. All of it stands down while
   the detail overlay is open or a form control/editor has focus. */
var _kbFocusId = null;

function _kbUnits() {
    /* Same visibility rule as selectAll: filtered-out cards aren't in the
       DOM, and units inside a collapsed section aren't navigable. */
    return _detailUnits().filter(function(el) {
        return !el.closest('.deck-body.collapsed');
    });
}

function _kbEl(id) {
    if (id === null) return null;
    var units = _kbUnits();
    for (var i = 0; i < units.length; i++) {
        if (_unitDetailId(units[i]) == id) return units[i];
    }
    return null;
}

function _kbSetFocus(el) {
    document.querySelectorAll('.kb-focus').forEach(function(f) {
        f.classList.remove('kb-focus');
    });
    if (!el) { _kbFocusId = null; return; }
    _kbFocusId = _unitDetailId(el);
    el.classList.add('kb-focus');
    el.scrollIntoView({block: 'nearest'});
}

/* After a targeted DOM rebuild the focused element is a fresh node — re-mark
   it (mirrors _reapplySelection; called from fillCards/_swapUnit/
   replaceSection). *root* may itself be the focused unit. */
function _reapplyKbFocus(root) {
    if (_kbFocusId === null || !root || !root.querySelectorAll) return;
    var els = [root].concat(Array.prototype.slice.call(
        root.querySelectorAll('[data-cid], [data-group-lead], [data-lazy]')));
    els.forEach(function(el) {
        if (!el.closest || el.closest('.note-cards-body')) return;
        if (_unitDetailId(el) == _kbFocusId) el.classList.add('kb-focus');
    });
}

function _kbMove(dx, dy) {
    var units = _kbUnits();
    if (!units.length) return;
    var cur = _kbEl(_kbFocusId);
    if (!cur) {
        /* No ring yet (or its unit vanished): start at the first unit in or
           below the viewport. */
        for (var i = 0; i < units.length; i++) {
            if (units[i].getBoundingClientRect().bottom > 0) {
                _kbSetFocus(units[i]);
                return;
            }
        }
        _kbSetFocus(units[0]);
        return;
    }
    if (dx) {
        var next = units[units.indexOf(cur) + dx];
        if (next) _kbSetFocus(next);
        return;
    }
    /* Vertical: nearest unit whose centre lies in the travel direction —
       the variable-width grid has no fixed columns to index into, so use
       geometry (horizontal drift is penalised so the ring tracks the same
       visual column where one exists). */
    var r = cur.getBoundingClientRect();
    var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    var best = null, bestScore = Infinity;
    units.forEach(function(el) {
        if (el === cur) return;
        var b = el.getBoundingClientRect();
        var ex = b.left + b.width / 2, ey = b.top + b.height / 2;
        var vy = (ey - cy) * dy;  /* progress along the travel direction */
        if (vy <= 1) return;
        var score = vy * vy + (ex - cx) * (ex - cx) * 4;
        if (score < bestScore) { bestScore = score; best = el; }
    });
    if (best) _kbSetFocus(best);
}

function _kbOpen(el) {
    if (typeof pycmd !== 'function') return;
    if (el.hasAttribute('data-group-lead')) {
        pycmd('note_detail:' + _unitDetailId(el));
    } else {
        /* Python re-dispatches group leads to the right detail kind. */
        pycmd('card_detail:' + _unitDetailId(el));
    }
}

/* ── Shortcut cheat-sheet (?) ── */
function _kbHelpRows() {
    return [
        ['← → ↑ ↓', 'Move focus'],
        ['Enter', 'Open detail'],
        ['Space', 'Select / deselect'],
        ['Ctrl+A', 'Select all visible'],
        ['Esc', 'Close / clear'],
        ['s · b', 'Suspend · bury (toggles)'],
        ['1–7 · 0', 'Flag · clear flag'],
        ['e', 'Edit card'],
        ['Del', 'Delete'],
        ['Ctrl+F or /', 'Search'],
        ['? ', 'This help'],
        ['← / → in detail', 'Previous / next card'],
        ['Ctrl+Enter in detail', 'Save fields'],
    ];
}

function toggleKbHelp(show) {
    var el = document.getElementById('kb-help');
    if (!el) {
        el = document.createElement('div');
        el.id = 'kb-help';
        var rows = _kbHelpRows().map(function(r) {
            return '<tr><td><kbd>' + r[0] + '</kbd></td><td>' + r[1] + '</td></tr>';
        }).join('');
        el.innerHTML = '<div class="kb-card"><h3>Keyboard shortcuts</h3>' +
            '<table>' + rows + '</table></div>';
        el.addEventListener('click', function() { toggleKbHelp(false); });
        document.body.appendChild(el);
    }
    var on = (typeof show === 'boolean') ? show : !el.classList.contains('open');
    el.classList.toggle('open', on);
}

document.addEventListener('keydown', function(e) {
    var t = document.activeElement;
    if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return;
    var overlay = document.getElementById('overlay');
    if (overlay && overlay.classList.contains('open')) return;
    var help = document.getElementById('kb-help');
    if (help && help.classList.contains('open')) {
        if (e.key === 'Escape' || e.key === '?') {
            e.preventDefault();
            toggleKbHelp(false);
        }
        return;  /* the sheet swallows everything else */
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;  /* Ctrl+A/F live elsewhere */
    switch (e.key) {
        case 'ArrowRight': e.preventDefault(); _kbMove(1, 0); return;
        case 'ArrowLeft': e.preventDefault(); _kbMove(-1, 0); return;
        case 'ArrowDown': e.preventDefault(); _kbMove(0, 1); return;
        case 'ArrowUp': e.preventDefault(); _kbMove(0, -1); return;
        case '?': e.preventDefault(); toggleKbHelp(true); return;
        case 'Escape': _kbSetFocus(null); return;  /* 20_overlay clears selection */
    }
    var el = _kbEl(_kbFocusId);
    if (!el) return;
    if (e.key === 'Enter') { e.preventDefault(); _kbOpen(el); return; }
    if (!_editMode || typeof pycmd !== 'function') return;
    if (e.key === ' ') { e.preventDefault(); toggleSelect(el); return; }
    /* Action keys route through the bulk path so Python expands group leads
       to their member cards, exactly like the selection bar. With an active
       selection they act on it (the focused unit is the toggle cue);
       otherwise on the focused unit alone. */
    var ids = (_selected && _selected.size > 0)
        ? Array.from(_selected).join(',')
        : _unitDetailId(el);
    if (e.key >= '0' && e.key <= '7') { pycmd('bulk:flag_' + e.key + ':' + ids); return; }
    if (e.key === 'Delete') { pycmd('bulk:delete:' + ids); return; }
    switch (e.key.toLowerCase()) {
        case 's':
            pycmd('bulk:' + (el.classList.contains('suspended') ? 'unsuspend' : 'suspend') + ':' + ids);
            return;
        case 'b':
            pycmd('bulk:' + (el.classList.contains('buried') ? 'unbury' : 'bury') + ':' + ids);
            return;
        case 'e':
            pycmd('edit_card:' + _unitDetailId(el));
            return;
    }
});
