from openhasp_config_manager.gui.domain.snapping import Rect, snap_rect
from tests import TestBase

PLATE = Rect(0, 0, 480, 320)


class TestSnapping(TestBase):
    def test_snaps_to_grid_without_alignment_lines_nearby(self):
        # GIVEN
        rect = Rect(43, 101, 20, 20)

        # WHEN
        result = snap_rect(rect, others=[], bounds=PLATE, grid=8, threshold=2)

        # THEN
        assert (result.x, result.y) == (40, 104)
        assert result.guides_x == ()
        assert result.guides_y == ()

    def test_snaps_left_edge_to_right_edge_of_other_object(self):
        # GIVEN
        other = Rect(100, 200, 50, 50)
        rect = Rect(153, 20, 20, 20)

        # WHEN
        result = snap_rect(rect, others=[other], bounds=PLATE, grid=8, threshold=6)

        # THEN
        assert result.x == 150
        assert 150 in result.guides_x

    def test_snaps_center_to_center_of_plate(self):
        # GIVEN
        rect = Rect(198, 13, 80, 40)  # center x = 238, plate center = 240

        # WHEN
        result = snap_rect(rect, others=[], bounds=PLATE, grid=None, threshold=6)

        # THEN
        assert result.x == 200
        assert 240 in result.guides_x

    def test_prefers_the_closest_line(self):
        # GIVEN
        others = [Rect(105, 0, 10, 10), Rect(0, 0, 103, 10)]
        rect = Rect(102, 50, 10, 10)

        # WHEN
        result = snap_rect(rect, others=others, bounds=PLATE, grid=None, threshold=6)

        # THEN
        assert result.x == 103

    def test_keeps_position_without_grid_and_lines(self):
        # GIVEN
        rect = Rect(43, 101, 20, 20)

        # WHEN
        result = snap_rect(rect, others=[], bounds=PLATE, grid=None, threshold=2)

        # THEN
        assert (result.x, result.y) == (43, 101)
