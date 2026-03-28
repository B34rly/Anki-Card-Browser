from __future__ import annotations

from collections.abc import Sequence

from aqt import mw
from aqt.webview import AnkiWebView, AnkiWebViewKind
from aqt.qt import (
    QWidget,
    QVBoxLayout,
    QLabel,
)


class CardTray(QWidget):
    """Displays cards in a single AnkiWebView, like Anki's own deck view."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header label
        self._header = QLabel(title)
        self._header.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 8px 4px;"
        )
        layout.addWidget(self._header)

        # Single web view for all cards
        self._web = AnkiWebView(parent=self, kind=AnkiWebViewKind.DEFAULT)
        layout.addWidget(self._web)

    @property
    def title(self) -> str:
        return self._header.text()

    @title.setter
    def title(self, value: str):
        self._header.setText(value)

    def set_cards(self, card_ids: Sequence[int]) -> None:
        """Render all cards as HTML in the single web view."""
        col = mw.col
        if col is None:
            self._web.stdHtml("<p>No collection loaded.</p>")
            return

        if not card_ids:
            self._web.stdHtml("<p>No cards in this deck.</p>")
            return

        parts: list[str] = []
        for cid in card_ids:
            card = col.get_card(cid)
            answer_html = card.answer()
            parts.append(
                f'<div class="card-frame">{answer_html}</div>'
            )

        body = "\n".join(parts)
        self._web.stdHtml(
            f"""
            <style>
                body {{ margin: 0; padding: 16px; }}
                .card-frame {{
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 16px;
                    margin-bottom: 12px;
                    overflow: hidden;
                }}
            </style>
            {body}
            """,
            context=self,
        )

    def cleanup(self) -> None:
        self._web.cleanup()

    def cleanup(self):
        self._clear()
