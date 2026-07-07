/* ── Toast: transient in-page feedback for completed actions ──
   Python evals showToast() from an op's success callback. Rendered inside
   the page (matching the selection bar's styling) instead of Anki's native
   yellow tooltip window, which looks foreign over the styled grid. */
var _toastTimer = null;
function showToast(msg) {
    var el = document.getElementById('toast');
    if (!el) {
        el = document.createElement('div');
        el.id = 'toast';
        document.body.appendChild(el);
    }
    el.textContent = msg;
    void el.offsetHeight;  /* commit initial state so the slide-in animates */
    el.classList.add('visible');
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function() {
        _toastTimer = null;
        el.classList.remove('visible');
    }, 2200);
}
