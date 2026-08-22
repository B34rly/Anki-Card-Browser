/* ── Search-term highlighting + keyboard access to the search box ──
   _searchTerm is baked into the page by Python and is non-empty only for
   plain substring searches (Anki-syntax queries are expressions — the typed
   text is not what matched). Highlighting wraps matches in text nodes with
   <mark class="search-hit">, so card markup is never re-parsed or broken;
   call sites re-run it for HTML that arrives after load (lazy fills,
   targeted replaces). */

function highlightMatches(root) {
    /* Every caller passes a wrapper (body, a unit frame, a section, a
       note-cards container) — .card-content is always a descendant. */
    if (!window._searchTerm || !root) return;
    var term = _searchTerm.toLowerCase();
    root.querySelectorAll('.card-content').forEach(function(el) {
        _highlightIn(el, term);
    });
}

function _highlightIn(container, term) {
    /* Collect first, then mutate — splitting while walking skips nodes. */
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) {
        if (n.nodeValue && n.nodeValue.toLowerCase().indexOf(term) !== -1) {
            nodes.push(n);
        }
    }
    nodes.forEach(function(node) {
        var parent = node.parentNode;
        if (!parent) return;
        /* Already-marked text (re-run after a targeted replace) stays as is. */
        if (parent.classList && parent.classList.contains('search-hit')) return;
        var text = node.nodeValue;
        var lower = text.toLowerCase();
        var frag = document.createDocumentFragment();
        var pos = 0, idx;
        while ((idx = lower.indexOf(term, pos)) !== -1) {
            if (idx > pos) frag.appendChild(document.createTextNode(text.slice(pos, idx)));
            var mark = document.createElement('mark');
            mark.className = 'search-hit';
            mark.textContent = text.slice(idx, idx + term.length);
            frag.appendChild(mark);
            pos = idx + term.length;
        }
        if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
        parent.replaceChild(frag, node);
    });
}

/* Ctrl/Cmd+F or / while the grid has focus → focus the Qt search box.
   The toolbar lives on the Qt side, so this goes through the bridge; the
   viewer widget owns the matching QShortcut for when Qt has focus. */
document.addEventListener('keydown', function(e) {
    var t = document.activeElement;
    if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return;
    var ctrlF = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f';
    var slash = e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey;
    if (!ctrlF && !slash) return;
    if (typeof pycmd !== 'function') return;
    e.preventDefault();
    pycmd('focus_search:1');
});

/* Initial pass over everything the full render mounted (search mode renders
   matches eagerly, so this covers the common case in one go). */
if (window._searchTerm) highlightMatches(document.body);
