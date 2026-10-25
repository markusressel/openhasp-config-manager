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

    def test_led_is_brighter_with_a_higher_value(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.led import HaspLedItem

        led = {"page": 1, "id": 1, "obj": "led", "x": 10, "y": 10, "w": 30, "h": 30, "bg_color": "#ff0000"}
        assert HaspLedItem({**led, "val": 255}).brightness == 1
        assert HaspLedItem({**led, "val": "{{ x }}"}).brightness == 0
        assert painted(render({**led, "val": 0})) > 0
        assert render({**led, "val": 255}) != render({**led, "val": 0})

    def test_spinner_draws_a_ring_and_a_segment(self):
        spinner = {"page": 1, "id": 1, "obj": "spinner", "x": 10, "y": 10, "w": 60, "h": 60, "line_width": 6}
        ring_only = painted(render({**spinner, "angle": 0, "line_color10": "#000000"}))
        assert ring_only > 0
        assert render({**spinner, "angle": 120, "line_color10": "#00ff00"}) != render({**spinner, "angle": 0})

    def test_linemeter_activates_lines_up_to_its_value(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.linemeter import HaspLineMeterItem

        meter = {"page": 1, "id": 1, "obj": "linemeter", "x": 10, "y": 10, "w": 150, "h": 150, "line_count": 20}
        assert HaspLineMeterItem({**meter, "val": 50}).active_lines() == 10
        assert HaspLineMeterItem({**meter, "val": 500}).active_lines() == 20
        assert painted(render(meter)) > 0
        assert render({**meter, "val": 50}) != render({**meter, "val": 50, "type": 1})

    def test_gauge_labels_and_needle(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.gauge import HaspGaugeItem

        gauge = {"page": 1, "id": 1, "obj": "gauge", "x": 10, "y": 10, "w": 200, "h": 200, "min": 0, "max": 1000}
        assert HaspGaugeItem(gauge).labels() == ["0", "200", "400", "600", "800", "1000"]
        assert HaspGaugeItem({**gauge, "format": 2, "label_count": 3}).labels() == ["0", "5", "10"]
        assert painted(render(gauge)) > 0
        assert render({**gauge, "val": 900}) != render({**gauge, "val": 100})

    def test_line_is_as_large_as_its_points_and_ignores_broken_ones(self):
        from openhasp_config_manager.gui.domain.line_points import parse_points
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.line import HaspLineItem

        line = {"page": 1, "id": 1, "obj": "line", "x": 10, "y": 10, "points": [[10, 25], [100, 25], [100, 0]]}
        item = HaspLineItem(line)
        assert (item.obj_w, item.obj_h) == (100, 25)
        assert HaspLineItem({**line, "auto_size": False, "w": 7, "h": 8}).obj_w == 7
        assert parse_points("[[1, 2], [3, 4]]") == [(1, 2), (3, 4)]
        assert parse_points("{{ points }}") == [] and parse_points([[1], "x", [1, "2"]]) == []
        assert painted(render(line)) > 0
        assert render({**line, "y_invert": True}) != render(line)

    def test_qrcode_is_a_square_and_follows_its_text(self):
        from openhasp_config_manager.gui.domain.qr_placeholder import MODULES, placeholder_modules
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.qrcode import HaspQrCodeItem

        code = {
            "page": 1,
            "id": 1,
            "obj": "qrcode",
            "x": 10,
            "y": 10,
            "size": 100,
            "w": 3,
            "h": 4,
            "text": "https://openhasp.com",
        }
        item = HaspQrCodeItem(code)
        assert (item.obj_w, item.obj_h) == (100, 100)
        assert placeholder_modules("a") == placeholder_modules("a") != placeholder_modules("b")
        assert len(placeholder_modules("a")) == MODULES
        # the finder square in the top left corner
        assert all(placeholder_modules("a")[0][:7]) and not placeholder_modules("a")[1][1]
        assert render({**code, "text": "other"}) != render(code)

    def test_base_object_is_a_rounded_rectangle(self):
        box = {"page": 1, "id": 1, "obj": "obj", "x": 10, "y": 10, "w": 100, "h": 50, "border_width": 0}
        assert painted(render(box)) >= 100 * 50 - 100
        assert painted(render({**box, "radius": 25})) < painted(render(box))
