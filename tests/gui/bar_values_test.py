import pytest

from openhasp_config_manager.gui.domain.bar_values import bar_range, indicator_span, pressed_knob
from tests import TestBase


class TestBarValues(TestBase):
    def test_the_start_is_limited_to_the_range_and_to_the_value(self):
        assert bar_range({"start_value": 30, "val": 60}, slider=True) == (0, 100, 30, 60)
        assert bar_range({"start_value": 70, "val": 60}, slider=True) == (0, 100, 60, 60)
        assert bar_range({"min": 10, "start_value": 0, "val": 60}, slider=False) == (10, 100, 10, 60)

    def test_a_type_after_the_start_value_resets_it_unless_it_is_range(self):
        assert bar_range({"start_value": 30, "type": 1, "val": 60}, slider=True)[2] == 0
        assert bar_range({"start_value": 30, "type": 2, "val": 60}, slider=True)[2] == 30
        assert bar_range({"type": 1, "start_value": 30, "val": 60}, slider=True)[2] == 30
        # a bar has no type
        assert bar_range({"start_value": 30, "type": 1, "val": 60}, slider=False)[2] == 30

    def test_the_indicator_goes_from_the_start_to_the_value(self):
        assert indicator_span({"start_value": 25, "val": 75}, slider=False) == (0.25, 0.75)
        assert indicator_span({"val": 0}, slider=False) is None

    def test_a_symmetrical_slider_fills_from_0(self):
        assert indicator_span({"type": 1, "min": -50, "max": 50, "val": 25}, slider=True) == (0.5, 0.75)
        assert indicator_span({"type": 1, "min": -50, "max": 50, "val": -25}, slider=True) == (0.25, 0.5)
        assert indicator_span({"type": 1, "min": 0, "max": 100, "val": 25}, slider=True) == (0, 0.25)
        # a bar is never symmetrical
        assert indicator_span({"type": 1, "min": -50, "max": 50, "val": 25}, slider=False) == (0, 0.75)

    @pytest.mark.parametrize(
        "finger, knob",
        [(10, "start"), (45, "start"), (100, "start"), (110, "val"), (150, "val"), (190, "val")],
    )
    def test_a_range_slider_moves_the_knob_nearer_to_the_finger(self, finger, knob):
        assert pressed_knob(finger, (30, 60), (140, 170), vertical=False) == knob

    def test_the_upper_knob_of_a_vertical_range_slider_is_the_value(self):
        assert pressed_knob(10, (140, 170), (30, 60), vertical=True) == "val"
        assert pressed_knob(190, (140, 170), (30, 60), vertical=True) == "start"
