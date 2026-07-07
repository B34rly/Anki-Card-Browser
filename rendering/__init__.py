"""Pure HTML builders for everything the tray renders.

Split by shape: frames (base card chrome), io_cards (Image Occlusion),
notes (field tables / note groups), detail (the inspector overlay).
This package re-exports the public surface so consumers just import
`from ..rendering import <builder>`.
"""
from .detail import (
    build_detail_actions,
    build_detail_html,
    build_editable_fields,
    build_qa_content,
    build_revlog_table,
)
from .frames import (
    FLAG_COLORS,
    build_card_menu,
    build_flag_indicator,
    build_flag_row,
    build_selection_bar,
    build_tag_strip,
    format_deck_path,
    frame_classes,
    render_normal_card,
)
from .io_cards import build_io_card_html, build_io_container, build_svg_mask
from .notes import (
    build_note_card_count,
    build_note_fields_table,
    build_note_group_html,
)

__all__ = [
    "FLAG_COLORS",
    "build_card_menu",
    "build_detail_actions",
    "build_detail_html",
    "build_editable_fields",
    "build_flag_indicator",
    "build_flag_row",
    "build_io_card_html",
    "build_io_container",
    "build_note_card_count",
    "build_note_fields_table",
    "build_note_group_html",
    "build_qa_content",
    "build_revlog_table",
    "build_selection_bar",
    "build_svg_mask",
    "build_tag_strip",
    "format_deck_path",
    "frame_classes",
    "render_normal_card",
]
