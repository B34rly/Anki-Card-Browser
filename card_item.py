from aqt import mw
from aqt.webview import AnkiWebView, AnkiWebViewKind
from aqt.qt import QWidget, QVBoxLayout


class CardItem(QWidget):
    """A widget that renders a single card's answer via an AnkiWebView."""

    def __init__(self, card_id: int, parent=None):
        super().__init__(parent)
        self.card_id = card_id
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.web = AnkiWebView(parent=self, kind=AnkiWebViewKind.DEFAULT)
        self.web.setFixedHeight(350)
        layout.addWidget(self.web)

    def load(self):
        """Render the card HTML (called lazily)."""
        if self._loaded:
            return
        self._loaded = True
        col = mw.col
        if col is None:
            return
        card = col.get_card(self.card_id)
        self.web.stdHtml(
            f'<div style="padding:16px;">{card.answer()}</div>',
            context=self,
        )

    def cleanup(self):
        self.web.cleanup()
