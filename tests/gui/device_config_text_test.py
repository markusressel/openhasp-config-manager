import json

import pytest

from openhasp_config_manager.gui.domain.device_config_text import set_debug_ansi
from tests import TestBase

CONFIG = """{
  "gui": {
    "ansi": 7,
    "rotate": 1
  },
  "debug": {
    "ansi": 0,
    "baud": 115200
  },
  "other": {"ansi": 5}
}
"""


class TestSetDebugAnsi(TestBase):
    def test_changes_only_the_debug_setting(self):
        # WHEN
        result = set_debug_ansi(CONFIG, True)

        # THEN
        assert result == CONFIG.replace('"ansi": 0', '"ansi": 1')
        assert json.loads(result)["gui"]["ansi"] == 7
        assert json.loads(result)["other"]["ansi"] == 5

    def test_back_again(self):
        assert set_debug_ansi(set_debug_ansi(CONFIG, True), False) == CONFIG

    def test_a_setting_that_is_already_set_keeps_the_text(self):
        assert set_debug_ansi(CONFIG.replace('"ansi": 0', '"ansi": 1'), True) == CONFIG.replace('"ansi": 0', '"ansi": 1')

    def test_no_ansi_in_the_debug_section(self):
        with pytest.raises(ValueError):
            set_debug_ansi('{"gui": {"ansi": 1}, "debug": {"baud": 1}}', True)

    def test_no_debug_section(self):
        with pytest.raises(ValueError):
            set_debug_ansi('{"gui": {"ansi": 1}}', True)
