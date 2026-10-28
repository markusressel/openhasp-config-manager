import dataclasses

from PyQt6 import QtCore, QtGui

from openhasp_config_manager.gui.domain.interaction import DRAG_LIMIT
from openhasp_config_manager.gui.domain.roller_scroll import SNAP_TIME, clicked_option, drag_offset, settled_option
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import (
    GRADIENT_VERTICAL,
    box_style,
    capped_radius,
    draw_box,
    resolve,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import (
    DEFAULT_RADIUS,
    INDICATOR_DEFAULTS,
    TRACK_DEFAULTS,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    DEFAULT_TEXT,
    draw_text,
    number,
    option_lines,
    plate_font,
    selected_index,
    to_color,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# measured on a plate: the height of a row is this many pixels per pixel of the font and this many on top (45 for font 24, 31 for 12)
_ROW_PER_FONT_PIXEL = 1.167
_ROW_EXTRA = 17
# the space between the text and the left and right edge of the roller
_TEXT_PADDING = 8
# the selected row (part 5): the blue of the indicator, with square corners
_SELECTED_DEFAULTS = {**INDICATOR_DEFAULTS, "radius": 0, "bg_color@2": "#18BEFF", "text_color@2": "#FFFFFF"}


class HaspRollerItem(EditableWidget):
    """
    A list of `options` with the selected one (`val`) in the middle, highlighted. With `rows` the height follows the rows and the
    font (`h` is ignored), without it `h` is the height and the list is cut off at the edges. In mode 1 (infinite) the list wraps around.
    Touched, the rows follow a finger that drags them and snap to the nearest option when it is let go (200 ms, linear); a touch
    without dragging selects the row that was touched. Neither sends an action, like on the plate.
    See https://www.openhasp.com/0.7.0/design/objects/roller/
    """

    def __init__(self, *args, **kwargs):
        # how far the rows are moved from where the selected option is in the middle, while dragged or snapping
        self._offset = 0.0
        self._press_y = 0.0
        self._dragging = False
        self._anim = None
        super().__init__(*args, **kwargs)

    @property
    def infinite(self) -> bool:
        return int(number(self.obj_data.get("mode"), 0)) == 1

    @property
    def option_count(self) -> int:
        return len(option_lines(self.obj_data.get("options")))

    @property
    def keeps_press(self) -> bool:
        # the finger can drag the rows from anywhere on, so it can't be known where it left the roller for good
        return True

    def _stop_animation(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim = None

    def _set_offset(self, value):
        self._offset = float(value)
        self.update()

    def _snap_to(self, option: int, from_offset: float):
        """Select an option and let the rows move to it: the rows are where they were, so the offset starts relative to the new option."""
        selected = selected_index(self.data)
        if self.infinite and self.option_count:
            # the nearest way round
            half = self.option_count / 2
            step = (option - selected + half) % self.option_count - half
            start = from_offset + step * self.row_height
        else:
            start = from_offset + (option - selected) * self.row_height
        self.runtime.set(self.key, "val", option, self.obj_data)
        self.follow_group(option, self.option_count)
        self._stop_animation()
        self._offset = start
        animation = QtCore.QVariantAnimation(self)
        animation.setStartValue(float(start))
        animation.setEndValue(0.0)
        animation.setDuration(round(SNAP_TIME * 1000))
        animation.valueChanged.connect(self._set_offset)
        self._anim = animation
        animation.start()
        self.runtime_changed()

    def finish_animation(self):
        """Let the rows arrive at once (tests don't wait for time)."""
        self._stop_animation()
        self._offset = 0.0
        self.update()

    def on_press(self, point):
        # a new touch stops the rows where they are (`lv_anim_del`)
        self._stop_animation()
        self._press_y = point[1]
        self._dragging = False
        self.set_pressed(True)

    def on_pressing(self, point):
        travel = point[1] - self._press_y
        if not self._dragging and abs(travel) >= DRAG_LIMIT:
            self._dragging = True
        if self._dragging:
            self._set_offset(drag_offset(travel))

    def on_release(self, point, short_click: bool):
        self.set_pressed(False)
        count = self.option_count
        if not count:
            self._dragging = False
            return
        if self._dragging:
            self._dragging = False
            option = settled_option(selected_index(self.data), self._offset, self.row_height, count, self.infinite)
            self._snap_to(option, self._offset)
            return
        local = self.mapFromScene(QtCore.QPointF(point[0], point[1]))
        if not self.hit(local):
            return
        option = clicked_option(
            selected_index(self.data), local.y(), self.obj_h, self._offset, self.row_height, count, self.infinite
        )
        self._snap_to(option, self._offset)

    def on_press_lost(self):
        self._dragging = False
        self.set_pressed(False)

    @property
    def rows(self):
        """:return: the number of visible rows if the object says so, else None"""
        return max(int(number(self.obj_data["rows"], 3)), 1) if "rows" in self.obj_data else None

    @property
    def font(self) -> QtGui.QFont:
        return plate_font(self.style("text_font", DEFAULT_FONT_SIZE))

    @property
    def row_height(self) -> float:
        return self.font.pixelSize() * _ROW_PER_FONT_PIXEL + _ROW_EXTRA

    @property
    def obj_h(self) -> int:
        rows = self.rows
        return round(rows * self.row_height) if rows else super().obj_h

    def entry_rows(self):
        """:return: (top of the row, entry or None, whether it is the selected one) for every row that is at least partly visible"""
        options = option_lines(self.obj_data.get("options"))
        selected = selected_index(self.data)
        infinite = int(number(self.obj_data.get("mode"), 0)) == 1
        middle = self.obj_h / 2 - self.row_height / 2
        reach = int(self.obj_h // self.row_height) + 3
        result = []
        for offset in range(-reach, reach + 1):
            top = middle + offset * self.row_height + self._offset
            if top + self.row_height <= 1 or top >= self.obj_h - 1:
                continue
            index = selected + offset
            if infinite and options:
                index %= len(options)
            result.append((top, options[index] if 0 <= index < len(options) else None, offset == 0))
        return result

    def _draw_mirrored_gradient(self, painter, style):
        """Measured on a plate: the background goes from `bg_color` at the top and at the bottom to `bg_grad_color` in the middle."""
        rect = self.obj_rect
        radius = capped_radius(rect, style.radius)
        painter.save()
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        painter.setClipPath(clip)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        edge, middle = QtGui.QColor(style.bg_color), QtGui.QColor(style.bg_grad_color)
        edge.setAlphaF(style.bg_opa)
        middle.setAlphaF(style.bg_opa)
        for top, bottom, from_top in ((rect.top(), rect.center().y(), True), (rect.center().y(), rect.bottom(), False)):
            gradient = QtGui.QLinearGradient(0, top if from_top else bottom, 0, bottom if from_top else top)
            gradient.setColorAt(0, edge)
            gradient.setColorAt(1, middle)
            painter.setBrush(QtGui.QBrush(gradient))
            painter.drawRect(QtCore.QRectF(rect.left(), top, rect.width(), bottom - top))
        painter.restore()

    def paint(self, painter, option, widget=None):
        main = box_style(self, Part.MAIN, TRACK_DEFAULTS)
        # the background and shadow are below the rows, the border and outline above them
        background = dataclasses.replace(main, border_width=0, outline_width=0)
        frame = dataclasses.replace(main, bg_opa=0, shadow_width=0)
        if main.bg_grad_dir == GRADIENT_VERTICAL and main.bg_opa > 0:
            self._draw_mirrored_gradient(painter, main)
            background = dataclasses.replace(background, bg_opa=0)
        draw_box(painter, self.obj_rect, background)

        painter.save()
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(self.obj_rect, DEFAULT_RADIUS, DEFAULT_RADIUS)
        painter.setClipPath(clip)
        align = self.obj_data.get("align", "center")
        color = to_color(self.style("text_color"), DEFAULT_TEXT)
        # the band of the selected option stays in the middle, the rows move under it
        band = QtCore.QRectF(0, self.obj_h / 2 - self.row_height / 2, self.obj_w, self.row_height)
        draw_box(
            painter,
            band.adjusted(main.border_width, 0, -main.border_width, 0),
            box_style(self, Part.SELECTED, _SELECTED_DEFAULTS),
        )
        selected_color = to_color(resolve(self, "text_color", Part.SELECTED, _SELECTED_DEFAULTS), color.name())
        outside = QtGui.QPainterPath()
        outside.addRect(self.obj_rect)
        inside = QtGui.QPainterPath()
        inside.addRect(band)
        for area, row_color in ((outside.subtracted(inside), color), (inside, selected_color)):
            painter.save()
            painter.setClipPath(area.intersected(clip))
            for top, entry, _ in self.entry_rows():
                if entry is not None:
                    row = QtCore.QRectF(0, top, self.obj_w, self.row_height)
                    draw_text(painter, row.adjusted(_TEXT_PADDING, 0, -_TEXT_PADDING, 0), entry, row_color, self.font, align)
            painter.restore()
        painter.restore()
        draw_box(painter, self.obj_rect, frame)
        super().paint(painter, option, widget)
