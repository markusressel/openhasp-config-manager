from typing import Dict

from PyQt6.QtWidgets import QGraphicsObject


class EditableWidget(QGraphicsObject):

    @property
    def obj_data(self):
        return self._object_data

    @property
    def obj_id(self):
        return self.obj_data.get("id", 0)

    @property
    def obj_x(self) -> int:
        return self.obj_data.get("x", 0)

    @property
    def obj_y(self) -> int:
        return self.obj_data.get("y", 0)

    @property
    def obj_w(self) -> int:
        return self.obj_data.get("w", 80)

    @property
    def obj_h(self) -> int:
        return self.obj_data.get("h", 40)

    def __init__(self, object_data: Dict, *args, **kwargs):
        self._object_data = object_data
        super().__init__(*args, **kwargs)

        self._editable = True

    @property
    def editable(self):
        return self._editable

    @editable.setter
    def editable(self, value: bool):
        self._editable = value
