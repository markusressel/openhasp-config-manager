from collections.abc import Callable
from typing import Dict

from PyQt6 import QtCore, QtGui, QtWidgets

from openhasp_config_manager.gui.domain.style_parts import Part
from openhasp_config_manager.gui.qt.async_bridge import qBridge
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box, text_color
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import DEFAULT_RADIUS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import (
    DEFAULT_FONT_SIZE,
    line_lead,
    line_top,
    number,
    plate_font,
    set_line_space,
)
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import ClickableWidget

# how a button looks on the plate without style properties (measured): a blue gradient, orange while toggled, gray while disabled
BUTTON_DEFAULTS = {
    "bg_color": "#4ACAFF",
    "bg_grad_color": "#0081B4",
    "bg_grad_dir": 1,
    "bg_opa": 255,
    "radius": 8,
    "border_width": 1,
    "border_color": "#60CDF2",
    "border_opa": 128,
    "text_color": "#FFFFFF",
    # the theme sets these for the toggled and the disabled state, so the `bg_color` of the object doesn't change them
    "bg_color@1": "#FF9962",
    "bg_grad_color@1": "#623C29",
    "border_color@1": "#596972",
    "text_color@1": "#FFFFFF",
    "bg_color@4": "#4ACAFF",
    "bg_grad_color@4": "#0081B4",
    "border_color@4": "#444444",
    "text_color@4": "#9C999C",
    "bg_color@5": "#8C8A8C",
    "bg_grad_color@5": "#623C29",
}
# the buttons of a button matrix or message box have smaller corners
COMPACT_BUTTON_DEFAULTS = {**BUTTON_DEFAULTS, "radius": DEFAULT_RADIUS}


class HaspButtonItem(ClickableWidget):
    @property
    def text(self) -> str:
        return self.obj_data.get("text", "")

    @property
    def text_font(self):
        """The `text_font` of the object, see `plate_font`."""
        return self.obj_data.get("text_font", DEFAULT_FONT_SIZE)

    def __init__(
        self,
        obj_data: Dict,
        on_click: Callable[[Dict], None] = None,
        parent_widget=None,
    ):
        super().__init__(obj_data, parent_widget)
        self._on_click = on_click

        self.text_item = QtWidgets.QGraphicsTextItem(parent=self)
        self._setup_text()

        self.clicked.connect(self._on_button_clicked)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)

    def shape(self):
        return self.object_shape()

    @qBridge()
    def _on_button_clicked(self):
        self._on_click(self.obj_data)

    def _setup_text(self):
        """Applies Rich Text (HTML) to support both regular fonts and icons."""
        raw_text = str(self.text)
        if not raw_text:
            self.text_item.setPlainText("")
            return

        base_font = plate_font(self.text_font)

        # HTML allows per-character font switching, for the icons
        if self.parent_widget and hasattr(self.parent_widget, "_replace_unicode_with_html"):
            processed_html = self.parent_widget._replace_unicode_with_html(raw_text, base_font.pixelSize())
            self.text_item.setHtml(processed_html)
        else:
            self.text_item.setPlainText(raw_text)

        base_font.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, number(self.style("text_letter_space", 0), 0))
        self.text_item.setFont(base_font)

        lead = line_lead(base_font)
        set_line_space(self.text_item, number(self.style("text_line_space", 0), 0) + lead)

        self.text_item.setDefaultTextColor(text_color(self, Part.MAIN, BUTTON_DEFAULTS))

        # every line is centered, and text wider than the button is cut off at its edges, symmetrically
        document = self.text_item.document()
        # HTML text has a default margin
        document.setDocumentMargin(0)
        option = QtGui.QTextOption(QtCore.Qt.AlignmentFlag.AlignHCenter)
        option.setWrapMode(QtGui.QTextOption.WrapMode.NoWrap)
        document.setDefaultTextOption(option)
        self.text_item.setTextWidth(max(self.obj_w, document.idealWidth()))
        t_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (self.obj_w - t_rect.width()) / 2,
            (self.obj_h - t_rect.height()) / 2 + line_top(base_font),
        )

    def _on_data_changed(self):
        self._setup_text()

    def paint(self, painter, option, widget=None):
        """Draws the button shape in native coordinates."""
        draw_box(painter, self.obj_rect, box_style(self, defaults=BUTTON_DEFAULTS))
        super().paint(painter, option, widget)
