from typing import Optional

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QComboBox, QProgressBar, QSizePolicy, QToolButton, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.live_screen import DEFAULT_INTERVAL, INTERVALS
from openhasp_config_manager.gui.qt.components import ThemedIcons, UiComponents


def interval_label(seconds: int) -> str:
    if seconds == 0:
        return "Only after changes"
    if seconds < 60:
        return f"Every {seconds} s"
    return f"Every {seconds // 60} min"


class _ScreenImage(QWidget):
    """The screenshot, scaled to fit and keeping its aspect ratio, or a text without one."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.image: Optional[QImage] = None
        self.placeholder = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(UiDimensions.five * 4, UiDimensions.five * 3)

    def paintEvent(self, _event):
        painter = QPainter(self)
        if self.image is None or self.image.isNull():
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.placeholder)
            return
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QtCore.QRect(QtCore.QPoint(0, 0), size)
        target.moveCenter(self.rect().center())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self.image)


class LiveScreenView(QWidget):
    """
    The *Live device* dock: the controls of the plate of the active tab (`set_controls`), the last screenshot of it, when it
    was taken, a busy indicator while one is taken, a Refresh button and how often to take one. `LiveScreens` decides when.
    """

    refreshRequested = QtCore.pyqtSignal()
    # the interval chosen (seconds, 0: only after changes)
    intervalChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = UiComponents.create_column(parent=self, margin_start=4, margin_end=4, margin_top=4, margin_bottom=4)
        self._layout = layout

        bar = UiComponents.create_row()
        self.refresh_button = QToolButton()
        ThemedIcons.apply(self.refresh_button, "refresh")
        self.refresh_button.setAutoRaise(True)
        self.refresh_button.setToolTip("Take a screenshot of the plate now")
        self.refresh_button.clicked.connect(lambda _checked=False: self.refreshRequested.emit())
        bar.addWidget(self.refresh_button)

        self.interval_combo = QComboBox()
        for seconds in INTERVALS:
            self.interval_combo.addItem(interval_label(seconds), seconds)
        self.interval_combo.setToolTip(
            "How often to take a screenshot of the plate. A screenshot keeps the plate busy for a moment; one is also taken "
            "shortly after a deploy, Restore plate, Live preview or a page change."
        )
        self.interval_combo.activated.connect(lambda index: self.intervalChanged.emit(self.interval_combo.itemData(index)))
        bar.addWidget(self.interval_combo)

        self.busy_indicator = QProgressBar()
        self.busy_indicator.setRange(0, 0)
        self.busy_indicator.setTextVisible(False)
        self.busy_indicator.setFixedSize(UiDimensions.five * 2, UiDimensions.two)
        self.busy_indicator.setToolTip("Taking a screenshot of the plate…")
        # keeps its room, so the status doesn't move
        policy = self.busy_indicator.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.busy_indicator.setSizePolicy(policy)
        self.busy_indicator.hide()
        bar.addWidget(self.busy_indicator)

        bar.addStretch(1)
        layout.addLayout(bar)

        # on a line of its own: an error can be long
        self.status_label = UiComponents.create_label("", role="hint", word_wrap=True)
        layout.addWidget(self.status_label)

        self.image = _ScreenImage()
        layout.addWidget(self.image, 1)
        self.set_interval(DEFAULT_INTERVAL)
        self.set_device(None)

    def set_controls(self, controls: QWidget):
        """The controls of the plate, above the screenshot."""
        self._layout.insertWidget(0, controls)

    def set_device(self, name: Optional[str]):
        """:param name: the device whose plate is shown, None without a tab"""
        self.refresh_button.setEnabled(name is not None)
        self.image.placeholder = "Open a device to see its plate." if name is None else "No screenshot of the plate yet."
        if name is None:
            self.set_image(None)
            self.set_status("", error=False)
            self.set_busy(False)

    def set_interval(self, seconds: int):
        self.interval_combo.setCurrentIndex(max(0, self.interval_combo.findData(seconds)))

    def set_image(self, image: Optional[QImage]):
        self.image.image = image
        self.image.update()

    def set_status(self, text: str, error: bool):
        self.status_label.setText(text)
        self.status_label.setToolTip(text)
        role = "error" if error else "hint"
        if self.status_label.property("role") != role:
            self.status_label.setProperty("role", role)
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def set_busy(self, busy: bool):
        self.busy_indicator.setVisible(busy)
