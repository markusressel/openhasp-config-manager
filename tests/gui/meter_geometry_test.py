from openhasp_config_manager.gui.domain.meter_geometry import (
    active_lines,
    arc_angles,
    fraction,
    gauge_labels,
    number,
    value_fraction,
)
from tests import TestBase


class TestMeterGeometry(TestBase):
    def test_a_property_that_is_no_number_is_the_default(self):
        assert number("12.5", 0) == 12.5
        assert number("{{ not rendered }}", 3) == 3
        assert number(None, 3) == 3

    def test_the_value_of_an_object_is_between_its_min_and_max(self):
        assert value_fraction({"val": 25}) == 0.25
        assert value_fraction({"val": 5, "min": 0, "max": 10}) == 0.5
        assert value_fraction({"min": 10, "max": 10}) == 0.0
        assert fraction(150, 0, 100) == 1.0
        assert fraction(-5, 0, 100) == 0.0

    def test_the_indicator_of_an_arc_fills_from_the_start_the_middle_or_the_end(self):
        assert arc_angles(0, 180, 0, kind=0, value=0.5) == ((0, 180), (0, 90))
        assert arc_angles(0, 180, 0, kind=2, value=0.5)[1] == (90, 90)
        assert arc_angles(0, 180, 0, kind=1, value=0.25)[1] == (45, 45)
        assert arc_angles(0, 180, 0, kind=1, value=0.75)[1] == (90, 45)

    def test_an_arc_is_rotated_and_a_closed_arc_is_a_full_circle(self):
        assert arc_angles(135, 45, 90, kind=0, value=0)[0] == (225, 270)
        assert arc_angles(0, 360, 0, kind=0, value=1) == ((0, 360), (0, 360))

    def test_the_labels_of_a_gauge_go_from_min_to_max(self):
        gauge = {"min": 0, "max": 1000}

        assert gauge_labels(gauge) == ["0", "200", "400", "600", "800", "1000"]
        assert gauge_labels({**gauge, "format": 2, "label_count": 3}) == ["0", "5", "10"]
        assert gauge_labels({**gauge, "label_count": 0}) == []

    def test_a_linemeter_activates_the_lines_up_to_its_value(self):
        assert active_lines(20, 0.5) == 10
        assert active_lines(20, 1.0) == 20
        assert active_lines(18, 0.5) == 9
