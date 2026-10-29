import re
from typing import List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QSizePolicy

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.components import UiComponents

# the folders of the paths in the description of an instance (see `PlateSession.describe_instance`)
_FOLDERS = re.compile(r"[^\s>(]*/")


class _ElidedLabel(QLabel):
    """A label of one line that cuts its text with "…" when it gets narrower than it."""

    def __init__(self):
        super().__init__()
        self._text = ""
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(UiDimensions.four)

    def set_text(self, text: str):
        self._text = text
        self._elide()
        self.updateGeometry()

    @property
    def full_text(self) -> str:
        return self._text

    def sizeHint(self) -> QtCore.QSize:
        hint = super().sizeHint()
        return QtCore.QSize(self.fontMetrics().horizontalAdvance(self._text) + 2, hint.height())

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self.minimumWidth(), super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self._text, QtCore.Qt.TextElideMode.ElideRight, self.width()))


def short_instance(description: str) -> str:
    """:return: the description of an instance without the folders of its files, e.g. "page.jsonl:4 (id=20)\""""
    return _FOLDERS.sub("", description)


class PartModeBar(QFrame):
    """
    One line above the preview of a part tab: the part (its path in the tooltip), a list to switch to another instance, "Show
    the page" (the page around the instance, dimmed) and "Done" (closes the tab). What else is worth knowing (a shared part,
    which devices saving it changes, a part on its own) is in the tooltip of an info icon.
    """

    # the index of the instance chosen in the list
    instanceChosen = QtCore.pyqtSignal(int)
    showPageToggled = QtCore.pyqtSignal(bool)
    doneClicked = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "notice")
        row = QHBoxLayout(self)
        row.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)
        row.setSpacing(UiDimensions.one)
        row.addWidget(UiComponents.create_icon_label("puzzle-edit-outline", size=UiDimensions.two))
        self.title = _ElidedLabel()
        row.addWidget(self.title)
        self.instances = QComboBox()
        self.instances.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.instances.setMinimumContentsLength(10)
        self.instances.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.instances.setMaximumWidth(UiDimensions.one * 40)
        self.instances.currentIndexChanged.connect(self._on_instance_chosen)
        row.addWidget(self.instances, 1)
        # keeps the buttons on the right while the list is hidden
        self._spacer = QLabel()
        self._spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self._spacer, 1)
        self.info = UiComponents.create_icon_label("information-outline", size=UiDimensions.two)
        row.addWidget(self.info)
        self.show_page = UiComponents.create_button(
            title="Show the page",
            icon="eye-outline",
            tooltip="Show the page around the instance, dimmed. Off: only the objects of the instance, zoomed to fit them",
            on_click=lambda: self.showPageToggled.emit(self.show_page.isChecked()),
        )
        self.show_page.setCheckable(True)
        row.addWidget(self.show_page)
        self.done = UiComponents.create_button(title="Done", icon="check", on_click=self.doneClicked.emit)
        row.addWidget(self.done)
        # the buttons with their titles, and how wide they are with them (see `_fit_buttons`)
        self._titles = [(button, button.text(), button.sizeHint().width()) for button in [self.show_page, self.done]]
        self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_buttons()

    def _fit_buttons(self):
        """The bar stays one line: in a narrow window the buttons show only their icons (their tooltips say what they do)."""
        row = self.layout()
        margins = row.contentsMargins()
        others = [
            row.itemAt(index).widget()
            for index in range(row.count())
            if row.itemAt(index).widget() not in (self.show_page, self.done, self._spacer)
        ]
        shown = [widget for widget in others if not widget.isHidden()]
        needed = (
            margins.left()
            + margins.right()
            + row.spacing() * (len(shown) + 1)
            + sum(widget.minimumSizeHint().width() for widget in shown if widget is not self.title)
            + self.title.sizeHint().width()
            + sum(width for _button, _title, width in self._titles)
        )
        compact = self.width() < needed
        for button, title, _width in self._titles:
            button.setText("" if compact else title)

    def show_part(self, part: str, instances: List[str], current: Optional[int], hint: Optional[str], alone: bool = False):
        """
        :param part: the path of the part
        :param instances: the descriptions of its instances in the draft (see `PlateSession.describe_instance`)
        :param current: the index of the instance that is edited, None if it has no objects anymore
        :param hint: e.g. what saving a shared part changes
        :param alone: the part is shown on its own, not on the pages of the device
        """
        self.title.set_text(part.rsplit("/", 1)[-1])
        where = "on its own" if alone else ("" if current is None else f"instance at {instances[current]}")
        self.title.setToolTip(f"Editing the part {part}" + (f", {where}" if where else ""))
        self.done.setToolTip(
            "Close the tab of the part. Asks to save the part first if it has changes"
            if alone
            else "Close the tab of the part. The changes of the part stay in the draft until you save"
        )
        self.instances.blockSignals(True)
        self.instances.clear()
        for index, description in enumerate(instances):
            self.instances.addItem(short_instance(description))
            self.instances.setItemData(index, description, QtCore.Qt.ItemDataRole.ToolTipRole)
        if current is not None:
            self.instances.setCurrentIndex(current)
        self.instances.blockSignals(False)
        # the list opens as wide as its descriptions, also while the box is narrow
        self.instances.view().setMinimumWidth(self.instances.view().sizeHintForColumn(0) + UiDimensions.two)
        self._update_instances_tooltip()
        self.instances.setVisible(len(instances) > 1)
        self._spacer.setVisible(len(instances) <= 1)
        self.info.setToolTip(hint or "")
        self.info.setVisible(bool(hint))
        self.show()
        self._fit_buttons()

    def set_show_page(self, show: bool):
        self.show_page.setChecked(show)

    def _on_instance_chosen(self, index: int):
        self._update_instances_tooltip()
        self.instanceChosen.emit(index)

    def _update_instances_tooltip(self):
        description = self.instances.itemData(self.instances.currentIndex(), QtCore.Qt.ItemDataRole.ToolTipRole)
        self.instances.setToolTip(
            "The instance of the part that is shown and edited: every other instance follows it"
            + (f"\n{description}" if description else "")
        )
