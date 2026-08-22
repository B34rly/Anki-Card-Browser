from __future__ import annotations

from aqt import mw, gui_hooks
from aqt.qt import (
    QKeySequence,
    QMainWindow,
    QShortcut,
    Qt,
)

from .widget import CardBrowserWidget

# ── Window mode ──


class CardBrowserWindow(QMainWindow):
    """Standalone floating window wrapping CardBrowserWidget."""

    _instance: CardBrowserWindow | None = None

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Card Browser")
        self.resize(1100, 750)
        self._widget = CardBrowserWidget(self)
        self.setCentralWidget(self._widget)
        # No Anki menu bar in a standalone window — provide the standard
        # undo/redo shortcuts directly. (Embedded mode inherits mw's Edit
        # menu, so adding them there would make the shortcut ambiguous.)
        undo_sc = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_sc.activated.connect(self._widget.trigger_undo)
        redo_sc = QShortcut(QKeySequence.StandardKey.Redo, self)
        redo_sc.activated.connect(self._widget.trigger_redo)

    def closeEvent(self, a0):
        CardBrowserWindow._instance = None
        self._widget.cleanup()
        super().closeEvent(a0)


def open_card_browser_window():
    """Open the Card Browser as a standalone window (singleton)."""
    if CardBrowserWindow._instance is None:
        CardBrowserWindow._instance = CardBrowserWindow(mw)
    CardBrowserWindow._instance.show()
    CardBrowserWindow._instance.activateWindow()
    # Refresh the top-level deck dropdown (a deck may have been added/removed);
    # this is a no-op render when the selection is unchanged.
    CardBrowserWindow._instance._widget._populate_combo()


# ── Embedded mode ──


class EmbeddedBrowser:
    """Manages showing/hiding the CardBrowserWidget inside Anki's main window."""

    _instance: EmbeddedBrowser | None = None

    def __init__(self) -> None:
        self._widget: CardBrowserWidget | None = None
        self._active = False
        # This is a lifetime singleton (the widget is created once and reused), so
        # these hooks are registered exactly once and never need removing.
        gui_hooks.state_will_change.append(self._on_state_will_change)
        # After an op (e.g. editing a card) Anki re-renders its own screen into
        # mw.web and re-shows it on top of us. These post-render hooks fire *after*
        # that show, so re-hiding here reliably keeps us in front — whether the
        # browser was opened over the deck list or a deck's overview.
        gui_hooks.deck_browser_did_render.append(self._reassert)
        gui_hooks.overview_did_refresh.append(self._reassert)

    def show(self) -> None:
        if self._widget is None:
            self._widget = CardBrowserWidget(mw)
            mw.mainLayout.addWidget(self._widget)

        # Hide Anki's own content areas and bring ours to the front. bottomWeb
        # needs a *real* Qt hide (setVisible): its own hide() merely collapses the
        # height to 1px, and Anki re-expands it asynchronously after every render
        # (BottomBar.draw / moveToState → adjustHeightToFit → setFixedHeight lands
        # a turn later, after our render hooks), which flashed the bottom toolbar
        # ("Get Shared / Create Deck / Import File") back over us. A setVisible
        # widget is dropped from the layout and ignores that deferred height change.
        mw.web.hide()
        mw.bottomWeb.setVisible(False)
        self._widget.show()
        self._widget.raise_()
        self._active = True

        # Refresh content (deck list may have changed)
        self._widget._populate_combo()

    def hide(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._widget is not None:
            self._widget.hide()
        # Restore Anki's own content areas. bottomWeb was Qt-hidden via setVisible,
        # so make it visible again and let its height re-fit to content.
        mw.web.show()
        mw.bottomWeb.setVisible(True)
        mw.bottomWeb.show()

    def _reassert(self, *args) -> None:
        """Keep our widget in front if Anki re-rendered its deck browser over us."""
        if self._active and self._widget is not None:
            mw.web.hide()
            mw.bottomWeb.setVisible(False)
            self._widget.raise_()

    def _on_state_will_change(self, new_state: str, old_state: str) -> None:
        # When Anki transitions to any standard state, hide viewer
        if self._active:
            self.hide()

    def teardown(self) -> None:
        """Destroy the widget (profile close) so no stale collection state
        survives into the next profile. The singleton and its hooks remain;
        they no-op until show() builds a fresh widget."""
        self.hide()
        if self._widget is not None:
            self._widget.cleanup()
            self._widget.deleteLater()
            self._widget = None


def open_card_browser_embedded():
    """Show the browser inside Anki's main window."""
    if EmbeddedBrowser._instance is None:
        EmbeddedBrowser._instance = EmbeddedBrowser()
    EmbeddedBrowser._instance.show()


def open_card_browser():
    """Open the Card Browser using the configured mode."""
    conf = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    mode = conf.get("mode", "embedded")
    if mode == "window":
        open_card_browser_window()
    else:
        open_card_browser_embedded()


def _on_profile_will_close() -> None:
    """Tear down any open browser UI before the collection goes away.

    Both hosts hold references into the closing collection (deck tree nodes,
    card-id snapshots, hooks); a fresh widget is built on next open.
    """
    if CardBrowserWindow._instance is not None:
        CardBrowserWindow._instance.close()
    if EmbeddedBrowser._instance is not None:
        EmbeddedBrowser._instance.teardown()


gui_hooks.profile_will_close.append(_on_profile_will_close)
