"""Shared fixtures for the card-browser test suite.

Strategy (three levels, see docs/CONTRIBUTING.md):
  1. Pure logic (card_state, card_data, note_grouping, card_rendering) runs
     against a REAL temporary `anki.Collection` — no mocks of Anki's data layer.
  2. Widget logic (CardTray, viewer) runs with the real Qt widgets on the
     offscreen platform, but with AnkiWebView swapped for FakeWebView so every
     stdHtml/eval call is captured and assertable, and `mw` swapped for a fake
     that wraps the real collection.
  3. DOM/JS behaviour runs in a real offscreen QWebEngineView via
     tests/webview_harness.py with pycmd shimmed (see test_dom_*.py).

The add-on directory name contains a hyphen (not a valid module name), which
trips up both the plain import statement and pytest's import machinery, so the
package is loaded once under the alias `card_browser` via `addon_module`.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PKG = "card_browser"  # import alias for the hyphenated add-on dir


def _load_addon_package():
    if ADDON_PKG in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        ADDON_PKG,
        os.path.join(_ADDON_DIR, "__init__.py"),
        submodule_search_locations=[_ADDON_DIR],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ADDON_PKG] = mod
    spec.loader.exec_module(mod)


_load_addon_package()

import pytest
from anki.collection import Collection
from anki.cards import CardId
from anki.consts import (
    CARD_TYPE_REV,
    QUEUE_TYPE_REV,
)


def addon_module(name: str):
    """Import a module from the add-on package (hyphenated dir name)."""
    return importlib.import_module(f"{ADDON_PKG}.{name}")


# ── Qt application (offscreen) ──


@pytest.fixture(scope="session")
def qapp():
    # WebEngine (used by the DOM tests) must be imported and the GL attribute
    # set before the QApplication exists, so it happens here for every level.
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu"
    )
    from PyQt6 import QtWebEngineWidgets
    from aqt.qt import QApplication, Qt, QCoreApplication

    _ = QtWebEngineWidgets  # imported for its side effect (pyflakes-visible)

    QCoreApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication([sys.argv[0]])
    global QT_APP_CREATED
    QT_APP_CREATED = True
    return app


# ── Real collection with sample data ──


def add_basic_note(col, deck: str, front: str, back: str, tags=()):
    """Add a Basic note to *deck* (created if missing); returns the note."""
    did = col.decks.id(deck)
    nt = col.models.by_name("Basic")
    note = col.new_note(nt)
    note["Front"] = front
    note["Back"] = back
    note.tags = list(tags)
    col.add_note(note, did)
    return note


def make_review_card(
    col, cid: int, due_in_days: int, ivl: int = 10,
    factor: int = 2500, lapses: int = 0, reps: int = 3,
) -> None:
    """Turn a new card into a review card due in *due_in_days* days."""
    card = col.get_card(CardId(cid))
    card.queue = QUEUE_TYPE_REV
    card.type = CARD_TYPE_REV
    card.due = col.sched.today + due_in_days
    card.ivl = ivl
    card.factor = factor
    card.lapses = lapses
    card.reps = reps
    col.update_card(card)


def suspend_card(col, cid: int) -> None:
    col.sched.suspend_cards([CardId(cid)])


@pytest.fixture
def col(tmp_path):
    """A real, empty Anki collection in a temp dir."""
    c = Collection(str(tmp_path / "collection.anki2"))
    yield c
    c.close()


@pytest.fixture
def sample_col(col):
    """Collection with a small deck tree and a spread of card states.

    Parent
    ├── (own) "apple pie" (new), "banana bread" (review due, tag:baking, flag 1)
    ├── Alpha: "cherry cake" (review in 5d), "date scone" (suspended, tag:baking)
    └── Beta:  "elderberry jam" (new)
    """
    notes = {}
    notes["apple"] = add_basic_note(col, "Parent", "apple pie", "crust")
    notes["banana"] = add_basic_note(
        col, "Parent", "banana bread", "loaf", tags=["baking"]
    )
    notes["cherry"] = add_basic_note(col, "Parent::Alpha", "cherry cake", "layers")
    notes["date"] = add_basic_note(
        col, "Parent::Alpha", "date scone", "crumbly", tags=["baking"]
    )
    notes["elder"] = add_basic_note(col, "Parent::Beta", "elderberry jam", "sweet")

    cids = {k: n.card_ids()[0] for k, n in notes.items()}
    make_review_card(col, cids["banana"], due_in_days=0, lapses=2)
    col.set_user_flag_for_cards(1, [CardId(cids["banana"])])
    make_review_card(col, cids["cherry"], due_in_days=5)
    suspend_card(col, cids["date"])

    col._test_notes = notes  # handy handles for tests
    col._test_cids = cids
    return col


def pytest_sessionfinish(session, exitstatus):
    global _EXIT_STATUS
    _EXIT_STATUS = int(exitstatus)


def pytest_unconfigure(config):
    """Skip Qt/Chromium teardown at interpreter exit.

    QtWebEngine's offscreen teardown can segfault after the test run has
    already completed and reported (a known Chromium-embedding issue). By
    unconfigure time the full report including failures has printed, so exit
    hard with pytest's real status instead of letting the crash turn the run
    into a core dump.
    """
    if QT_APP_CREATED:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_EXIT_STATUS)


QT_APP_CREATED = False
_EXIT_STATUS = 0


def deck_node(col, name: str):
    """Find the DeckTreeNode for a top-level deck by name."""
    root = col.decks.deck_tree()
    for child in root.children:
        if child.name == name:
            return child
    raise LookupError(f"deck {name!r} not in tree")


# ── Fake mw + fake webview ──


class FakeAddonManager:
    def __init__(self, config=None):
        self._config = config or {}

    def getConfig(self, _name):
        return dict(self._config)


class FakeMainWindow:
    """Minimal stand-in for aqt.mw: a real collection plus inert stubs."""

    def __init__(self, col):
        self.col = col
        self.addonManager = FakeAddonManager()
        self.moved_to = []

    def moveToState(self, state):
        self.moved_to.append(state)


@pytest.fixture
def fake_mw(sample_col, monkeypatch):
    """Patch a FakeMainWindow wrapping sample_col into every add-on module.

    Auto-discovers every loaded add-on module that binds ``mw`` at import
    time, so the fixture survives file moves and package splits.
    """
    m = FakeMainWindow(sample_col)
    monkeypatch.setattr("aqt.mw", m, raising=False)
    for name, mod in list(sys.modules.items()):
        if name.startswith(ADDON_PKG) and mod is not None and hasattr(mod, "mw"):
            monkeypatch.setattr(mod, "mw", m)
    return m


@pytest.fixture
def fake_webview_cls(qapp):
    """A QWidget standing in for AnkiWebView that records stdHtml/eval calls."""
    from aqt.qt import QWidget

    class FakeWebView(QWidget):
        def __init__(self, parent=None, kind=None):
            super().__init__(parent)
            self.pages: list[str] = []       # every stdHtml body
            self.evals: list[str] = []       # every eval'd JS string
            self.bridge = None

        # AnkiWebView API used by CardTray
        def set_bridge_command(self, func, _context):
            self.bridge = func

        def stdHtml(self, html, context=None, **_kw):
            self.pages.append(html)

        def eval(self, js):
            self.evals.append(js)

        def cleanup(self):
            pass

        # test conveniences
        @property
        def page_html(self) -> str:
            return self.pages[-1] if self.pages else ""

        def evals_matching(self, prefix: str) -> list[str]:
            return [e for e in self.evals if e.startswith(prefix)]

        def reset_log(self):
            self.pages.clear()
            self.evals.clear()

    return FakeWebView


@pytest.fixture
def tray(qapp, fake_mw, fake_webview_cls, monkeypatch):
    """A CardTray wired to the sample collection, rendering deck 'Parent'."""
    tray_mod = addon_module("tray.tray")
    monkeypatch.setattr(tray_mod, "TrayWebView", fake_webview_cls)
    t = tray_mod.CardTray()
    node = deck_node(fake_mw.col, "Parent")
    t.set_deck_tree(node, "Parent")
    yield t
    t.cleanup()
