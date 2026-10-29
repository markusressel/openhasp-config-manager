from PyQt6 import QtCore, QtGui, QtWidgets

from openhasp_config_manager.gui.domain.source.placeholders import shown_text
from openhasp_config_manager.gui.domain.problems import geometry_value
from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, padding, text_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    line_lead,
    line_top,
    number,
    plate_font,
    set_line_space,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspLabelItem(EditableWidget):
    @property
    def text(self) -> str:
        # a placeholder like `%ip%` with an example value, like the plate shows it
        return shown_text(self.obj_data.get("text", ""))

    @property
    def text_font(self):
        """The `text_font` of the object, see `plate_font`."""
        return self.obj_data.get("text_font", DEFAULT_FONT_SIZE)

    @property
    def align(self) -> str:
        """`left`, `center` or `right`, written as the word or as 0, 1 or 2."""
        value = self.obj_data.get("align", "left")
        return {"0": "left", "1": "center", "2": "right"}.get(str(value), str(value))

    @property
    def mode(self) -> str:
        """How text that is too long is shown: `expand` (the default), `break` (wraps), `dots`, `scroll`, `loop` or `crop`."""
        return str(self.obj_data.get("mode", "expand"))

    @property
    def content_rect(self) -> QtCore.QRectF:
        left, top, right, bottom = padding(self, Part.MAIN)
        return QtCore.QRectF(0, 0, self.obj_w, self.obj_h).adjusted(left, top, -right, -bottom)

    def __init__(self, obj_data, parent_widget=None):
        # the area of the label: what its size is, unless it grows to its text (see `mode`)
        self._visual = QtCore.QRectF(0, 0, geometry_value(obj_data, "w"), geometry_value(obj_data, "h"))
        super().__init__(obj_data, parent_widget)

        # measured on a plate: the text is cut off at the edges of the content area, not of the label
        self._clip = QtWidgets.QGraphicsRectItem(parent=self)
        self._clip.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))
        self._clip.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
        self.text_item = QtWidgets.QGraphicsTextItem(parent=self._clip)
        # without the default margin of 4px around the text, it starts exactly at the top and left of the label
        self.text_item.document().setDocumentMargin(0)
        self._setup_text()

    def _setup_text(self):
        """Processes font, color, icons, and alignment."""
        self._visual = QtCore.QRectF(0, 0, self.obj_w, self.obj_h)
        raw_text = self.text
        if not raw_text:
            self.text_item.setPlainText("")
            return

        base_font = plate_font(self.text_font)
        base_font.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, number(self.style("text_letter_space", 0), 0))
        self.text_item.setFont(base_font)

        if self.mode == "dots":
            raw_text = self._with_dots(raw_text, base_font)

        if self.parent_widget and hasattr(self.parent_widget, "_replace_unicode_with_html"):
            processed_html = self.parent_widget._replace_unicode_with_html(raw_text, base_font.pixelSize())
            self.text_item.setHtml(processed_html)
        else:
            self.text_item.setPlainText(raw_text)

        self._lead = line_lead(base_font)
        set_line_space(self.text_item, number(self.style("text_line_space", 0), 0) + self._lead)

        self.text_item.setDefaultTextColor(text_color(self))
        self._align_text()

    def _with_dots(self, text: str, font: QtGui.QFont) -> str:
        """The first line of the text without what doesn't fit the label, ending with "..." (the `dots` mode)."""
        metrics = QtGui.QFontMetricsF(font)
        available = self.content_rect.width()
        if metrics.horizontalAdvance(text) <= available:
            return text
        while text and metrics.horizontalAdvance(text + "...") > available:
            text = text[:-1]
        return text.rstrip() + "..."

    def _align_text(self):
        """Positions the child text item in the content area, based on the 'align' property and the `mode`."""
        content = self.content_rect
        document = self.text_item.document()
        option = QtGui.QTextOption(
            {"center": QtCore.Qt.AlignmentFlag.AlignHCenter, "right": QtCore.Qt.AlignmentFlag.AlignRight}.get(
                self.align, QtCore.Qt.AlignmentFlag.AlignLeft
            )
        )
        option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap if self.mode == "break" else QtGui.QTextOption.WrapMode.NoWrap)
        document.setDefaultTextOption(option)
        self.text_item.setTextWidth(content.width() if self.mode == "break" else max(content.width(), document.idealWidth()))
        # the label grows to its text: wider with `expand`, higher with `break`
        left, top, right, bottom = padding(self, Part.MAIN)
        if self.mode == "expand":
            self._visual.setWidth(max(self.obj_w, document.idealWidth() + left + right))
        elif self.mode == "break":
            self._visual.setHeight(max(self.obj_h, self.text_item.boundingRect().height() + self._lead + top + bottom))
        self._clip.setRect(self._visual.adjusted(left, top, -right, -bottom))
        # the text of a label starts at the top of its content area, whatever its height (like in LVGL)
        t_rect = self.text_item.boundingRect()
        if self.mode == "break" or t_rect.width() <= content.width():
            x_pos = content.left()
        else:
            x_pos = content.left() + {
                "center": (content.width() - t_rect.width()) / 2,
                "right": content.width() - t_rect.width(),
            }.get(self.align, 0)
        self.text_item.setPos(x_pos, content.top() + line_top(self.text_item.font()))

    def _on_data_changed(self):
        self._setup_text()

    @property
    def obj_rect(self) -> QtCore.QRectF:
        return self._visual

    def shape(self):
        return self.object_shape()

    def paint(self, painter, option, widget=None):
        """Draws the background, border, outline and shadow of the label: none by default."""
        draw_box(painter, self.obj_rect, box_style(self))
        super().paint(painter, option, widget)
