from typing import List, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QVBoxLayout

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.qt.components import UiComponents


class PartModeBar(QFrame):
    """
    Above the preview in part mode: which part is edited and in which instance, a list to switch to another instance, and a
    button to leave part mode. A shared part says what saving it changes.
    """

    # the index of the instance chosen in the list
    instanceChosen = QtCore.pyqtSignal(int)
    doneClicked = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "notice")
        column = QVBoxLayout(self)
        column.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)
        column.setSpacing(UiDimensions.half)

        row = QHBoxLayout()
        row.setSpacing(UiDimensions.one)
        row.addWidget(UiComponents.create_icon_label("puzzle-edit-outline", size=UiDimensions.two))
        self.title = UiComponents.create_label("", word_wrap=True)
        self.title.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.title, 1)
        self.instances = QComboBox()
        self.instances.setToolTip("The instance of the part that is shown and edited: every other instance follows it")
        self.instances.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.instances.setMinimumContentsLength(32)
        self.instances.currentIndexChanged.connect(self.instanceChosen)
        row.addWidget(self.instances)
        self.done = UiComponents.create_button(
            title="Done",
            icon="check",
            tooltip="Leave part mode. The changes of the part stay in the draft until you save",
            on_click=self.doneClicked.emit,
        )
        row.addWidget(self.done)
        column.addLayout(row)

        self.hint = UiComponents.create_label("", role="hint", word_wrap=True)
        column.addWidget(self.hint)
        self.hide()

    def show_part(self, part: str, instances: List[str], current: Optional[int], hint: Optional[str]):
        """
        :param part: the path of the part
        :param instances: the descriptions of its instances in the draft (see `PlateSession.describe_instance`)
        :param current: the index of the instance that is edited, None if it has no objects anymore
        :param hint: e.g. what saving a shared part changes
        """
        where = "" if current is None else f", instance at {instances[current]}"
        self.title.setText(f"Editing part {part}{where}".replace("/", "/​"))
        self.instances.blockSignals(True)
        self.instances.clear()
        self.instances.addItems(instances)
        if current is not None:
            self.instances.setCurrentIndex(current)
        self.instances.blockSignals(False)
        self.instances.setVisible(len(instances) > 1)
        self.hint.setText(hint or "")
        self.hint.setVisible(bool(hint))
        self.show()
