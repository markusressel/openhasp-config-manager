from openhasp_config_manager.gui.domain.properties import group_properties
from tests import TestBase


class TestProperties(TestBase):
    def test_group_properties(self):
        # GIVEN
        obj = {
            "page": 1,
            "id": 2,
            "obj": "btn",
            "x": 0,
            "y": 0,
            "w": 10,
            "h": 10,
            "text": "Hi",
            "text_color": "#FFFFFF",
            "bg_color": "#000000",
            "radius": 4,
            "action": "next",
            "foo": 1,
        }

        # WHEN
        result = group_properties(obj)

        # THEN
        assert result == [
            ("Object", ["page", "id", "obj"]),
            ("Position", ["x", "y"]),
            ("Size", ["w", "h"]),
            ("Text", ["text", "text_color"]),
            ("Style", ["bg_color", "radius"]),
            ("Behaviour", ["action"]),
            ("Other", ["foo"]),
        ]

    def test_empty_groups_are_left_out(self):
        assert group_properties({"x": 1}) == [("Position", ["x"])]
