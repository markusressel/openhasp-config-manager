from openhasp_config_manager.gui.domain.style_parts import Part, State, style_key
from tests import TestBase


class TestStyleKey(TestBase):
    def test_suffix_is_part_then_state(self):
        assert style_key("bg_color") == "bg_color00"
        assert style_key("bg_color", Part.KNOB) == "bg_color20"
        assert style_key("radius", Part.INDICATOR, State.PRESSED) == "radius12"
