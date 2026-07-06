"""Level-3 test harness: drive the tray's real DOM in an offscreen browser.

Loads the exact page HTML that CardTray pushed to its (fake) webview into a
real QWebEngineView, with `pycmd` shimmed to a JS array. Tests can then:

  * run arbitrary JS against the live DOM (`run_js`),
  * read the pycmd messages the page sent (`drain_pycmds`),
  * route those messages through a real CardTray and replay the eval()s it
    produced back into the page (`pump_bridge`) — a full Python↔JS round trip
    without Anki running,
  * grab screenshots (`screenshot`) for visual inspection.

The shim can be created "disconnected" (pycmd undefined at load) to reproduce
the QWebChannel-handshake race that left search results blank.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView

_SHIM_CONNECTED = (
    "<script>window._pycmds=[];"
    "var pycmd=function(c){window._pycmds.push(String(c));};</script>"
)
# pycmd stays undefined until connect_bridge() — like a slow webchannel
# handshake. `var pycmd` alone would still be *declared* (hoisted), matching
# the real bridge script, which declares it before the async handshake fills
# it in.
_SHIM_DISCONNECTED = "<script>window._pycmds=[];var pycmd;</script>"


def spin(ms: int) -> None:
    """Run the Qt event loop for *ms* milliseconds."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class DomPage:
    """A tray page loaded in a real (offscreen) web engine."""

    def __init__(self, body_html: str, connected: bool = True,
                 width: int = 1000, height: int = 800):
        shim = _SHIM_CONNECTED if connected else _SHIM_DISCONNECTED
        self._html = (
            f"<!doctype html><html><head><meta charset='utf-8'>{shim}</head>"
            f"<body>{body_html}</body></html>"
        )
        self.view = QWebEngineView()
        self.view.resize(width, height)
        self._loaded = False
        self.view.loadFinished.connect(self._on_loaded)
        self.view.setHtml(self._html)
        self.view.show()  # offscreen "show" — required for layout/rendering

    def _on_loaded(self, _ok: bool) -> None:
        self._loaded = True

    def wait_loaded(self, timeout_ms: int = 5000) -> None:
        waited = 0
        while not self._loaded and waited < timeout_ms:
            spin(50)
            waited += 50
        if not self._loaded:
            raise TimeoutError("page did not finish loading")
        spin(100)  # let post-load scripts (observers, layout) settle

    def run_js(self, js: str, timeout_ms: int = 5000):
        """Evaluate JS in the page and return the result (synchronously)."""
        result: dict = {}
        page = self.view.page()
        page.runJavaScript(js, lambda v: result.setdefault("v", v))
        waited = 0
        while "v" not in result and waited < timeout_ms:
            spin(25)
            waited += 25
        if "v" not in result:
            raise TimeoutError(f"JS did not return: {js[:80]}")
        return result["v"]

    def connect_bridge(self) -> None:
        """Define pycmd late — completes the simulated handshake."""
        self.run_js("pycmd=function(c){window._pycmds.push(String(c));}; true")

    def drain_pycmds(self) -> list[str]:
        """Return and clear the pycmd messages the page has sent."""
        return self.run_js("(function(){var m=window._pycmds;window._pycmds=[];return m;})()")

    def pump_bridge(self, tray, rounds: int = 12, settle_ms: int = 250) -> list[str]:
        """Route page pycmds through *tray* and replay its evals into the page.

        Runs until two consecutive rounds produce no traffic (the observer's
        first flush can take a few hundred ms after load) or *rounds* is
        exhausted. Returns every pycmd handled. The tray must use a
        FakeWebView (its `evals` list is drained here).
        """
        handled: list[str] = []
        idle_rounds = 0
        for _ in range(rounds):
            spin(settle_ms)
            cmds = self.drain_pycmds()
            if not cmds and not tray._web.evals:
                idle_rounds += 1
                if idle_rounds >= 2:
                    break
                continue
            idle_rounds = 0
            for cmd in cmds:
                handled.append(cmd)
                tray._on_bridge_cmd(cmd)
            for js in tray._web.evals:
                self.run_js(js + "; true")
            tray._web.evals.clear()
        return handled

    def screenshot(self, path: str) -> None:
        """Save a PNG of the current page rendering."""
        self.view.grab().save(path)

    def close(self) -> None:
        # Tear the view down *now*, inside a running event loop — a deferred
        # delete processed at interpreter exit segfaults inside Chromium.
        self.view.hide()
        self.view.setHtml("")
        spin(50)
        self.view.deleteLater()
        spin(50)


def js_str(value) -> str:
    """JSON-encode a value for direct embedding in a JS snippet."""
    return json.dumps(value)
