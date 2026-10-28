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

        assert (box.obj_x, box.obj_y) == (140, 110)

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
