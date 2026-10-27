from enum import Enum
from typing import Dict, List, Tuple

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions


class OverlayAnchor(Enum):
    """Where a floating bar sits on the preview (see `PagePreviewWidget.add_overlay`)."""

    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


def overlay_layout(
    overlays: List[Tuple[QWidget, OverlayAnchor]], width: int, height: int
) -> Tuple[Dict[QWidget, QPoint], int, int]:
    """
    Where the floating bars go in a view of the given size: the top left and top right ones in their corners (the left one below the right one if they don't fit next to each other), the bottom right one in its corner, and the bottom
    center one centered next to it, or in a row above it if they don't fit next to each other.
    :return: the position of each bar, and the height of the rows above and below the plate
    """
    margin = UiDimensions.one
    positions = {}
    top_row_bottom = 0
    bottom_row_top = height
    right_edge = width - margin
    top_right_x = width
    visible = [(widget, anchor) for widget, anchor in overlays if not widget.isHidden()]
    for widget, anchor in visible:
        widget.adjustSize()
        x = max(margin, width - widget.width() - margin)
        if anchor == OverlayAnchor.TOP_RIGHT:
            positions[widget] = QPoint(x, margin)
            top_row_bottom = max(top_row_bottom, margin + widget.height())
            top_right_x = x
        elif anchor == OverlayAnchor.BOTTOM_RIGHT:
            y = height - widget.height() - margin
            positions[widget] = QPoint(x, y)
            right_edge = min(right_edge, x - margin)
            bottom_row_top = min(bottom_row_top, y)
    for widget, anchor in visible:
        if anchor == OverlayAnchor.TOP_LEFT:
            if margin + widget.width() + margin <= top_right_x:
                y = margin
            else:
                # no room next to the bar on the right: below it
                y = top_row_bottom + margin if top_row_bottom else margin
            positions[widget] = QPoint(margin, y)
            top_row_bottom = max(top_row_bottom, y + widget.height())
    left_edge = margin
    for widget, anchor in visible:
        if anchor == OverlayAnchor.BOTTOM_LEFT:
            y = height - widget.height() - margin
            positions[widget] = QPoint(margin, y)
            left_edge = max(left_edge, margin + widget.width() + margin)
            bottom_row_top = min(bottom_row_top, y)
    last_row_top = bottom_row_top
    for widget, anchor in visible:
        if anchor == OverlayAnchor.BOTTOM_CENTER:
            x = min((width - widget.width()) // 2, right_edge - widget.width())
            y = height - widget.height() - margin
            if x < left_edge:
                # no room next to the bar on the right: above it
                x = max(margin, (width - widget.width()) // 2)
                y = last_row_top - margin - widget.height()
            positions[widget] = QPoint(x, y)
            bottom_row_top = min(bottom_row_top, y)
    top = top_row_bottom + margin if top_row_bottom else 0
    bottom = height - bottom_row_top + margin if bottom_row_top < height else 0
    return positions, top, bottom
