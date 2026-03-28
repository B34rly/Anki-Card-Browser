from aqt import gui_hooks

from .viewer import open_card_viewer


def on_top_toolbar_did_init_links(links, toolbar):
    """Add a 'View' button to the main toolbar."""
    link = toolbar.create_link(
        cmd="card-viewer",
        label="View",
        func=open_card_viewer,
        tip="Open Card Viewer",
        id="card-viewer",
    )
    links.insert(3, link)


gui_hooks.top_toolbar_did_init_links.append(on_top_toolbar_did_init_links)