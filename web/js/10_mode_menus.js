var _editMode = false;
function setEditMode(on) {
    _editMode = on;
    document.body.classList.toggle('view-mode', !on);
    if (!on) {
        closeAllCardMenus();
        clearSelection();  /* selection is an edit-mode gesture */
    }
}
/* Python bakes _initialEditMode into the page before this script, so the page
   loads directly in the right mode (no flash of the wrong controls). */
setEditMode(typeof _initialEditMode === 'undefined' ? false : _initialEditMode);
function closeAllCardMenus() {
    document.querySelectorAll('.card-menu.open').forEach(function(m) {
        m.classList.remove('open', 'flip-up');
    });
    document.querySelectorAll('.card-frame.menu-open').forEach(function(f) {
        f.classList.remove('menu-open');
    });
}
function toggleMenu(e, id) {
    e.stopPropagation();
    var menu = document.getElementById('menu-' + id);
    if (!menu) return;
    var wasOpen = menu.classList.contains('open');
    closeAllCardMenus();
    if (wasOpen) return;  /* second click on the same button closes it */
    menu.classList.add('open');
    menu.classList.remove('flip-up');
    /* Lift every enclosing card-frame so none clips/scales the menu (note-group
       inner cards are frames nested inside the note-group frame). */
    var f = menu.parentElement;
    while (f) {
        if (f.classList && f.classList.contains('card-frame')) f.classList.add('menu-open');
        f = f.parentElement;
    }
    /* Flip above the button if the menu would overflow the viewport bottom. */
    if (menu.getBoundingClientRect().bottom > window.innerHeight - 6) {
        menu.classList.add('flip-up');
    }
}
document.addEventListener('click', function() { closeAllCardMenus(); });
function cardAction(e, action, cid) {
    e.stopPropagation();
    closeAllCardMenus();
    if (!_editMode) return;  /* view mode is read-only */
    pycmd(action + ':' + cid);
}
function editCard(e, cid) {
    /* Explicit ✎ buttons (card pencil / menu) — obeys the edit_target config. */
    e.stopPropagation();
    pycmd('edit_card:' + cid);
}
function tagClicked(e, el) {
    /* A tag pill sets the toolbar's tag filter (the Qt side owns the combo). */
    e.stopPropagation();
    if (typeof pycmd === 'function') {
        pycmd('filter_tag:' + el.getAttribute('data-tag'));
    }
}
function deleteCard(e, cid) {
    e.stopPropagation();
    closeAllCardMenus();
    if (!_editMode) return;  /* view mode is read-only */
    pycmd('delete_card:' + cid);
}
