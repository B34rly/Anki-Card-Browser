"""Web asset loading for the tray page.

The page's CSS and JS live as real files under web/ (editable with proper
tooling, syntax-checkable with `node --check`). The JS is split into numbered
files concatenated in name order into one script — a single script program,
so function declarations hoist across file boundaries and only the few
top-level statements (listener registration, initial calls) are order-
sensitive.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@lru_cache(maxsize=1)
def tray_css() -> str:
    return (WEB_DIR / "tray.css").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def tray_js() -> str:
    parts = [
        p.read_text(encoding="utf-8")
        for p in sorted((WEB_DIR / "js").glob("*.js"))
    ]
    return "\n".join(parts)
