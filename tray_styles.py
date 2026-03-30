"""CSS stylesheet for the CardTray webview.

All visual styling for card frames, menus, overlays, deck sections,
state indicators, and dark-mode refinements lives here.
"""

TRAY_CSS = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
    margin: 0; padding: 0;
    background: Canvas; color: CanvasText;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.45;
}

/* ── Card frames ── */
.card-frame {
    position: relative;
    border: 1px solid color-mix(in srgb, CanvasText 14%, Canvas);
    border-radius: 8px;
    padding: 14px;
    padding-top: 34px;
    margin-bottom: 12px;
    break-inside: avoid;
    cursor: pointer;
    overflow: hidden;
    transition: box-shadow 0.2s ease, transform 0.2s ease, opacity 0.15s ease;
    transform-origin: center center;
    content-visibility: auto;
    contain-intrinsic-size: auto 200px;
}
.card-frame img { max-width: 100%; height: auto; display: block; }
.card-frame:hover {
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    transform: scale(1.03);
    z-index: 10;
}
.card-frame:active {
    transform: scale(0.98);
    transition: transform 0.1s ease;
}
.card-frame.suspended { opacity: 0.45; }

/* ── IO grouped card ── */
.io-container { position: relative; display: inline-block; max-width: 100%; overflow: hidden; line-height: 0; }
.io-container img { display: block; max-width: 100%; height: auto; }
.io-container svg { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; }
.io-badge {
    display: inline-block; font-size: 11px; color: GrayText;
    background: color-mix(in srgb, CanvasText 8%, Canvas); border-radius: 4px; padding: 2px 8px;
    margin-top: 8px;
}

/* ── Card action buttons (top-right) ── */
.card-actions {
    position: absolute; top: 6px; right: 8px;
    display: flex; align-items: center; gap: 2px;
}
.card-menu-btn {
    background: none; border: none; cursor: pointer;
    font-size: 18px; color: GrayText; padding: 2px 6px;
    border-radius: 4px; line-height: 1;
    transition: background 0.15s ease, color 0.1s ease;
}
.card-menu-btn:hover { background: color-mix(in srgb, CanvasText 10%, Canvas); color: CanvasText; }
.edit-card-btn {
    background: none; border: none; cursor: pointer;
    font-size: 14px; color: GrayText; padding: 2px 6px;
    border-radius: 4px; line-height: 1;
    transition: opacity 0.15s ease, background 0.15s ease, color 0.1s ease;
}
.edit-card-btn:hover { background: color-mix(in srgb, CanvasText 10%, Canvas); color: CanvasText; }

/* ── Card dropdown menu ── */
.card-menu {
    display: none; position: absolute; top: 30px; right: 8px;
    background: Canvas; color: CanvasText;
    border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas); border-radius: 6px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.18); z-index: 100;
    min-width: 160px; overflow: hidden;
    padding: 4px 0;
}
.card-menu.open { display: block; }
.card-menu button {
    display: block; width: 100%; padding: 7px 14px;
    border: none; background: none; text-align: left;
    cursor: pointer; font-size: 13px; color: CanvasText;
    transition: background 0.1s ease;
}
.card-menu button:hover { background: color-mix(in srgb, CanvasText 8%, Canvas); }

/* ── Overlay for expanded card ── */
#overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0);
    backdrop-filter: blur(0px); -webkit-backdrop-filter: blur(0px);
    z-index: 200;
    justify-content: center; align-items: center;
    transition: background 0.3s ease, backdrop-filter 0.3s ease, -webkit-backdrop-filter 0.3s ease;
}
#overlay.open { display: flex; }
#overlay.visible {
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
}
#overlay-card {
    background: Canvas; color: CanvasText; border-radius: 12px;
    padding: 28px; max-width: 85vw; max-height: 85vh;
    overflow: auto; position: relative;
    box-shadow: 0 8px 40px rgba(0,0,0,0.3);
    transform: scale(0.9); opacity: 0;
    transition: transform 0.25s ease, opacity 0.25s ease;
}
#overlay.visible #overlay-card {
    transform: scale(1); opacity: 1;
}
#overlay-card img { max-width: 100%; height: auto; }
#overlay-close {
    position: absolute; top: 10px; right: 14px;
    font-size: 22px; cursor: pointer; background: none;
    border: none; color: GrayText;
    transition: color 0.1s ease;
}
#overlay-close:hover { color: CanvasText; }

/* Lock scroll when overlay is open */
body.overlay-open { overflow: hidden; padding-right: var(--scrollbar-w, 0px); }

/* ── Deck sections ── */
.deck-header {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px;
    background: color-mix(in srgb, CanvasText 4%, Canvas);
    border-bottom: 1px solid color-mix(in srgb, CanvasText 10%, Canvas);
    cursor: pointer; user-select: none;
    transition: background 0.15s ease;
    position: sticky; top: 0; z-index: 50;
}
.deck-header:hover {
    background: color-mix(in srgb, CanvasText 8%, Canvas);
}
.deck-header.highlight {
    background: color-mix(in srgb, Highlight 20%, Canvas);
    transition: background 0.5s;
}
.depth-0 { padding-left: 12px; font-weight: 600; font-size: 14px; }
.depth-1 { padding-left: 28px; font-weight: 600; font-size: 13px; }
.depth-2 { padding-left: 44px; font-size: 13px; }
.depth-3 { padding-left: 60px; font-size: 13px; }
.depth-4 { padding-left: 76px; font-size: 12px; }
.collapse-arrow {
    display: inline-block; font-size: 10px;
    transition: transform 0.2s ease;
    color: GrayText;
}
.collapse-arrow.collapsed { transform: rotate(-90deg); }
.deck-name { flex: 1; min-width: 0; }
.deck-path { color: GrayText; font-size: 0.85em; }
.deck-leaf { font-weight: 600; }
.deck-info { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.card-count {
    color: GrayText; font-size: 12px; white-space: nowrap;
}
.deck-btn {
    padding: 3px 10px; border: 1px solid color-mix(in srgb, CanvasText 15%, Canvas);
    border-radius: 4px; background: Canvas; color: CanvasText;
    font-size: 11px; cursor: pointer; white-space: nowrap;
    transition: background 0.1s ease, border-color 0.1s ease;
}
.deck-btn:hover {
    background: color-mix(in srgb, CanvasText 8%, Canvas);
    border-color: color-mix(in srgb, CanvasText 25%, Canvas);
}
.deck-body {
    overflow: visible;
    transition: height 0.3s ease;
}
.deck-body.collapsed {
    overflow: hidden;
}
.deck-cards {
    column-width: 320px; column-gap: 14px;
    padding: 14px;
}
.deck-cards:empty { display: none; }

/* ── Header plus-button ── */
.root-header {
    display: flex; align-items: center; justify-content: flex-end;
    padding: 4px 14px 0;
    position: relative;
}
.header-plus-btn {
    border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas);
    border-radius: 4px;
    background: transparent;
    color: color-mix(in srgb, CanvasText 50%, Canvas);
    font-size: 18px; line-height: 1;
    width: 26px; height: 26px;
    cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    transition: border-color 0.15s, color 0.15s, background 0.15s,
               opacity 0.25s ease, visibility 0.25s ease;
    user-select: none;
    position: relative;
}
.header-plus-btn:hover {
    border-color: color-mix(in srgb, CanvasText 40%, Canvas);
    color: CanvasText;
    background: color-mix(in srgb, CanvasText 5%, Canvas);
}

/* ── Plus-button dropdown menu ── */
.plus-menu {
    display: none; position: fixed;
    background: Canvas; color: CanvasText;
    border: 1px solid color-mix(in srgb, CanvasText 18%, Canvas); border-radius: 6px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.18); z-index: 300;
    min-width: 180px; overflow: hidden;
    padding: 4px 0;
}
.plus-menu.open { display: block; }
.plus-menu button {
    display: block; width: 100%; padding: 7px 14px;
    border: none; background: none; text-align: left;
    cursor: pointer; font-size: 13px; color: CanvasText;
    transition: background 0.1s ease;
}
.plus-menu button:hover { background: color-mix(in srgb, CanvasText 8%, Canvas); }



/* ── View mode: hide edit-only elements ── */
body.view-mode .header-plus-btn {
    opacity: 0; visibility: hidden;
    pointer-events: none;
}
body.view-mode .edit-card-btn {
    opacity: 0; visibility: hidden;
    pointer-events: none;
}

/* ── Card state indicators ── */
.card-frame.state-new          { border-bottom: 3px solid var(--state-new-color); }
.card-frame.state-learn        { border-bottom: 3px solid var(--state-learn-color); }
.card-frame.state-review-due   { border-bottom: 3px solid var(--state-review-color); }
.card-frame.state-review-soon  { border-bottom: 2px dotted var(--state-review-70); }
.card-frame.state-review-mid   { border-bottom: 2px dotted var(--state-review-50); }
.card-frame.state-review-later { border-bottom: 2px dotted var(--state-review-30); }

.card-state-badge {
    position: absolute; top: 8px; left: 10px;
    display: flex; align-items: center; gap: 4px;
    font-size: 11px; line-height: 1;
    border-radius: 4px; padding: 2px 6px;
    pointer-events: none; z-index: 5;
}
.state-new .card-state-badge {
    color: var(--state-new-color);
    background: var(--state-new-bg);
}
.state-learn .card-state-badge {
    color: var(--state-learn-color);
    background: var(--state-learn-bg);
}
.state-review-due .card-state-badge {
    color: var(--state-review-color);
    background: var(--state-review-bg);
}
.state-review-soon .card-state-badge {
    color: var(--state-review-70);
    background: var(--state-review-soon-bg);
}
.state-review-mid .card-state-badge {
    color: var(--state-review-50);
    background: var(--state-review-mid-bg);
}
.state-review-later .card-state-badge {
    color: var(--state-review-30);
    background: var(--state-review-later-bg);
}
.card-state-icon { display: inline-flex; }
.card-state-text { font-weight: 600; white-space: nowrap; }

/* ── Lazy-load placeholders ── */
.card-placeholder {
    min-height: 80px;
    display: flex; align-items: center; justify-content: center;
}
.card-placeholder .placeholder-inner {
    color: GrayText; font-size: 12px;
}

/* ── Dark mode refinements ── */
@media (prefers-color-scheme: dark) {
    .card-frame:hover {
        box-shadow: 0 2px 16px rgba(0,0,0,0.35);
    }
    .card-menu, .deck-ctx-menu {
        box-shadow: 0 6px 24px rgba(0,0,0,0.4);
    }
    #overlay-card {
        box-shadow: 0 8px 48px rgba(0,0,0,0.5);
    }
}
"""
