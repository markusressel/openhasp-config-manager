from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.bar_values import indicator_span
from openhasp_config_manager.gui.domain.meter_geometry import value_fraction
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    INDICATOR_DEFAULTS,
    TRACK_DEFAULTS,
    TRACK_PADDING,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


def indicator_rect(inner: QtCore.QRectF, progress: float, vertical: bool, start: float = 0.0) -> QtCore.QRectF:
    """
    :return: the part of the inner rect of a track that is filled: from the start to the progress, both counted from the left (the
        bottom if vertical)
    """
    if vertical:
        return QtCore.QRectF(
            inner.left(), inner.bottom() - inner.height() * progress, inner.width(), inner.height() * (progress - start)
        )
    return QtCore.QRectF(inner.left() + inner.width() * start, inner.top(), inner.width() * (progress - start), inner.height())


class HaspBarItem(EditableWidget):
    """
    A bar: the track (the main part) with its indicator (part 1) inside of the padding of the track, from `start_value` to `val`. The
    `text` of a bar is not shown on the plate, a label on top of it is.
    """

    # a slider has a `type`, a bar has none
    is_slider = False

    @property
    def progress(self) -> float:
        return value_fraction(self.data)

    @property
    def is_vertical(self) -> bool:
        return self.obj_h > self.obj_w

    def inner_rect(self) -> QtCore.QRectF:
        """The place of the indicator at 100%: the object without the padding of the main part, like LVGL."""
        left, top, right, bottom = padding(self, Part.MAIN, TRACK_PADDING)
        return self.obj_rect.adjusted(left, top, -right, -bottom)

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, Part.MAIN, TRACK_DEFAULTS))

        self.draw_indicator(painter)

        super().paint(painter, option, widget)

    def draw_indicator(self, painter):
        span = indicator_span(self.data, self.is_slider)
        if span is not None:
            draw_box(
                painter,
                indicator_rect(self.inner_rect(), span[1], self.is_vertical, start=span[0]),
                box_style(self, Part.INDICATOR, INDICATOR_DEFAULTS),
            )
