from typing import Dict, List, Optional

from PyQt6 import QtGui, QtCore, QtWidgets
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from openhasp_config_manager.gui.domain.draft.page_objects import is_hidden
from openhasp_config_manager.gui.domain.problems import geometry_value
from openhasp_config_manager.gui.domain.style_parts import Part, State, style_key
from openhasp_config_manager.gui.qt.theme import current_colors

# the opacity of objects that are hidden on the plate
HIDDEN_OPACITY = 0.3
# the opacity of objects that are not highlighted, while the objects of a file are (on top of HIDDEN_OPACITY)
DIMMED_OPACITY = 0.25
# the space around an object that is part of its bounding rect, for the pen width of the selection outline (prevents smearing)
SELECTION_MARGIN = 3


# the states whose style properties apply in a state, in the order of precedence (like LVGL: the most specific state wins)
_STATE_FALLBACK: Dict[State, List[State]] = {
    State.DEFAULT: [State.DEFAULT],
    State.TOGGLED: [State.TOGGLED, State.DEFAULT],
    State.PRESSED: [State.PRESSED, State.DEFAULT],
    State.PRESSED_TOGGLED: [State.PRESSED_TOGGLED, State.PRESSED, State.TOGGLED, State.DEFAULT],
    State.DISABLED: [State.DISABLED, State.DEFAULT],
    State.DISABLED_TOGGLED: [State.DISABLED_TOGGLED, State.DISABLED, State.TOGGLED, State.DEFAULT],
}


def state_fallback(state: State) -> List[State]:
    """:return: the states whose style properties apply in a state, the most specific first"""
    return _STATE_FALLBACK[state]


def _is_true(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).lower() not in ("false", "0", "")


class EditableWidget(QGraphicsObject):
    @property
    def obj_data(self):
        return self._object_data

    @property
    def obj_id(self):
        return self.obj_data.get("id", 0)

    @property
    def obj_x(self) -> int:
        return geometry_value(self.obj_data, "x")

    @property
    def obj_y(self) -> int:
        return geometry_value(self.obj_data, "y")

    @property
    def obj_w(self) -> int:
        return geometry_value(self.obj_data, "w")

    @property
    def obj_h(self) -> int:
        return geometry_value(self.obj_data, "h")

    @property
    def is_toggled(self) -> bool:
        """Whether the object is checked: a switch or checkbox that is on, a button that toggles and is on."""
        obj = self.obj_data.get("obj")
        if obj in ("switch", "checkbox"):
            return _is_true(self.obj_data.get("val"), False)
        return obj == "btn" and _is_true(self.obj_data.get("toggle"), False) and _is_true(self.obj_data.get("val"), False)

    @property
    def is_enabled(self) -> bool:
        return _is_true(self.obj_data.get("enabled"), True)

    @property
    def state(self) -> State:
        """The state the plate draws the object in: the style properties of this state (and the ones it falls back to) apply."""
        if self.is_enabled:
            return State.TOGGLED if self.is_toggled else State.DEFAULT
        return State.DISABLED_TOGGLED if self.is_toggled else State.DISABLED

    def own_style(self, name: str, part: Part, state: State):
        """:return: the value of a style property of the object for exactly this part and state, None if it has none"""
        data = self.obj_data
        if part == Part.MAIN and state == State.DEFAULT and name in data:
            return data[name]
        return data.get(style_key(name, part, state))

    def style(self, name: str, default=None, part: Part = Part.MAIN, state: Optional[State] = None):
        """
        :param name: a style property without suffix, e.g. `bg_color`
        :param part: the part of the object the style is for: the key is `<name><part><state>`, e.g. `bg_color20` is the color of
            the knob (`Part.KNOB`) in the default state. `radius` and `radius00` are the same, see `style_parts.py`.
        :param state: the state to look up, the state of the object (`state`) by default. The properties of the states it falls back to
            apply as well, e.g. `bg_color` for a disabled object without `bg_color04`.
        :return: the value of the property for a part and state, `default` if the object has none
        """
        for candidate in state_fallback(self.state if state is None else state):
            found = self.own_style(name, part, candidate)
            if found is not None:
                return found
        return default

    def __init__(self, obj_data: Dict, parent_widget=None):
        """
        :param obj_data: the rendered object (it belongs to the draft, see PlateSession)
        :param parent_widget: the preview the item is drawn in (`PagePreviewWidget`), for icons and the other objects of the page
        """
        self._object_data = obj_data
        self._dimmed = False
        self.parent_widget = parent_widget
        super().__init__()

        # itemChange() is only called for position changes with this flag, it is needed for snapping
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Initial sync: Move the item to the position defined in the JSON data
        self.setPos(float(self.obj_x), float(self.obj_y))
        self._update_hidden()

    def refresh(self):
        """
        Redraw the object after its data changed (the data belongs to the draft, see PlateSession).
        """
        # the bounding rect depends on w and h
        self.prepareGeometryChange()
        self.setPos(float(self.obj_x), float(self.obj_y))
        self._update_hidden()
        self._on_data_changed()
        self.update()

    def set_dimmed(self, dimmed: bool):
        """Dim the object, e.g. while the objects of another file are highlighted."""
        self._dimmed = dimmed
        self._update_hidden()

    def _update_hidden(self):
        # hidden objects stay selectable and editable, but are dimmed
        opacity = HIDDEN_OPACITY if is_hidden(self.obj_data) else 1.0
        self.setOpacity(opacity * (DIMMED_OPACITY if self._dimmed else 1.0))

    def _on_data_changed(self):
        """
        Called after a property changed. Subclasses that derive child items or state from the data
        (text items, images, values) update them here.
        """

    @property
    def live_x(self) -> int:
        """The current X position in the scene (after user drag)."""
        return int(self.pos().x())

    @property
    def live_y(self) -> int:
        """The current Y position in the scene (after user drag)."""
        return int(self.pos().y())

    @property
    def delta_x(self) -> int:
        """How far the widget has moved from its original data point."""
        return self.live_x - self.obj_x

    @property
    def delta_y(self) -> int:
        """How far the widget has moved from its original data point."""
        return self.live_y - self.obj_y

    @property
    def editable(self):
        return QGraphicsItem.GraphicsItemFlag.ItemIsSelectable in self.flags()

    @editable.setter
    def editable(self, value: bool):
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, value)

    @property
    def movable(self):
        return QGraphicsItem.GraphicsItemFlag.ItemIsMovable in self.flags()

    @movable.setter
    def movable(self, value: bool):
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, value)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # This is called WHENEVER the item is moved (dragging or setPos)
            # 'value' is the new QPointF the item is moving to.
            if self.scene() is not None:
                value = self.scene().snap_position(self, value)
            self.update()

        return super().itemChange(change, value)

    @property
    def is_selected(self) -> bool:
        return self.isSelected()

    def boundingRect(self) -> QtCore.QRectF:
        return self.obj_rect.adjusted(-SELECTION_MARGIN, -SELECTION_MARGIN, SELECTION_MARGIN, SELECTION_MARGIN)

    @property
    def obj_rect(self):
        return QtCore.QRectF(0, 0, self.obj_w, self.obj_h)

    def object_shape(self) -> QtGui.QPainterPath:
        """:return: the shape of the object itself, without what reaches over its edge (for `shape()`: where it is hit)"""
        path = QtGui.QPainterPath()
        path.addRect(self.obj_rect)
        return path

    def paint(self, painter, option, widget=None):
        """
        Painting is mostly handled by the specific widget types (e.g., button, bar).
        The base class implements common behavior such as selection highlighting.

        :param painter: QPainter object used for drawing the widget.
        :param option: QStyleOptionGraphicsItem containing style options for the widget (e.g., state, level of detail).
        :param widget: Optional QWidget that is being painted on; can be None if not applicable.
        """
        if self.is_selected:
            # Draw a selection rectangle around the widget when selected
            selection_color = QtGui.QColor(current_colors().accent)
            selection_pen = QtGui.QPen(selection_color, 2, QtCore.Qt.PenStyle.DashLine)
            painter.setPen(selection_pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)

            # CRITICAL: Do NOT use self.boundingRect() here.
            # Use the actual dimensions of the widget.
            # This ensures the drawing is well within the 3px margin.
            widget_rect = self.obj_rect
            painter.drawRect(widget_rect)


class ClickableWidget(EditableWidget):
    """An object that tells when it is pressed (`clicked`, with the id of the object)."""

    clicked = QtCore.pyqtSignal(int)

    def mousePressEvent(self, event):
        self.clicked.emit(self.obj_id)
        super().mousePressEvent(event)
