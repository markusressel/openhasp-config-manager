import math
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QSlider, QToolButton, QVBoxLayout, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import MAX_ZOOM, MIN_ZOOM

# the positions of the zoom slider
ZOOM_SLIDER_STEPS = 100


def create_zoom_slider(preview) -> QSlider:
    """A slider for the zoom of a `PagePreviewWidget`, on a logarithmic scale: every step zooms by the same factor."""
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, ZOOM_SLIDER_STEPS)
    slider.setFixedWidth(UiDimensions.five * 4)
    slider.setToolTip("Zoom of the preview")
    # keep the keyboard focus on the plate, for its shortcuts
    slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def on_moved(position: int):
        preview.set_zoom(MIN_ZOOM * (MAX_ZOOM / MIN_ZOOM) ** (position / ZOOM_SLIDER_STEPS))

    def on_zoom_changed(zoom: float):
        # the zoom changed by other means: only move the handle
        slider.blockSignals(True)
        slider.setValue(round(ZOOM_SLIDER_STEPS * math.log(zoom / MIN_ZOOM) / math.log(MAX_ZOOM / MIN_ZOOM)))
        slider.blockSignals(False)

    slider.valueChanged.connect(on_moved)
    preview.zoomChanged.connect(on_zoom_changed)
    return slider


def floating_bar(
    items: List[Optional[QAction | QWidget]], with_text: List[QAction] = (), footer: Optional[QWidget] = None
) -> QFrame:
    """
    A small toolbar that floats on the preview.
    :param items: actions (shown as buttons), widgets, and None for a separator
    :param with_text: the actions that show their text next to the icon
    :param footer: a widget below the toolbar, centered
    """
    bar = QFrame()
    bar.setProperty("role", "floating")
    row = QHBoxLayout()
    column = QVBoxLayout(bar)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    column.addLayout(row)
    if footer is not None:
        column.addWidget(footer, alignment=Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(UiDimensions.half)
    row.setContentsMargins(UiDimensions.half, UiDimensions.half, UiDimensions.half, UiDimensions.half)
    row.setSpacing(UiDimensions.half)
    for item in items:
        if item is None:
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            row.addWidget(separator)
        elif isinstance(item, QAction):
            button = QToolButton()
            button.setDefaultAction(item)
            button.setAutoRaise(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            # keep the keyboard focus on the plate, for its shortcuts
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon if item in with_text else Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            # in the bar first: shown without a parent, the button would be a window of its own for a moment
            row.addWidget(button)
            # an action that is hidden hides its button
            button.setVisible(item.isVisible())
            item.changed.connect(lambda button=button, action=item: button.setVisible(action.isVisible()))
        else:
            row.addWidget(item)
    return bar
