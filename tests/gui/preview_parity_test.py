"""The preview draws objects like the plate does: what the default theme of openHASP looks like, and which style property wins."""

import pytest

from tests import TestBase
from tests.gui.preview_items_test import painted, render


def item_of(obj: dict):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem
    from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.registry import ITEM_CLASSES

    obj = {"page": 1, "id": 1, "x": 10, "y": 10, "w": 100, "h": 50, **obj}
    return HaspButtonItem(obj) if obj["obj"] == "btn" else ITEM_CLASSES[obj["obj"]](obj)


@pytest.mark.usefixtures("qapp")
class TestStates(TestBase):
    def test_the_state_of_an_object_follows_its_value_and_enabled(self):
        from openhasp_config_manager.gui.domain.style_parts import State

        assert item_of({"obj": "btn"}).state == State.DEFAULT
        assert item_of({"obj": "btn", "toggle": True, "val": 1}).state == State.TOGGLED
        # a button that doesn't toggle doesn't look toggled
        assert item_of({"obj": "btn", "val": 1}).state == State.DEFAULT
        assert item_of({"obj": "switch", "val": 1, "enabled": False}).state == State.DISABLED_TOGGLED
        assert item_of({"obj": "checkbox", "enabled": "false"}).state == State.DISABLED

    def test_the_properties_of_a_state_fall_back_to_the_less_specific_ones(self):
        from openhasp_config_manager.gui.domain.style_parts import Part, State

        item = item_of({"obj": "btn", "bg_color": "#111111", "bg_color04": "#222222", "bg_color01": "#333333"})

        assert item.style("bg_color", None, Part.MAIN, State.DEFAULT) == "#111111"
        assert item.style("bg_color", None, Part.MAIN, State.DISABLED) == "#222222"
        assert item.style("bg_color", None, Part.MAIN, State.DISABLED_TOGGLED) == "#222222"
        assert item.style("bg_color", None, Part.MAIN, State.TOGGLED) == "#333333"
        assert item.style("bg_color", None, Part.MAIN, State.PRESSED) == "#111111"

    def test_the_default_theme_of_a_state_beats_the_property_of_a_less_specific_state(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.box import box_style
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import BUTTON_DEFAULTS

        # measured on a plate: the `bg_color` of a button doesn't change it while it is toggled, its `bg_color01` does
        toggled = {"obj": "btn", "toggle": True, "val": 1, "bg_color": "#ff0000"}
        assert box_style(item_of(toggled), defaults=BUTTON_DEFAULTS).bg_color.name() == "#ff9962"
        assert box_style(item_of({**toggled, "bg_color01": "#00ff00"}), defaults=BUTTON_DEFAULTS).bg_color.name() == "#00ff00"
        # in the default state the object wins
        assert box_style(item_of({"obj": "btn", "bg_color": "#ff0000"}), defaults=BUTTON_DEFAULTS).bg_color.name() == "#ff0000"


@pytest.mark.usefixtures("qapp")
class TestDefaultLook(TestBase):
    def test_a_button_without_style_is_a_blue_gradient_with_rounded_corners(self):
        image = render({"page": 1, "id": 1, "obj": "btn", "x": 10, "y": 10, "w": 100, "h": 60})

        top, bottom = image.pixelColor(60, 12), image.pixelColor(60, 66)
        assert top.blue() > 200 and top.red() < 120
        assert bottom.green() < top.green()
        assert image.pixelColor(10, 10).name() == "#000000"

    def test_a_toggled_button_is_orange(self):
        toggled = render({"page": 1, "id": 1, "obj": "btn", "x": 0, "y": 0, "w": 100, "h": 60, "toggle": True, "val": 1})
        assert toggled.pixelColor(50, 8).red() > toggled.pixelColor(50, 8).blue()

    def test_a_label_has_no_background_by_default(self):
        label = {"page": 1, "id": 1, "obj": "label", "x": 10, "y": 10, "w": 100, "h": 40, "text": ""}
        assert painted(render(label)) == 0
        assert render({**label, "bg_color": "#ff0000", "bg_opa": 255}).pixelColor(50, 30).name() == "#ff0000"

    def test_an_led_without_a_value_is_on_and_one_with_value_0_is_black(self):
        led = {"page": 1, "id": 1, "obj": "led", "x": 20, "y": 20, "w": 40, "h": 40}
        assert render(led).pixelColor(40, 40).name() == "#00b6ff"
        assert render({**led, "val": 0}).pixelColor(40, 40).name() == "#000000"
        # half the brightness is half of the color
        assert render({**led, "val": 128}).pixelColor(40, 40).blue() == pytest.approx(0xFF * 128 / 255, abs=4)

    def test_an_image_without_a_file_is_a_placeholder(self):
        image = {
            "page": 1,
            "id": 1,
            "obj": "img",
            "x": 10,
            "y": 10,
            "w": 40,
            "h": 40,
            "bg_color": "#ff0000",
            "border_width": 3,
        }
        assert render(image).pixelColor(15, 15).name() == "#ff0000"


@pytest.mark.usefixtures("qapp")
class TestGeometry(TestBase):
    def test_the_knob_of_a_switch_is_a_bit_wider_than_high_and_reaches_over_the_track(self):
        off = item_of({"obj": "switch", "w": 100, "h": 50})
        on = item_of({"obj": "switch", "w": 100, "h": 50, "val": 1})

        inner = off.obj_rect
        assert (off._knob_rect(inner).left(), off._knob_rect(inner).width(), off._knob_rect(inner).height()) == (-1, 53, 52)
        assert on._knob_rect(inner).right() == 102

    def test_the_padding_of_the_track_moves_the_knob_and_the_padding_of_the_knob_makes_it_bigger(self):
        switch = {"obj": "switch", "w": 100, "h": 50}
        padded_track = item_of({**switch, "pad_left": 10, "pad_right": 10})
        padded_knob = item_of({**switch, "pad_left20": 8, "pad_right20": 8, "pad_top20": 8, "pad_bottom20": 8})

        track_inner = padded_track.obj_rect.adjusted(10, 0, -10, 0)
        assert padded_track._knob_rect(track_inner).left() == 10 - 1
        assert padded_knob._knob_rect(padded_knob.obj_rect).width() == 50 + 1 + 16
        assert padded_knob._knob_rect(padded_knob.obj_rect).height() == 50 + 16

    def test_the_knob_of_a_slider_is_centered_on_its_value_between_the_paddings(self):
        slider = {"obj": "slider", "w": 200, "h": 24, "min": 0, "max": 100}

        at_start = item_of({**slider, "val": 0})._knob_rect()
        at_middle = item_of({**slider, "val": 50})._knob_rect()
        at_end = item_of({**slider, "val": 100})._knob_rect()

        # the track is padded by 6, the knob is a square as big as the slider is high, plus 4 on every side
        assert at_start.center().x() == 6 and at_end.center().x() == 194 and at_middle.center().x() == 100
        assert (at_middle.width(), at_middle.height()) == (32, 32)

    def test_a_vertical_bar_fills_from_the_bottom(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.bar import indicator_rect

        bar = item_of({"obj": "bar", "w": 20, "h": 100, "val": 25})

        assert bar.is_vertical
        rect = indicator_rect(bar.inner_rect(), bar.progress, bar.is_vertical)
        assert rect.bottom() == bar.inner_rect().bottom() and rect.height() == pytest.approx(0.25 * bar.inner_rect().height())

    def test_the_text_of_a_bar_is_not_drawn(self):
        bar = {"page": 1, "id": 1, "obj": "bar", "x": 10, "y": 10, "w": 200, "h": 30, "val": 50}
        assert render({**bar, "text": "50 %"}) == render(bar)

    def test_a_label_grows_to_its_text_with_expand_and_break(self):
        label = {"obj": "label", "w": 60, "h": 20, "text": "A text that is longer than the label"}

        assert item_of(label).obj_rect.width() > 60
        assert item_of({**label, "mode": "crop"}).obj_rect.width() == 60
        grown = item_of({**label, "mode": "break"}).obj_rect
        assert grown.width() == 60 and grown.height() > 20

    def test_a_label_with_dots_ends_with_dots_instead_of_overflowing(self):
        label = item_of({"obj": "label", "w": 60, "h": 20, "text": "A text that is longer than the label", "mode": "dots"})

        assert label.text_item.toPlainText().endswith("...")
        assert label.obj_rect.width() == 60

    def test_a_message_box_is_in_the_middle_of_the_screen_whatever_its_position(self):
        box = item_of({"obj": "msgbox", "x": 5, "y": 7, "w": 200, "h": 100})

        assert (box.obj_x, box.obj_y) == (140, round((320 - box.obj_h) / 2))

    def test_a_message_box_is_as_high_as_its_text_and_buttons_and_ignores_h(self):
        one_line = item_of({"obj": "msgbox", "w": 300, "h": 250, "text": "Message"})
        two_lines = item_of({"obj": "msgbox", "w": 300, "h": 250, "text": "Message\nover two lines"})

        # measured on a plate with its font (112 and 144): 6 above the text, 12 + 50 + 12 for the buttons
        assert one_line.obj_h == round(6 + one_line.line_height + 74)
        assert two_lines.obj_h == round(6 + 2 * two_lines.line_height + 74)
        assert two_lines.obj_h > one_line.obj_h

    def test_a_roller_is_as_high_as_its_rows_if_it_has_them_and_else_as_high_as_it_says(self):
        assert item_of({"obj": "roller", "h": 60}).obj_h == 60
        assert item_of({"obj": "roller", "h": 60, "rows": 3}).obj_h > 100

    def test_a_qr_code_takes_its_size_from_w_and_h_or_from_size(self):
        assert item_of({"obj": "qrcode", "w": 80, "h": 100}).obj_w == 80
        assert item_of({"obj": "qrcode", "w": 80, "h": 100, "size": 60}).obj_w == 60
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.qrcode import HaspQrCodeItem

        assert HaspQrCodeItem({"obj": "qrcode"}).obj_w == 140


@pytest.mark.usefixtures("qapp")
class TestBox(TestBase):
    def test_the_shadow_fades_out_around_the_edge_of_the_box(self):
        box = {"page": 1, "id": 1, "obj": "label", "x": 40, "y": 40, "w": 40, "h": 40, "bg_color": "#000000", "bg_opa": 255}
        image = render({**box, "shadow_width": 10, "shadow_color": "#ffffff", "shadow_opa": 255})

        # 1 pixel outside: the shadow is about half there, 6 pixels outside: it is gone
        assert 60 < image.pixelColor(39, 60).red() < 200
        assert image.pixelColor(33, 60).red() == 0

    def test_the_border_is_inside_of_the_box_and_can_be_limited_to_some_sides(self):
        box = {"page": 1, "id": 1, "obj": "label", "x": 10, "y": 10, "w": 40, "h": 40, "bg_color": "#000000", "bg_opa": 255}
        box = {**box, "border_width": 4, "border_color": "#ff0000"}

        assert render(box).pixelColor(11, 30).name() == "#ff0000"
        assert render(box).pixelColor(9, 30).name() == "#000000"
        # only the bottom (1)
        bottom = render({**box, "border_side": 1})
        assert bottom.pixelColor(30, 48).name() == "#ff0000" and bottom.pixelColor(30, 11).name() == "#000000"

    def test_a_radius_is_at_most_half_of_the_short_side(self):
        box = {"page": 1, "id": 1, "obj": "label", "x": 0, "y": 0, "w": 100, "h": 20, "bg_color": "#ff0000", "bg_opa": 255}

        image = render({**box, "radius": 500})

        assert image.pixelColor(50, 10).name() == "#ff0000" and image.pixelColor(0, 0).name() == "#000000"


@pytest.mark.usefixtures("qapp")
class TestTextAndShapes(TestBase):
    def test_text_is_set_in_pixels_of_the_font_size_and_has_the_lead_of_the_plate(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import line_lead, plate_font

        assert plate_font(24).pixelSize() == 24
        assert [line_lead(plate_font(size)) for size in (12, 24, 32)] == [3, 3, 4]

    def test_text_in_a_size_that_is_not_built_into_the_plate_has_no_lead(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import line_lead, line_top, plate_font

        # the plate renders these from a TrueType font: e.g. a label of size 25 that is 30 pixels high shows its descenders
        assert [line_lead(plate_font(size)) for size in (18, 25, 36)] == [0, 0, 0]
        assert line_top(plate_font(25)) == 0

    def test_text_is_drawn_in_the_fonts_of_the_plate_that_are_part_of_the_package(self):
        from PyQt6 import QtGui

        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import line_lead, line_top, plate_font

        assert QtGui.QFontInfo(plate_font(24)).family() == "openHASP Roboto Condensed"
        # the pixel font unscii: a line of 16 pixels, like on the plate
        pixel = plate_font(8)
        assert QtGui.QFontInfo(pixel).family() == "openHASP unscii"
        assert (pixel.pixelSize(), line_lead(pixel), line_top(pixel)) == (8, 8, 3)

    def test_a_truetype_font_file_of_the_device_is_drawn_in_its_font(self, tmp_path):
        import shutil

        from PyQt6 import QtGui

        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets import drawing

        # a TrueType font that is not Roboto Condensed, as a font file of the device: the pixel font of the package
        font_file = shutil.copy(drawing._PIXEL_FONT_FILE, tmp_path / "pixels.ttf")
        drawing.set_font_files({"pixels.ttf": font_file})
        try:
            font = drawing.plate_font("pixels_20")
        finally:
            drawing.set_font_files({})

        assert (QtGui.QFontInfo(font).family(), font.pixelSize()) == ("openHASP unscii", 20)
        # a font file the device doesn't have doesn't change the font, like on the plate
        assert drawing.plate_font("pixels_20").pixelSize() == 24

    def test_lines_are_wrapped_at_words(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import plate_font, wrap_lines

        assert wrap_lines(plate_font(24), "a b", 1000) == ["a b"]
        assert wrap_lines(plate_font(24), "one\ntwo", 1000) == ["one", "two"]
        assert wrap_lines(plate_font(24), "one two three", 1) == ["one", "two", "three"]

    def test_a_checkbox_is_centered_in_its_height_and_its_box_follows_the_font(self):
        small = item_of({"obj": "checkbox", "text_font": 12, "h": 40})
        big = item_of({"obj": "checkbox", "text_font": 32, "h": 40})

        assert (small.box_size, big.box_size) == (22, 46)
        assert small.obj_rect.top() == (40 - small.obj_h) / 2

    def test_a_checkbox_styles_its_background_with_every_part_but_the_box(self):
        from openhasp_config_manager.gui.domain.style_parts import Part, State

        checkbox = item_of({"obj": "checkbox", "bg_color20": "#FF0000", "bg_color10": "#00FF00"})

        assert checkbox.own_style("bg_color", Part.MAIN, State.DEFAULT) == "#FF0000"

    def test_a_dropdown_text_starts_at_the_top_left_and_its_symbol_follows_the_font(self):
        assert painted(render({"obj": "dropdown", "options": "One\nTwo", "w": 146, "h": 38, "text_font": 12})) > 0
        assert render({"obj": "dropdown", "options": "One\nTwo", "w": 146, "h": 38, "text_font": 12}) != render(
            {"obj": "dropdown", "options": "One\nTwo", "w": 146, "h": 38, "text_font": 24}
        )

    def test_a_roller_draws_its_border_over_the_selected_row_and_its_text_centered_in_every_row(self):
        roller = {"x": 10, "y": 10, "w": 100, "h": 120, "obj": "roller", "options": "One\nTwo\nThree", "val": 1}

        image = render({**roller, "border_width": 3, "border_color": "#FF0000", "border_opa": 255, "bg_grad_dir": 0})

        # the selected row is in the middle: its left edge is part of the border
        assert image.pixelColor(11, 70).name() == "#ff0000"
        assert render({**roller, "rows": 3}) == render({**roller, "h": 135})

    def test_a_linemeter_has_18_lines_and_the_lines_of_the_value_follow_the_indicator_width(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.linemeter import HaspLineMeterItem

        meter = item_of({"obj": "linemeter", "w": 86, "h": 86, "val": 50})

        assert isinstance(meter, HaspLineMeterItem) and meter.active_lines() == 9
        thin = render({"obj": "linemeter", "w": 86, "h": 86, "val": 100, "line_width10": 1})
        wide = render({"obj": "linemeter", "w": 86, "h": 86, "val": 100, "line_width10": 8})
        assert thin != wide

    def test_a_button_matrix_ignores_val(self):
        matrix = {"obj": "btnmatrix", "options": ["A", "B"], "w": 200, "h": 60, "toggle": True}

        assert render({**matrix, "val": 1}) == render(matrix)

    def test_a_spinner_turns(self):
        from PyQt6 import QtTest

        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.spinner import HaspSpinnerItem

        spinner = HaspSpinnerItem({"obj": "spinner", "w": 60, "h": 60, "speed": 400})
        start = spinner.rotation_degrees
        QtTest.QTest.qWait(150)

        assert start < 5
        assert spinner.rotation_degrees > 20

    def test_a_qr_code_has_whole_pixel_modules_and_a_quiet_zone_of_two(self):
        pytest.importorskip("segno")
        from openhasp_config_manager.gui.domain.qr_code import qr_modules

        assert len(qr_modules("https://openhasp.com")) == 25
        item = item_of({"obj": "qrcode", "w": 100, "h": 100, "text": "https://openhasp.com"})
        assert item.obj_w == 100
        assert 100 // (25 + 4) == 3


@pytest.mark.usefixtures("qapp")
class TestDrawingHelpers(TestBase):
    def test_an_opacity_is_a_share_between_0_and_1(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import opacity

        assert opacity(255) == 1.0
        assert opacity("0") == 0.0
        assert opacity(300) == 1.0
        assert opacity(None) == 1.0
        assert opacity("{{ not rendered }}", 128) == 128 / 255

    def test_the_value_of_an_object_is_between_its_min_and_max(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import selected_index, value_fraction

        assert value_fraction({"val": 25}) == 0.25
        assert value_fraction({"val": 5, "min": 0, "max": 10}) == 0.5
        assert value_fraction({"min": 10, "max": 10}) == 0.0
        assert selected_index({"val": "2"}) == 2
        assert selected_index({}) == 0

    def test_a_square_is_centered_in_the_larger_rect(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import centered_square

        square = centered_square(100, 60)

        assert (square.x(), square.y(), square.width(), square.height()) == (20, 0, 60, 60)
