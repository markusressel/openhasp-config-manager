from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style, draw_box
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.default_theme import TRACK_DEFAULTS
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class HaspBaseObjectItem(EditableWidget):
    """
    The base object (`obj`): a rectangle that looks like a track (a dark gradient with a border). Used as the background of other
    objects; `click` 0 lets touches go through to the objects below.
    See https://www.openhasp.com/0.7.0/design/objects/obj/
    """

    def paint(self, painter, option, widget=None):
        draw_box(painter, self.obj_rect, box_style(self, defaults=TRACK_DEFAULTS))
        super().paint(painter, option, widget)
