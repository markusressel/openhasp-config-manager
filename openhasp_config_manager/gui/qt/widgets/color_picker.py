import math
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.colors import Argb, parse_color

_WHEEL_SIZE = 190
_RING_WIDTH = 16
_HANDLE_RADIUS = 6


class ColorWheel(QWidget):
    """A ring for the hue and, inside of it, a square for the saturation and the value of the color."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_WHEEL_SIZE, _WHEEL_SIZE)
        # 0..359, 0..1, 0..1
        self.hue = 0
        self.saturation = 0.0
        self.value = 1.0
        # what a drag started on: the ring or the square
        self._dragging: Optional[str] = None

    def set_hsv(self, hue: int, saturation: float, value: float):
        # the hue of a gray is undefined: keep the one that was set
        if saturation > 0 and value > 0:
            self.hue = hue % 360
        self.saturation = saturation
        self.value = value
        self.update()

    def color(self) -> QColor:
        return QColor.fromHsvF(self.hue / 360, self.saturation, self.value)

    # --- geometry ---

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _outer_radius(self) -> float:
        return min(self.width(), self.height()) / 2 - 1

    def _square(self) -> QRectF:
        """The square inside of the ring."""
        half = (self._outer_radius() - _RING_WIDTH - 3) / math.sqrt(2)
        center = self._center()
        return QRectF(center.x() - half, center.y() - half, 2 * half, 2 * half)

    # --- painting ---

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self._center()
        outer = self._outer_radius()

        gradient = QConicalGradient(center, 0)
        for step in range(0, 361, 30):
            gradient.setColorAt(step / 360, QColor.fromHsv(min(step, 359) % 360, 255, 255))
        ring = QPainterPath()
        ring.addEllipse(center, outer, outer)
        ring.addEllipse(center, outer - _RING_WIDTH, outer - _RING_WIDTH)
        painter.fillPath(ring, QBrush(gradient))

        square = self._square()
        horizontal = QLinearGradient(square.topLeft(), square.topRight())
        horizontal.setColorAt(0, QColor("white"))
        horizontal.setColorAt(1, QColor.fromHsv(self.hue, 255, 255))
        painter.fillRect(square, horizontal)
        vertical = QLinearGradient(square.topLeft(), square.bottomLeft())
        vertical.setColorAt(0, QColor(0, 0, 0, 0))
        vertical.setColorAt(1, QColor("black"))
        painter.fillRect(square, vertical)

        angle = math.radians(self.hue)
        middle = outer - _RING_WIDTH / 2
        self._handle(painter, QPointF(center.x() + middle * math.cos(angle), center.y() - middle * math.sin(angle)))
        self._handle(
            painter,
            QPointF(square.left() + self.saturation * square.width(), square.top() + (1 - self.value) * square.height()),
        )

    @staticmethod
    def _handle(painter: QPainter, position: QPointF):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("black"), 3))
        painter.drawEllipse(position, _HANDLE_RADIUS, _HANDLE_RADIUS)
        painter.setPen(QPen(QColor("white"), 1.5))
        painter.drawEllipse(position, _HANDLE_RADIUS, _HANDLE_RADIUS)

    # --- mouse ---

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position()
        distance = math.hypot(position.x() - self._center().x(), position.y() - self._center().y())
        if distance >= self._outer_radius() - _RING_WIDTH - 3 and distance <= self._outer_radius() + 2:
            self._dragging = "ring"
        elif self._square().adjusted(-3, -3, 3, 3).contains(position):
            self._dragging = "square"
        else:
            return
        self._drag_to(position)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging is not None:
            self._drag_to(event.position())

    def mouseReleaseEvent(self, _event):
        self._dragging = None

    def _drag_to(self, position: QPointF):
        if self._dragging == "ring":
            center = self._center()
            self.hue = int(round(math.degrees(math.atan2(center.y() - position.y(), position.x() - center.x())))) % 360
        else:
            square = self._square()
            self.saturation = min(max((position.x() - square.left()) / square.width(), 0.0), 1.0)
            self.value = 1.0 - min(max((position.y() - square.top()) / square.height(), 0.0), 1.0)
        self.update()
        self.changed.emit()


class _Swatch(QFrame):
    """A color on a checkerboard, so that a color with an alpha can be told from an opaque one."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(UiDimensions.three)
        self._color = QColor("black")

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        size = 6
        for x in range(0, self.width(), size):
            for y in range(0, self.height(), size):
                painter.fillRect(x, y, size, size, QColor("#cccccc") if (x // size + y // size) % 2 else QColor("#ffffff"))
        painter.fillRect(self.rect(), self._color)
        painter.setPen(QColor(128, 128, 128))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


class ColorPicker(QFrame):
    """
    A floating color picker for a color of a file: a hue ring with a saturation/value square, the channels (A, R, G, B) and the
    text. It is a child of the editor (a window would be placed by the window manager), and closes with Escape or a click outside.
    """

    # the color changed, as it is written in the file
    colorChanged = pyqtSignal(object)
    closed = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setProperty("role", "floating")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # the color as it was written: its case and whether it has an alpha are kept
        self._argb = Argb(0, 0, 0)
        self._original = QColor("black")
        self._updating = False

        column = QVBoxLayout(self)
        column.setContentsMargins(UiDimensions.one, UiDimensions.one, UiDimensions.one, UiDimensions.one)
        column.setSpacing(UiDimensions.half)

        self._wheel = ColorWheel()
        self._wheel.changed.connect(self._on_wheel_changed)
        column.addWidget(self._wheel, alignment=Qt.AlignmentFlag.AlignHCenter)

        swatches = QGridLayout()
        swatches.setHorizontalSpacing(0)
        self._old_swatch = _Swatch()
        self._new_swatch = _Swatch()
        self._old_swatch.setToolTip("The color from before")
        self._new_swatch.setToolTip("The new color")
        swatches.addWidget(self._old_swatch, 0, 0)
        swatches.addWidget(self._new_swatch, 0, 1)
        column.addLayout(swatches)

        grid = QGridLayout()
        grid.setHorizontalSpacing(UiDimensions.half)
        self._channels = {}
        for index, (name, tooltip) in enumerate(
            (
                ("A", "Alpha. A color with an alpha is written as #AARRGGBB, openHASP itself uses #RRGGBB."),
                ("R", "Red"),
                ("G", "Green"),
                ("B", "Blue"),
            )
        ):
            label = QLabel(name)
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            spin.setToolTip(tooltip)
            spin.valueChanged.connect(self._on_channel_changed)
            grid.addWidget(label, 0, index)
            grid.addWidget(spin, 1, index)
            self._channels[name] = spin
        column.addLayout(grid)

        self._text = QLineEdit()
        self._text.setToolTip("#RGB, #RRGGBB or #AARRGGBB")
        self._text.editingFinished.connect(self._on_text_edited)
        self._text.textEdited.connect(self._on_text_typed)
        column.addWidget(self._text)
        self.setFixedWidth(_WHEEL_SIZE + 2 * UiDimensions.one + 4)
        self.hide()

    @property
    def argb(self) -> Argb:
        return self._argb

    def open(self, argb: Argb):
        """Show the picker for a color; `colorChanged` follows every change from now on."""
        self._argb = argb
        self._original = QColor(argb.red, argb.green, argb.blue, argb.alpha)
        self._old_swatch.set_color(self._original)
        self._update_all(from_wheel=False)
        self.adjustSize()
        self.show()
        self.raise_()
        self.setFocus()
        QApplication.instance().installEventFilter(self)

    def close_picker(self):
        QApplication.instance().removeEventFilter(self)
        if self.isVisible():
            self.hide()
            self.closed.emit()

    # --- the color ---

    def set_color(self, red: int, green: int, blue: int, alpha: int):
        self._set(Argb(red, green, blue, alpha, self._argb.upper, self._argb.has_alpha))

    def _set(self, argb: Argb, from_wheel: bool = False, keep_text: bool = False):
        changed = argb != self._argb
        self._argb = argb
        self._update_all(from_wheel, keep_text)
        if changed:
            self.colorChanged.emit(argb)

    def _update_all(self, from_wheel: bool, keep_text: bool = False):
        self._updating = True
        try:
            argb = self._argb
            for name, value in zip("ARGB", (argb.alpha, argb.red, argb.green, argb.blue)):
                self._channels[name].setValue(value)
            color = QColor(argb.red, argb.green, argb.blue, argb.alpha)
            if not from_wheel:
                hue, saturation, value, _ = color.getHsvF()
                self._wheel.set_hsv(max(int(round(hue * 360)), 0) if hue >= 0 else self._wheel.hue, saturation, value)
            self._new_swatch.set_color(color)
            if not keep_text:
                self._text.setText(argb.hex())
        finally:
            self._updating = False

    # --- input ---

    def _on_wheel_changed(self):
        color = self._wheel.color()
        argb = self._argb
        self._set(Argb(color.red(), color.green(), color.blue(), argb.alpha, argb.upper, argb.has_alpha), from_wheel=True)

    def _on_channel_changed(self):
        if self._updating:
            return
        values = {name: spin.value() for name, spin in self._channels.items()}
        argb = self._argb
        self._set(Argb(values["R"], values["G"], values["B"], values["A"], argb.upper, argb.has_alpha))

    def _on_text_typed(self, text: str):
        """Follow the text while it is a color."""
        parsed = parse_color(text.strip())
        if parsed is not None:
            has_alpha = parsed.has_alpha or self._argb.has_alpha
            self._set(Argb(parsed.red, parsed.green, parsed.blue, parsed.alpha, parsed.upper, has_alpha), keep_text=True)

    def _on_text_edited(self):
        # the text is written the way the color is now (and if it is no color, that is the one from before)
        self._updating = True
        try:
            self._text.setText(self._argb.hex())
        finally:
            self._updating = False

    # --- closing ---

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.close_picker()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget):
            if watched is not self and not self.isAncestorOf(watched):
                self.close_picker()
        return False
