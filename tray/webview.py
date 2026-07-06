"""The tray's webview subclass."""
from __future__ import annotations

from aqt.webview import AnkiWebView


class TrayWebView(AnkiWebView):
    """AnkiWebView that accepts drops only from in-app drag sources.

    The tray's own HTML5 card drags re-enter the widget as native Qt drops,
    which stock AnkiWebView refuses outright (allow_drops is False and stdHtml
    resets it). Gating on the drag *source* keeps in-page card drags working
    while external drags (files, text from other apps) can never reach the
    page — Chromium would otherwise navigate the view to a dropped file. The
    page's own dragover/drop handlers refuse foreign drags as a second layer.
    """

    def dragEnterEvent(self, evt):
        self.allow_drops = evt.source() is not None
        super().dragEnterEvent(evt)
