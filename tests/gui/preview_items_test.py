"""Every object type of the preview draws something: one test per type, in the order they were added."""

import pytest
from PyQt6 import QtGui

from tests import TestBase


def render(obj: dict) -> "QtGui.QImage":
    """Draw the object the way the preview does, on a transparent image."""
    from PyQt6 import QtCore
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

    view = PagePreviewWidget()
    view.set_objects([obj])
    image = QtGui.QImage(480, 320, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("black"))
    painter = QtGui.QPainter(image)
    view.scene().render(painter, QtCore.QRectF(0, 0, 480, 320), QtCore.QRectF(0, 0, 480, 320))
    painter.end()
    return image


def painted(image) -> int:
    """:return: the number of pixels that are not black"""
    black = 0xFF000000
    return sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixel(x, y) != black)


@pytest.mark.usefixtures("qapp")
class TestPreviewItems(TestBase):
    def test_known_types_are_drawn(self):
        image = render({"page": 1, "id": 1, "obj": "bar", "x": 10, "y": 10, "w": 100, "h": 20, "val": 50})
        assert painted(image) > 0

    def test_checkbox_ignores_w_and_h_and_shows_the_check_mark_when_checked(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.checkbox import HaspCheckboxItem

        box = {"page": 1, "id": 1, "obj": "checkbox", "x": 10, "y": 10, "w": 5, "h": 5, "text": "Dark mode"}
        item = HaspCheckboxItem(box)
        assert item.obj_h > 5 and item.obj_w > item.obj_h
        unchecked = painted(render(box))
        assert unchecked > 0
        assert render({**box, "val": 1}) != render(box)

    def test_arc_indicator_follows_its_value(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.arc import HaspArcItem

        arc = {"page": 1, "id": 1, "obj": "arc", "x": 10, "y": 10, "w": 150, "h": 150}
        empty, full = painted(render({**arc, "val": 0})), painted(render({**arc, "val": 100}))
        assert 0 < empty < full

        item = HaspArcItem({**arc, "val": 50, "start_angle": 0, "end_angle": 180})
        assert item.angles() == ((0, 180), (0, 90))
        item.obj_data["type"] = 2
        assert item.angles()[1] == (90, 90)
        item.obj_data["type"] = 1
        item.obj_data["val"] = 25
        assert item.angles()[1] == (45, 45)

    def test_dropdown_shows_the_selected_option(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.dropdown import HaspDropdownItem

        dropdown = {
            "page": 1,
            "id": 1,
            "obj": "dropdown",
            "x": 10,
            "y": 10,
            "w": 150,
            "h": 30,
            "options": "Apple\nBanana",
            "val": 1,
        }
        assert HaspDropdownItem(dropdown).selected_text == "Banana"
        assert HaspDropdownItem({**dropdown, "val": 7}).selected_text == ""
        assert render({**dropdown, "val": 0}) != render(dropdown)

    def test_roller_shows_rows_around_the_selected_option(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.roller import HaspRollerItem

        roller = HaspRollerItem({"obj": "roller", "w": 100, "h": 1, "options": "a\nb\nc\nd", "val": 0})
        assert roller.visible_entries() == [None, "a", "b"]
        roller.obj_data["mode"] = 1
        assert roller.visible_entries() == ["d", "a", "b"]
        roller.obj_data["rows"] = 5
        assert roller.visible_entries() == ["c", "d", "a", "b", "c"]
        assert roller.obj_h == 5 * roller.row_height
        assert (
            painted(render({"page": 1, "id": 1, "obj": "roller", "x": 5, "y": 5, "w": 100, "options": "a\nb", "val": 1})) > 0
        )
