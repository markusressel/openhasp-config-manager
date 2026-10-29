"""Every object type of the preview draws something: one test per type, in the order they were added."""

import pytest

from tests import TestBase


def render(obj: dict, *others: dict):
    """Draw the objects (of one page) the way the preview does, on a black image."""
    from PyQt6 import QtCore, QtGui
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

    view = PagePreviewWidget()
    view.set_objects([obj, *others])
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

    def test_a_bar_draws_the_track_and_an_indicator_with_its_own_color_inside_of_it(self):
        # GIVEN: a track of 100 x 30, its indicator (part 1) at half, and 6 pixels of padding
        image = render(
            {
                "page": 1,
                "id": 1,
                "obj": "bar",
                "x": 10,
                "y": 10,
                "w": 100,
                "h": 30,
                "val": 50,
                "bg_color": "#202020",
                "bg_color10": "#00ff00",
                "bg_grad_dir": 0,
                "bg_grad_dir10": 0,
                "border_width": 0,
                "border_width10": 0,
                "radius": 0,
                "radius10": 0,
                "pad_left": 6,
                "pad_right": 6,
                "pad_top": 6,
                "pad_bottom": 6,
            }
        )

        # THEN: the track has the color of the object, the indicator its own, starting at the padding and half as wide as the rest
        assert image.pixelColor(12, 25).name() == "#202020"
        assert image.pixelColor(20, 25).name() == "#00ff00"
        assert image.pixelColor(20, 14).name() == "#202020"
        assert image.pixelColor(10 + 6 + 40, 25).name() == "#00ff00"
        assert image.pixelColor(10 + 6 + 44, 25).name() == "#202020"

    def test_the_radius_of_a_bar_is_at_most_half_of_its_height(self):
        # GIVEN: an indicator of 10 x 20 with a radius of 15, which has to be a half circle (radius 5 on the short side)
        image = render(
            {
                "page": 1,
                "id": 1,
                "obj": "bar",
                "x": 0,
                "y": 0,
                "w": 100,
                "h": 20,
                "val": 10,
                "bg_color": "#202020",
                "bg_color10": "#00ff00",
                "bg_grad_dir": 0,
                "bg_grad_dir10": 0,
                "border_width": 0,
                "border_width10": 0,
                "radius": 0,
                "radius10": 15,
                "pad_left": 0,
                "pad_right": 0,
                "pad_top": 0,
                "pad_bottom": 0,
            }
        )

        # THEN: the corner of the indicator is cut away, the middle of its end is not
        assert image.pixelColor(0, 0).name() == "#202020"
        assert image.pixelColor(1, 10).name() == "#00ff00"
        assert image.pixelColor(9, 10).name() == "#00ff00"

    def test_every_type_gets_its_item(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.registry import ITEM_CLASSES
        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

        view = PagePreviewWidget()
        types = ["btn", *ITEM_CLASSES]
        view.set_objects([{"page": 1, "id": index, "obj": kind} for index, kind in enumerate(types, start=1)])
        items = {item.obj_data["obj"]: item for item in view.editable_items()}
        assert isinstance(items["btn"], HaspButtonItem)
        assert all(type(items[kind]) is ITEM_CLASSES[kind] for kind in ITEM_CLASSES)
        assert all(item.parent_widget is view for item in items.values())

    def test_checkbox_ignores_w_and_h_and_shows_the_check_mark_when_checked(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.checkbox import HaspCheckboxItem

        box = {"page": 1, "id": 1, "obj": "checkbox", "x": 10, "y": 10, "w": 5, "h": 5, "text": "Dark mode"}
        item = HaspCheckboxItem(box)
        assert item.obj_h > 5 and item.obj_w > item.obj_h
        unchecked = painted(render(box))
        assert unchecked > 0
        assert render({**box, "val": 1}) != render(box)

    def test_arc_indicator_follows_its_value(self):
        arc = {"page": 1, "id": 1, "obj": "arc", "x": 10, "y": 10, "w": 150, "h": 150}
        empty, full = painted(render({**arc, "val": 0})), painted(render({**arc, "val": 100}))
        assert 0 < empty < full

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

        def entries(item):
            return [entry for _, entry, _ in item.entry_rows()]

        roller = HaspRollerItem({"obj": "roller", "w": 100, "h": 1, "rows": 3, "options": "a\nb\nc\nd", "val": 0})
        assert entries(roller) == [None, "a", "b"]
        assert [selected for _, _, selected in roller.entry_rows()] == [False, True, False]
        roller.obj_data["mode"] = 1
        assert entries(roller) == ["d", "a", "b"]
        roller.obj_data["rows"] = 5
        assert entries(roller) == ["c", "d", "a", "b", "c"]
        assert roller.obj_h == round(5 * roller.row_height)
        # without rows the height is the one of the object
        del roller.obj_data["rows"]
        roller.obj_data["h"] = 90
        assert roller.obj_h == 90
        assert (
            painted(render({"page": 1, "id": 1, "obj": "roller", "x": 5, "y": 5, "w": 100, "options": "a\nb", "val": 1})) > 0
        )

    def test_led_is_brighter_with_a_higher_value(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.led import HaspLedItem

        led = {"page": 1, "id": 1, "obj": "led", "x": 10, "y": 10, "w": 30, "h": 30, "bg_color": "#ff0000"}
        assert HaspLedItem({**led, "val": 255}).brightness == 255
        assert HaspLedItem({**led, "val": 100}).brightness == 100
        # like on the plate an LED without a value is on
        assert HaspLedItem(led).brightness == 255
        assert render({**led, "val": 255}) != render({**led, "val": 0})
        assert render({**led, "val": 200}) != render({**led, "val": 100})

    def test_spinner_draws_a_ring_and_a_segment(self):
        spinner = {"page": 1, "id": 1, "obj": "spinner", "x": 10, "y": 10, "w": 60, "h": 60, "line_width": 6}
        ring_only = painted(render({**spinner, "angle": 0, "line_color10": "#000000"}))
        assert ring_only > 0
        assert render({**spinner, "angle": 120, "line_color10": "#00ff00"}) != render({**spinner, "angle": 0})

    def test_linemeter_activates_lines_up_to_its_value(self):
        meter = {"page": 1, "id": 1, "obj": "linemeter", "x": 10, "y": 10, "w": 150, "h": 150, "line_count": 20}
        assert painted(render(meter)) > 0
        assert render({**meter, "val": 50}) != render({**meter, "val": 50, "type": 1})

    def test_gauge_labels_and_needle(self):
        gauge = {"page": 1, "id": 1, "obj": "gauge", "x": 10, "y": 10, "w": 200, "h": 200, "min": 0, "max": 1000}
        assert painted(render(gauge)) > 0
        assert render({**gauge, "val": 900}) != render({**gauge, "val": 100})

    def test_line_is_as_large_as_its_points_and_ignores_broken_ones(self):
        from openhasp_config_manager.gui.domain.line_points import parse_points
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.line import HaspLineItem

        line = {
            "page": 1,
            "id": 1,
            "obj": "line",
            "x": 10,
            "y": 10,
            "points": [[10, 25], [100, 25], [100, 0]],
            "line_color": "#ffffff",
        }
        item = HaspLineItem(line)
        assert (item.obj_w, item.obj_h) == (100, 25)
        assert HaspLineItem({**line, "auto_size": False, "w": 7, "h": 8}).obj_w == 7
        assert parse_points("[[1, 2], [3, 4]]") == [(1, 2), (3, 4)]
        assert parse_points("{{ points }}") == [] and parse_points([[1], "x", [1, "2"]]) == []
        assert painted(render(line)) > 0
        assert render({**line, "y_invert": True}) != render(line)

    def test_qrcode_is_a_square_and_follows_its_text(self):
        from openhasp_config_manager.gui.domain.qr_code import qr_modules
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
        modules = qr_modules("https://openhasp.com")
        assert len(modules) == len(modules[0]) and all(modules[0][:7])
        assert qr_modules("") == []
        assert painted(render({**code, "text": ""})) > 0
        assert render({**code, "text": "other"}) != render(code)

    def test_base_object_is_a_rounded_rectangle(self):
        box = {"page": 1, "id": 1, "obj": "obj", "x": 10, "y": 10, "w": 100, "h": 50, "border_width": 0}
        assert painted(render(box)) >= 100 * 50 - 100
        assert painted(render({**box, "radius": 25})) < painted(render(box))

    def test_tabview_shows_the_buttons_of_its_tabs(self):
        from openhasp_config_manager.gui.domain.tabs import last_tabview_id, tab_of, tab_texts
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.tabview import HaspTabviewItem

        view = {"page": 1, "id": 2, "obj": "tabview", "x": 0, "y": 0, "w": 300, "h": 200}
        objects = [
            view,
            {"page": 1, "id": 3, "obj": "tab", "parentid": 2, "text": "Lights"},
            {"page": 1, "id": 4, "obj": "tab", "parentid": 9},
        ]
        assert tab_texts(objects, view) == ["Lights"]
        assert last_tabview_id(objects, 1) == 2 and last_tabview_id(objects, 2) is None
        assert tab_of(objects, {"page": 1, "id": 5, "obj": "btn", "parentid": 3}) is objects[1]
        assert tab_of(objects, {"page": 1, "id": 5, "obj": "btn", "parentid": 2}) is None

        item = HaspTabviewItem(view)
        assert item.button_area().height() == 62
        item.obj_data["btn_pos"] = 2
        assert item.button_area().top() == 138
        item.obj_data["btn_pos"] = 0
        assert item.button_area().isEmpty()

        assert painted(render(view)) > 0

    def test_tab_is_not_drawn_itself_but_tabview_draws_its_button(self):
        tabview = {"page": 1, "id": 2, "obj": "tabview", "x": 0, "y": 0, "w": 300, "h": 200}
        tab = {"page": 1, "id": 3, "obj": "tab", "parentid": 2, "text": "Lights"}
        assert painted(render(tab)) == 0
        assert render(tabview, tab) != render(tabview)

    def test_objects_on_a_tab_are_drawn_on_its_page_only_while_it_is_active(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

        # GIVEN: a tabview with its buttons on top (62 high), a button on each of its two tabs, the second reaching out of it
        tabview = {"page": 1, "id": 2, "obj": "tabview", "x": 20, "y": 30, "w": 300, "h": 200, "val": 1}
        tabs = [{"page": 1, "id": 3 + n, "obj": "tab", "parentid": 2} for n in range(2)]
        first = {"page": 1, "id": 5, "obj": "btn", "x": 10, "y": 10, "w": 50, "h": 50, "parentid": 3}
        second = {"page": 1, "id": 6, "obj": "btn", "x": 250, "y": 100, "w": 100, "h": 100, "parentid": 4}

        # WHEN
        view = PagePreviewWidget()
        view.set_objects([tabview, *tabs, first, second])

        # THEN: x/y are relative to the content of the tab, only the active tab is shown
        items = {item.obj_id: item for item in view.editable_items()}
        assert (items[6].scenePos().x(), items[6].scenePos().y()) == (20 + 250, 30 + 62 + 100)
        assert items[6].isVisible() and not items[5].isVisible()
        # the button is cut off at the tabview
        image = render(tabview, *tabs, first, second)
        assert image.pixel(20 + 300 + 5, 30 + 62 + 150) == 0xFF000000
        assert image.pixel(20 + 300 - 5, 30 + 62 + 50) != image.pixel(20 + 300 - 5, 30 + 62 + 150)

    def test_an_object_that_gets_a_tab_as_parent_moves_onto_it(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

        # GIVEN
        tabview = {"page": 1, "id": 2, "obj": "tabview", "x": 20, "y": 30, "w": 300, "h": 200}
        tab = {"page": 1, "id": 3, "obj": "tab", "parentid": 2}
        button = {"page": 1, "id": 5, "obj": "btn", "x": 10, "y": 10, "w": 50, "h": 50}
        view = PagePreviewWidget()
        view.set_objects([tabview, tab, button])
        item = next(item for item in view.editable_items() if item.obj_id == 5)
        assert item.scenePos().x() == 10

        # WHEN
        button["parentid"] = 3
        view.refresh_items()

        # THEN
        assert (item.scenePos().x(), item.scenePos().y()) == (30, 30 + 62 + 10)

        # WHEN it isn't on the tab anymore
        del button["parentid"]
        view.refresh_items()

        # THEN
        assert item.parentItem() is None and item.scenePos().x() == 10

    def test_button_matrix_splits_options_into_rows(self):
        from openhasp_config_manager.gui.domain.button_matrix import MatrixButton, matrix_rows
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.btnmatrix import HaspButtonMatrixItem

        options = ["#FF0000 Red text#", "Cyan", "\n", "One", 5]
        assert matrix_rows(options) == [[MatrixButton("Red text", "#FF0000"), MatrixButton("Cyan")], [MatrixButton("One")]]
        assert matrix_rows('["a", "\\n", "b"]') == [[MatrixButton("a")], [MatrixButton("b")]]
        assert matrix_rows("{{ options }}") == [] and matrix_rows(None) == []

        matrix = {"page": 1, "id": 1, "obj": "btnmatrix", "x": 10, "y": 10, "w": 220, "h": 150, "options": options}
        rects = HaspButtonMatrixItem(matrix).button_rects()
        assert len(rects) == 3
        assert rects[0][0].width() == rects[1][0].width() < rects[2][0].width() == 220 - 2 * 6
        # measured on a plate: `val` doesn't check a button of a matrix
        assert render({**matrix, "toggle": True, "val": 1}) == render(matrix)

    def test_msgbox_has_a_button_for_every_option(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.msgbox import HaspMessageBoxItem

        box = {"page": 1, "id": 1, "obj": "msgbox", "x": 20, "y": 20, "w": 300, "h": 140, "text": "Really?"}
        assert HaspMessageBoxItem(box).buttons() == ["OK"]
        assert HaspMessageBoxItem({**box, "options": ["Yes", "No"]}).buttons() == ["Yes", "No"]
        assert painted(render(box)) > 0
        assert render({**box, "options": ["Yes", "No"]}) != render(box)

    def test_color_picker_gradient_follows_its_mode_and_shows_its_color(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.cpicker import HaspColorPickerItem

        picker = {"page": 1, "id": 1, "obj": "cpicker", "x": 10, "y": 10, "w": 150, "h": 150, "color": "#00ff00"}
        item = HaspColorPickerItem(picker)
        assert item.gradient_stops()[0][1].name() == "#ff0000"
        item.obj_data["mode"] = "saturation"
        assert item.gradient_stops()[0][1].name() == "#ffffff"
        item.obj_data["mode"] = "value"
        assert item.gradient_stops()[0][1].name() == "#000000"
        assert HaspColorPickerItem({"color": "{{ c }}"}).color.name() == "#ff0000"
        assert render({**picker, "color": "#0000ff"}) != render(picker)
        assert painted(render({**picker, "w": 200, "h": 40})) > 0
