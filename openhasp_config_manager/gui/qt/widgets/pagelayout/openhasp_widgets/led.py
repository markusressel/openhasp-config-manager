import dataclasses

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import number
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# measured on a plate: a round light with a glow (its shadow, which doesn't follow `bg_color`) and a faint border
LED_DEFAULTS = {
    "bg_color": "#00B6FF",
    "bg_opa": 255,
    "radius": 1000,
    "border_width": 1,
    "border_color": "#FFFFFF",
    "border_opa": 30,
    "shadow_width": 15,
    "shadow_color": "#00B6FF",
}
# below this brightness the LED doesn't glow (LV_LED_BRIGHT_MIN)
_GLOW_FROM = 120


class HaspLedItem(EditableWidget):
    """
    A round light. `val` is the brightness (0 to 255, 255 if the object has none), the color comes from `bg_color`: it is mixed with
    black, so an LED with brightness 0 is not visible. A bright LED glows, the glow grows with the brightness.
    See https://www.openhasp.com/0.7.0/design/objects/led/
    """

    @property
    def brightness(self) -> float:
        """:return: how bright the LED is, 0 to 255"""
        return max(0.0, min(number(self.obj_data.get("val"), 255), 255.0))

    def paint(self, painter, option, widget=None):
        style = box_style(self, defaults=LED_DEFAULTS)
        scale = self.brightness / 255
        color = style.bg_color
        glow = max(0.0, (self.brightness - _GLOW_FROM) / (255 - _GLOW_FROM))
        style = dataclasses.replace(
            style,
            bg_color=color.fromRgbF(color.redF() * scale, color.greenF() * scale, color.blueF() * scale),
            shadow_width=style.shadow_width * glow,
            shadow_spread=style.shadow_spread * glow,
        )
        draw_box(painter, self.obj_rect, style)
        super().paint(painter, option, widget)
