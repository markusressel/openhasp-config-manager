from openhasp_config_manager.util import contains_nested_dict_key
from tests import TestBase


class TestUtil(TestBase):

    def test_contains_nested_key_true(self, tmp_path):
        # GIVEN
        d = {
            "a": {
                "items": {
                    "b": 1
                }
            }
        }

        # WHEN
        result = contains_nested_dict_key(d, "items")
        assert result is True

    def test_contains_nested_key_false(self, tmp_path):
        # GIVEN
        d = {
            "a": {
                "items": {
                    "b": 1
                }
            }
        }

        # WHEN
        result = contains_nested_dict_key(d, "test")
        assert result is False
