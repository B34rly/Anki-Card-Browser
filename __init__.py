from aqt import gui_hooks

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