from aqt import gui_hooks

from .core.card_data import clear_caches
from .viewer import open_card_browser


def on_top_toolbar_did_init_links(links, toolbar):
    """Add a 'Cards' button to the main toolbar."""
    link = toolbar.create_link(
        cmd="card-browser",
        label="Cards",
        func=open_card_browser,
        tip="Open Card Browser",
        id="card-browser",
    )
    links.insert(3, link)


gui_hooks.top_toolbar_did_init_links.append(on_top_toolbar_did_init_links)
# Clear per-collection caches (e.g. IO notetype lookups) when the collection
# changes, so model ids from a previous profile are never reused.
gui_hooks.collection_did_load.append(lambda col: clear_caches())